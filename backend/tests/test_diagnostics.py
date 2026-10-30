import asyncio
import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.answer.schemas import AnswerRecommendation
from app.answer.service import AnswerService
from app.auth.dependencies import required_current_user
from app.config import Settings
from app.database import PlatformError
from app.diagnostics import DiagnosticBoundary, category, configure, context, emit, span
from app.learning.service import SessionService
from app.main import create_app
from app.schemas import QuestionObservation


def events(caplog):
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "solveguide.diagnostics"
    ]


@pytest.mark.parametrize(
    "code,expected",
    [
        ("session_expired", "authentication"),
        ("session_revoked", "authentication"),
        ("session_check_timeout", "network_timeout"),
        ("backend_connection_failed", "network_connect"),
        ("preparation_changed", "session_revision"),
        ("database_schema", "database"),
        ("answer_timeout", "provider_timeout"),
        ("request_cancelled", "cancellation"),
    ],
)
def test_failure_classification(code, expected):
    assert category(code) == expected


def test_redaction_is_allowlisted_not_exception_string_scrubbing(caplog):
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        emit(
            "test_event",
            stage="session",
            status=503,
            error_code="database_schema",
            sqlstate="42p01",
            endpoint="/api/v1/auth/google/callback?code=secret-oauth",
            question_text="secret question",
            answer="secret answer",
            document="secret notes",
            authorization="Bearer secret-token",
            cookies="secret-cookie",
            exception=RuntimeError("postgresql://private:password@host/db"),
        )
    data = events(caplog)[-1]
    assert data["sqlstate"] == "42p01"
    assert data["endpoint"] == "/api/v1/auth/google/callback"
    assert "secret" not in caplog.text and "password" not in caplog.text


def test_monitor_trace_crosses_http_and_service_without_payload_logging(
    api_factory, image_payload, caplog
):
    trace = "live-1a-123456-1"
    request = "monitor-2-3-vision-abcdef"
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        response = api_factory().post(
            "/api/v1/vision/question",
            json=image_payload,
            headers={
                "X-Solveguide-Trace-ID": trace,
                "X-Request-ID": request,
                "X-Solveguide-Candidate-ID": "question-2-3",
            },
        )
    assert response.headers["x-request-id"] == request
    rows = events(caplog)
    assert rows and all(row["request_id"] == request and row["trace_id"] == trace for row in rows)
    assert rows[-1]["candidate_id"] == "question-2-3"
    assert rows[-1]["outcome"] == "detected"
    assert image_payload["image_base64"] not in caplog.text


def test_bad_correlation_headers_and_sensitive_query_are_not_echoed(caplog):
    app = create_app(Settings(_env_file=None))
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        response = TestClient(app, base_url="http://127.0.0.1").get(
            "/api/health?token=private-query",
            headers={
                "X-Request-ID": "Bearer private-token",
                "X-Solveguide-Trace-ID": "private-secret",
                "X-Solveguide-Candidate-ID": "private-question",
            },
        )
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 36
    assert "private" not in caplog.text
    assert events(caplog)[-1]["endpoint"] == "/api/health"


def test_context_is_isolated_across_overlapping_requests(caplog):
    app = FastAPI()
    app.add_middleware(DiagnosticBoundary)

    @app.get("/test")
    async def route():
        emit("before", stage="isolation")
        await asyncio.sleep(0.01)
        emit("after", stage="isolation")
        return {}

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://local"
        ) as client:
            ids = [str(uuid4()), str(uuid4())]
            await asyncio.gather(
                *(client.get("/test", headers={"x-request-id": value}) for value in ids)
            )
            return ids

    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        ids = asyncio.run(run())
    for identifier in ids:
        assert [row["event"] for row in events(caplog) if row["request_id"] == identifier] == [
            "http_request_started",
            "before",
            "after",
            "http_request",
        ]
    assert context.get() is None


def test_healthy_process_and_failed_session_lookup_are_distinguished(caplog):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[required_current_user] = lambda: SimpleNamespace(id=uuid4())

    class Unavailable:
        @span("active_session_lookup")
        async def active(self, owner):
            raise PlatformError("database_unavailable", "safe message")

    app.state.learning_service = Unavailable()
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        client = TestClient(app, base_url="http://127.0.0.1")
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/v1/learning/sessions/active").status_code == 503
    row = events(caplog)[-1]
    assert row["error_code"] == "database_unavailable" and row["error_category"] == "database"
    assert any(v.get("stage") == "active_session_lookup" for v in events(caplog))


def test_revision_and_owner_scope_failures_are_diagnostic_without_contents(caplog):
    service = SessionService(None)
    identifier = uuid4()

    class Transaction:
        async def get(self, _):
            return SimpleNamespace(id=identifier, revision=4, objective="private objective")

    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        with pytest.raises(PlatformError):
            asyncio.run(service.owned(Transaction(), identifier, 3))
    row = next(row for row in events(caplog) if row["event"] == "session_revision_check")
    assert row["expected_revision"] == 3 and row["actual_revision"] == 4
    assert "private objective" not in caplog.text
    caplog.clear()

    class Missing:
        async def get(self, _):
            return None

    with pytest.raises(PlatformError):
        asyncio.run(service.owned(Missing(), identifier, 1))
    assert any(row.get("reason") == "ownership_scope_miss" for row in events(caplog))


def test_provider_abstention_has_a_reason_without_logging_its_explanation(
    observation_data, answer_data, caplog
):
    payload = {
        **answer_data,
        "status": "insufficient_information",
        "answer_text": None,
        "selected_options": [],
        "key_points": [],
        "confidence": 0,
        "explanation": "private provider explanation",
        "warnings": ["private warning"],
    }

    class Provider:
        async def recommend(self, observation):
            return AnswerRecommendation.model_validate(payload)

    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        asyncio.run(
            AnswerService(Provider()).recommend(
                QuestionObservation.model_validate(observation_data)
            )
        )
    assert any(row.get("reason") == "provider_abstention" for row in events(caplog))
    assert "private" not in caplog.text and observation_data["question_text"] not in caplog.text


def test_debug_does_not_enable_sdk_or_sql_payload_logs():
    try:
        configure("DEBUG")
        assert logging.getLogger("solveguide").getEffectiveLevel() == logging.DEBUG
        for name in ("httpx", "openai", "httpcore", "sqlalchemy.engine"):
            assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
        with pytest.raises(ValidationError):
            Settings(_env_file=None, solveguide_log_level="VERBOSE")
    finally:
        configure("INFO")


def test_unexpected_exception_is_sanitized_at_http_boundary(caplog):
    app = FastAPI()
    app.add_middleware(DiagnosticBoundary)

    @app.get("/test")
    async def route():
        raise RuntimeError("private provider payload and password")

    with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
        response = TestClient(app).get("/test")
    assert response.status_code == 500 and "private" not in caplog.text
    assert events(caplog)[-1]["error_code"] == "internal_error"


def test_successful_heartbeat_is_quiet_at_info_but_failures_remain_visible(caplog):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[required_current_user] = lambda: SimpleNamespace(id=uuid4())

    class Active:
        async def active(self, owner):
            return None

    app.state.learning_service = Active()
    with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
        client = TestClient(app, base_url="http://127.0.0.1")
        for _ in range(5):
            assert client.get("/api/v1/learning/sessions/active").status_code == 200
    assert events(caplog) == []
    app.dependency_overrides.clear()
    with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
        assert client.get("/api/v1/learning/sessions/active").status_code == 401
    rows = [row for row in events(caplog) if row["event"] == "http_request"]
    assert len(rows) == 1 and rows[0]["error_category"] == "authentication"


def test_cancelled_request_resets_context_and_never_logs_its_payload(caplog):
    async def app(scope, receive, send):
        raise asyncio.CancelledError("private cancelled payload")

    async def run():
        with pytest.raises(asyncio.CancelledError):
            await DiagnosticBoundary(app)(
                {"type": "http", "path": "/api/v1/answer", "headers": []}, None, None
            )
        assert context.get() is None

    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        asyncio.run(run())
    row = events(caplog)[-1]
    assert row["outcome"] == "cancelled" and row["error_category"] == "cancellation"
    assert "status" not in row and "private" not in caplog.text
