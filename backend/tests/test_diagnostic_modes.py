"""Focused diagnostics only: synthetic requests, no database or provider connection."""

import asyncio
import json
import logging

import pytest
from pydantic import ValidationError

from app import diagnostics as diag
from app.config import Settings
from app.diagnostic_reports import Metrics, resolve_mode
from app.performance import Timing


@pytest.fixture(autouse=True)
def restore_logging():
    yield
    diag.configure("INFO")


@pytest.mark.parametrize(
    "explicit,legacy,expected",
    [
        (None, "INFO", "NORMAL"),
        (None, "DEBUG", "DEBUG"),
        ("NORMAL", "DEBUG", "NORMAL"),
        ("PERFORMANCE", "DEBUG", "PERFORMANCE"),
        ("DEBUG", "INFO", "DEBUG"),
        ("NORMAL", "INFO", "NORMAL"),
    ],
)
def test_mode_precedence(explicit, legacy, expected):
    assert resolve_mode(explicit, legacy) == expected
    diag.configure(legacy, explicit)
    assert diag.performance_enabled() == (expected != "NORMAL")
    assert logging.getLogger("solveguide").getEffectiveLevel() == (
        logging.DEBUG if expected == "DEBUG" else logging.INFO
    )


def test_explicit_mode_environment_is_validated(monkeypatch):
    monkeypatch.setenv("SOLVEGUIDE_DIAGNOSTIC_MODE", "PERFORMANCE")
    monkeypatch.setenv("SOLVEGUIDE_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert (
        resolve_mode(settings.solveguide_diagnostic_mode, settings.solveguide_log_level)
        == "PERFORMANCE"
    )
    monkeypatch.setenv("SOLVEGUIDE_DIAGNOSTIC_MODE", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def rows(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == diag.logger.name]


def run_request(status=200, cancel=False, path="/api/v1/answer", request="monitor-1-2-answer-aa"):
    async def app(scope, receive, send):
        @diag.span("authentication")
        async def auth():
            pass

        await auth()
        for _ in range(10):
            diag.emit("session_validated", level=logging.DEBUG, question_text="private")
        diag.emit("question_metadata", level=logging.DEBUG, question_type="multiple_choice")
        with Timing("provider_sdk", role="answer", clock=iter([10, 10.25]).__next__):
            pass
        for duration in (100, 200):
            diag.emit(
                "performance_stage",
                level=logging.DEBUG,
                stage="database_query",
                duration_ms=duration,
            )
        diag.outcome("answered")
        if cancel:
            raise asyncio.CancelledError("secret payload")
        if status >= 400:
            diag.emit("security_failure", level=logging.WARNING, error_code="session_expired")
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message):
        pass

    return asyncio.run(
        diag.DiagnosticBoundary(app)(
            {
                "type": "http",
                "path": path,
                "headers": [
                    (b"x-request-id", request.encode()),
                    (b"x-solveguide-trace-id", b"live-a-b-1"),
                    (b"x-solveguide-candidate-id", b"question-1-2"),
                ],
            },
            None,
            send,
        )
    )


def test_performance_has_one_request_report_not_routine_events(caplog):
    diag.configure("DEBUG", "PERFORMANCE")
    # Even a capture handler accepting DEBUG must not expose detailed spans in PERFORMANCE.
    with caplog.at_level(logging.DEBUG, logger=diag.logger.name):
        run_request()
    events = rows(caplog)
    assert len(events) == 1 and events[0]["event"] == "performance_report"
    row = events[0]
    assert row["boundary"] == "backend_request" and row["observed_total_ms"] is None
    assert row["candidate_id"] == "question-1-2" and row["request_id"] == "monitor-1-2-answer-aa"
    assert row["provider_calls"] == 1 and row["authentication_checks"] == 1
    assert row["stages_ms"]["provider_answer"]["max_single_span_ms"] == 250
    assert row["stages_ms"]["database_query"] == {"count": 2, "max_single_span_ms": 200}
    assert row["stages_ms"]["retrieval"] is None and row["panel_ready_ms"] is None
    assert "private" not in caplog.text and "secret" not in caplog.text
    assert diag.context.get() is None


@pytest.mark.parametrize(
    "status,cancel,expected", [(503, False, "failed"), (200, True, "cancelled")]
)
def test_failure_and_cancel_report_once_with_security_warnings_visible(
    caplog, status, cancel, expected
):
    diag.configure("INFO", "PERFORMANCE")
    with caplog.at_level(logging.INFO, logger=diag.logger.name):
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                run_request(status, cancel)
        else:
            run_request(status, cancel)
    report = [row for row in rows(caplog) if row["event"] == "performance_report"]
    assert len(report) == 1 and report[0]["outcome"] == expected
    if not cancel:
        assert any(row["event"] == "security_failure" for row in rows(caplog))
    assert "secret" not in caplog.text


def test_polling_is_quiet_and_normal_preserves_lifecycle_and_errors(caplog):
    for mode in ("NORMAL", "PERFORMANCE"):
        diag.configure("DEBUG", mode)
        with caplog.at_level(logging.INFO, logger=diag.logger.name):
            for _ in range(10):
                run_request(path="/api/v1/learning/preparation")
        assert rows(caplog) == []
    diag.configure("INFO", "NORMAL")
    with caplog.at_level(logging.INFO, logger=diag.logger.name):
        diag.emit("application_started")
        diag.emit("routine_success")
        diag.emit("security_failure", level=logging.ERROR, error_code="session_revoked")
        diag.emit("application_stopped")
    assert [r["event"] for r in rows(caplog)] == [
        "application_started",
        "security_failure",
        "application_stopped",
    ]


def test_aggregation_has_fixed_vocabulary_and_never_sums_overlaps():
    metrics = Metrics()
    for i in range(1000):
        metrics.observe(f"private_{i}", i)
        metrics.observe("authentication", 100)
    metrics.observe("authentication", 300)
    metrics.observe("database_query", 250)
    assert len(metrics.stages) == 2
    assert metrics.view()["authentication"] == {"count": 1001, "max_single_span_ms": 300}
    assert "total" not in metrics.view()
    assert "private" not in json.dumps(metrics.view())


def test_debug_retains_detail_and_handlers_do_not_duplicate(caplog):
    diag.configure("DEBUG", "DEBUG")
    diag.configure("DEBUG", "DEBUG")
    assert len(logging.getLogger("openai").handlers) == 1
    assert not logging.getLogger("openai").propagate
    with caplog.at_level(logging.DEBUG, logger=diag.logger.name):
        run_request()
        logging.getLogger("openai").warning("secret token and provider payload")
    events = rows(caplog)
    assert any(r["event"] == "performance_stage" for r in events)
    assert sum(r["event"] == "dependency_warning" for r in events) == 1
    assert "secret" not in caplog.text


def test_reporting_does_not_add_provider_or_database_calls(api_factory, image_payload, caplog):
    client = api_factory()
    provider = client.app.state.vision_service.provider
    diag.configure("INFO", "PERFORMANCE")
    with caplog.at_level(logging.INFO, logger=diag.logger.name):
        assert client.post("/api/v1/vision/question", json=image_payload).status_code == 200
    assert provider.calls == 1
    assert client.app.state.database.sessions is None
    reports = [r for r in rows(caplog) if r["event"] == "performance_report"]
    assert len(reports) == 1 and reports[0]["database_transactions"] == 0
    assert reports[0]["provider_calls"] == 0  # Fake provider does not invoke an SDK.
    assert image_payload["image_base64"] not in caplog.text
