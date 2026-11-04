"""DEBUG-only monotonic spans. No payloads, exception strings or extra I/O calls."""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

from app.diagnostics import TOKEN, context, emit, performance_enabled

parent: ContextVar[str | None] = ContextVar("performance_parent", default=None)
operation: ContextVar[str | None] = ContextVar("performance_operation", default=None)
provider_role: ContextVar[str | None] = ContextVar("performance_provider_role", default=None)


@contextmanager
def provider_scope(role):
    token = provider_role.set(role)
    try:
        yield
    finally:
        provider_role.reset(token)


class Timing:
    def __init__(
        self, stage, *, role=None, provider=None, model=None, clock=None, bind_parent=True
    ):
        self.stage, self.role, self.provider, self.model = stage, role, provider, model
        self.clock = clock or time.monotonic
        self.enabled = performance_enabled()
        self.finished = False
        self.bind_parent = bind_parent

    def __enter__(self):
        if self.enabled:
            self.start = self.clock()
            current = context.get()
            self.origin = current.started if current else self.start
            self.parent_id = parent.get()
            self.span_id = None
            if current:
                current.sequence += 1
                self.span_id = f"span_{current.sequence}"
                if self.stage == "provider_sdk":
                    current.provider_calls += 1
            self.token = parent.set(self.span_id) if self.bind_parent else None
            self.operation_token = operation.set(self.stage) if self.bind_parent else None
        return self

    def finish(self, error=None):
        if not self.enabled or self.finished:
            return
        self.finished = True
        end = self.clock()
        code = getattr(error, "code", None)
        if not isinstance(code, str) or not TOKEN.fullmatch(code):
            code = None
        cancelled = isinstance(error, BaseException) and type(error).__name__ == "CancelledError"
        emit(
            "performance_stage",
            level=logging.DEBUG,
            stage=self.stage,
            role=self.role,
            provider=self.provider,
            model=self.model,
            sdk_max_retries=0 if self.stage == "provider_sdk" else None,
            latency_category="provider" if self.stage == "provider_sdk" else "application",
            span_id=self.span_id,
            parent_span_id=self.parent_id,
            start_offset_ms=max(0, round((self.start - self.origin) * 1000)),
            end_offset_ms=max(0, round((end - self.origin) * 1000)),
            duration_ms=max(0, round((end - self.start) * 1000)),
            outcome="cancelled" if cancelled else "failed" if error else "completed",
            error_code="request_cancelled" if cancelled else code,
        )

    def __exit__(self, _kind, error, _traceback):
        try:
            self.finish(error)
        finally:
            if self.enabled and self.token is not None:
                parent.reset(self.token)
                operation.reset(self.operation_token)
        return False
