"""Allowlisted JSON diagnostics. No request/response bodies, headers or exception text."""

import asyncio
import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from uuid import uuid4

logger = logging.getLogger("solveguide.diagnostics")
TOKEN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
REQUEST = re.compile(
    r"(?:monitor-[0-9]+-[0-9]+-(?:vision|answer)(?:-[0-9a-f]{1,32})?|session-[0-9a-f]{1,32})\Z"
)
TRACE = re.compile(r"live-[0-9a-f]{1,8}-[0-9a-f]{1,32}-[0-9]+\Z")
CANDIDATE = re.compile(r"question-[0-9]+-[0-9]+\Z")


@dataclass
class Context:
    request_id: str
    trace_id: str
    candidate_id: str | None = None
    outcome: str = "completed"
    error_code: str | None = None


context: ContextVar[Context | None] = ContextVar("diagnostic_context", default=None)


def configure(level: str):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("solveguide").setLevel(getattr(logging, level))
    # DEBUG affects application diagnostics only, never SDK payload/SQL tracing.
    for name in (
        "openai",
        "httpx",
        "httpcore",
        "authlib",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "psycopg",
    ):
        external = logging.getLogger(name)
        external.setLevel(logging.WARNING)
        external.propagate = False
        if not any(isinstance(handler, logging.NullHandler) for handler in external.handlers):
            external.addHandler(logging.NullHandler())


def category(code: str) -> str:
    if code in {
        "session_expired",
        "session_revoked",
        "invalid_session",
        "sign_in_required",
        "auth_forbidden",
    }:
        return "authentication"
    if code.startswith(("google_", "invalid_oauth_")) or code in {
        "invalid_exchange",
        "email_unverified",
        "auth_not_configured",
    }:
        return "authentication"
    if code.startswith("database_"):
        return "database"
    if code in {"preparation_changed", "session_revision_mismatch"}:
        return "session_revision"
    if code in {"preparation_not_found", "document_not_found"}:
        return "ownership_or_missing"
    if code in {"backend_timeout", "session_check_timeout"}:
        return "network_timeout"
    if code.startswith(("session_", "preparation_")):
        return "session"
    if code.startswith(("provider_", "answer_", "embedding_", "vision_", "invalid_provider_")):
        return "provider_timeout" if "timeout" in code else "provider"
    if code in {"request_cancelled", "client_disconnected"}:
        return "cancellation"
    if code == "backend_connection_failed":
        return "network_connect"
    if code == "backend_http_error":
        return "backend_http"
    if code in {"backend_invalid_response", "backend_response_too_large"}:
        return "invalid_response"
    if code.startswith("backend_"):
        return "network"
    return "validation_or_internal"


def endpoint(path: str) -> str:
    path = path.split("?", 1)[0]
    fixed = {
        "/api/health",
        "/api/v1/vision/question",
        "/api/v1/answer",
        "/api/v1/learning/preparation",
        "/api/v1/learning/sessions/active",
        "/api/v1/learning/sessions/start",
        "/api/v1/context/documents",
        "/api/v1/context/documents/indexes",
        "/api/v1/context/documents/limits",
        "/api/v1/context/documents/text",
    }
    if path in fixed:
        return path
    if re.fullmatch(
        r"/api/v1/auth/(?:me|logout|google/start|google/callback|desktop/start|desktop/exchange|desktop/cancel)",
        path,
    ):
        return path
    if re.fullmatch(
        r"/api/v1/(?:learning/(?:preparation|sessions)|context/documents)/[0-9a-fA-F-]{36}(?:/(?:ready|end|index|validate))?",
        path,
    ):
        return re.sub(r"[0-9a-fA-F-]{36}", "{id}", path)
    return "/unclassified"


def emit(event: str, *, level: int = logging.INFO, **fields):
    if not logger.isEnabledFor(level):
        return
    current = context.get()
    data = {
        "event": event if TOKEN.fullmatch(event) else "diagnostic_event",
        "level": logging.getLevelName(level),
        "timestamp_ms": round(time.time() * 1000),
    }
    if current:
        data.update(
            request_id=current.request_id,
            trace_id=current.trace_id,
            candidate_id=current.candidate_id,
        )
    integers = {
        "status",
        "duration_ms",
        "revision",
        "expected_revision",
        "actual_revision",
        "selected_count",
        "evidence_count",
        "citation_count",
        "option_count",
        "warning_count",
        "visual_count",
    }
    tokens = {
        "stage",
        "outcome",
        "error_code",
        "error_category",
        "reason",
        "mode",
        "method",
        "question_type",
        "state",
        "provider",
    }
    for key, value in fields.items():
        if key in integers and type(value) is int and value >= 0:
            data[key] = value
        elif key == "sqlstate" and isinstance(value, str) and re.fullmatch(r"[0-9a-z]{5}", value):
            data[key] = value
        elif key in tokens and isinstance(value, str) and TOKEN.fullmatch(value):
            data[key] = value
        elif key in {"session_id", "owner_id"} and UUID.fullmatch(str(value)):
            data[key] = str(value)
        elif key == "endpoint":
            data[key] = endpoint(value)
    logger.log(level, json.dumps(data, separators=(",", ":")))


def outcome(value: str, error: bool = False):
    current = context.get()
    if current:
        current.outcome = value if TOKEN.fullmatch(value) else "failed"
        if error:
            current.error_code = current.outcome


def span(stage: str):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            start = time.monotonic()
            emit("stage_started", level=logging.DEBUG, stage=stage)
            result, code = "completed", None
            try:
                return await function(*args, **kwargs)
            except asyncio.CancelledError:
                result, code = "cancelled", "request_cancelled"
                raise
            except Exception as error:
                result, code = "failed", getattr(error, "code", None)
                if not isinstance(code, str) or not TOKEN.fullmatch(code):
                    code = "internal_error"
                raise
            finally:
                emit(
                    "stage_finished",
                    level=logging.WARNING
                    if code and code != "request_cancelled"
                    else logging.DEBUG,
                    stage=stage,
                    outcome=result,
                    error_code=code,
                    error_category=category(code) if code else None,
                    duration_ms=round((time.monotonic() - start) * 1000),
                )

        return wrapped

    return decorate


class DiagnosticBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])

        def header(name):
            return headers.get(name, b"")[:128].decode("ascii", errors="ignore")

        request_id = header(b"x-request-id")
        if not (UUID.fullmatch(request_id) or REQUEST.fullmatch(request_id)):
            request_id = str(uuid4())
        trace_id = header(b"x-solveguide-trace-id")
        if not (UUID.fullmatch(trace_id) or TRACE.fullmatch(trace_id)):
            trace_id = request_id
        candidate_id = header(b"x-solveguide-candidate-id")
        current = Context(
            request_id, trace_id, candidate_id if CANDIDATE.fullmatch(candidate_id) else None
        )
        token = context.set(current)
        started, status, began = time.monotonic(), 500, False
        route = endpoint(scope["path"])
        emit("http_request_started", level=logging.DEBUG, endpoint=route)

        async def traced_send(message):
            nonlocal status, began
            if message["type"] == "http.response.start":
                status, began = message["status"], True
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-request-id", request_id.encode()),
                        (b"x-solveguide-trace-id", trace_id.encode()),
                    ],
                }
            elif (
                message["type"] == "http.response.body"
                and status >= 400
                and len(message.get("body", b"")) <= 4096
            ):
                try:
                    code = json.loads(message.get("body", b""))["error"]["code"]
                    if isinstance(code, str) and TOKEN.fullmatch(code):
                        current.error_code = code
                        current.outcome = code
                except (ValueError, KeyError, TypeError):
                    pass
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        except asyncio.CancelledError:
            current.error_code, current.outcome = "request_cancelled", "cancelled"
            raise
        except Exception:
            # Never hand raw provider/SQL/request exceptions to terminal access logs.
            current.error_code, current.outcome = "internal_error", "internal_error"
            if began:
                raise RuntimeError("Response stream ended unexpectedly.") from None
            if not began:
                from app.middleware import error_response

                await error_response("internal_error", "The request could not complete.", 500)(
                    scope, receive, traced_send
                )
        finally:
            level = (
                logging.DEBUG
                if current.error_code == "request_cancelled"
                else logging.WARNING
                if status >= 400
                else logging.INFO
                if route in {"/api/v1/vision/question", "/api/v1/answer"}
                else logging.DEBUG
            )
            emit(
                "http_request",
                level=level,
                endpoint=route,
                status=None if current.error_code == "request_cancelled" and not began else status,
                duration_ms=round((time.monotonic() - started) * 1000),
                outcome=current.outcome,
                error_code=current.error_code,
                error_category=category(current.error_code) if current.error_code else None,
            )
            context.reset(token)
