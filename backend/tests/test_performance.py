"""Synthetic clocks and isolated boundaries only; never connect to providers/PostgreSQL."""

import asyncio
import json
import logging
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi import FastAPI

from app import database
from app.diagnostics import Context, DiagnosticBoundary, context, span
from app.performance import Timing, operation, parent, provider_scope


def records(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == "solveguide.diagnostics"]


def clock(*values):
    sequence = iter(values)
    return lambda: next(sequence)


def test_nested_intervals_not_double_counted_and_safe_metadata(caplog):
    token = context.set(Context("test-request", "test-trace", started=100))
    try:
        with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
            with Timing("parent", clock=clock(100, 101)):
                with Timing(
                    "provider_sdk",
                    clock=clock(100.1, 100.4),
                    role="answer",
                    provider="openai",
                    model="gpt-test",
                ):
                    pass
        events = records(caplog)
        assert [e["duration_ms"] for e in events] == [300, 1000]
        assert events[0]["parent_span_id"] == events[1]["span_id"]
        assert events[0]["start_offset_ms"] == 100
        assert events[0]["model"] == "gpt-test" and events[0]["sdk_max_retries"] == 0
        assert context.get().provider_calls == 1
        assert parent.get() is None and operation.get() is None
    finally:
        context.reset(token)


@pytest.mark.parametrize(
    "error,outcome",
    [(RuntimeError("secret provider payload"), "failed"), (asyncio.CancelledError(), "cancelled")],
)
def test_failure_and_cancellation_have_elapsed_time_without_exception_payload(
    caplog, error, outcome
):
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        with (
            pytest.raises(type(error)),
            Timing("provider_sdk", clock=clock(1, 2), model="sk-private-key", provider="openai"),
        ):
            raise error
    event = records(caplog)[-1]
    assert event["duration_ms"] == 1000 and event["outcome"] == outcome
    assert "model" not in event and "secret" not in caplog.text and "private" not in caplog.text


def test_info_logging_is_a_noop_and_does_not_change_results(caplog):
    token = context.set(Context("request", "trace"))
    try:
        with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
            with Timing("provider_sdk", clock=lambda: pytest.fail("disabled timing read clock")):
                result = {"selected_options": ["A"]}
        assert not records(caplog) and context.get().provider_calls == 0
        assert result == {"selected_options": ["A"]}
    finally:
        context.reset(token)


def test_query_hooks_time_only_execution_without_reading_sql_or_parameters(monkeypatch, caplog):
    state = NS()
    counts = {"count": 0, "ms": 0}
    count_token = database.query_counts.set(counts)
    token = context.set(Context("request", "trace", started=10))
    monkeypatch.setattr(
        database, "Timing", lambda *a, **kw: Timing(*a, **kw, clock=clock(10, 10.25, 10.25))
    )
    try:
        with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
            database.before_query(None, None, "secret SQL", {"token": "private"}, state, False)
            database.after_query(None, None, "secret SQL", {"token": "private"}, state, False)
        assert counts == {"count": 1, "ms": 250}
        assert context.get().database_queries == 1
        assert records(caplog)[-1]["duration_ms"] == 250
        assert "secret" not in caplog.text and "private" not in caplog.text
        assert parent.get() is None
    finally:
        database.query_counts.reset(count_token)
        context.reset(token)


def test_query_failure_records_failure_once_and_never_replaces_exception(caplog):
    execution = NS()
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        database.before_query(None, None, "hidden", {}, execution, False)
        database.query_error(
            NS(execution_context=execution, original_exception=ValueError("private"))
        )
        database.finish_query(execution)  # No duplicate completion log.
    assert len(records(caplog)) == 1 and records(caplog)[0]["outcome"] == "failed"
    assert "private" not in caplog.text


def test_parallel_requests_keep_correlation_and_counters_isolated(caplog):
    app = FastAPI()
    app.add_middleware(DiagnosticBoundary)

    @span("authentication")
    async def auth():
        await asyncio.sleep(0)

    @app.get("/api/health")
    async def route():
        await auth()
        with Timing("provider_sdk", provider="openai", role="answer"):
            await asyncio.sleep(0)
        return {"ok": True}

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await asyncio.gather(
                *[
                    client.get(
                        "/api/health",
                        headers={
                            "X-Request-ID": f"monitor-1-{i}-answer-aa",
                            "X-Solveguide-Trace-ID": f"live-a-b-{i}",
                            "X-Solveguide-Candidate-ID": f"question-1-{i}",
                        },
                    )
                    for i in (1, 2)
                ]
            )

    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        assert all(r.status_code == 200 for r in asyncio.run(run()))
    completions = [e for e in records(caplog) if e["event"] == "http_request"]
    assert len(completions) == 2
    for e in completions:
        i = e["candidate_id"].split("-")[-1]
        assert e["trace_id"] == f"live-a-b-{i}"
        assert e["provider_calls"] == 1 and e["authentication_checks"] == 1
    assert context.get() is None and parent.get() is None


def test_provider_retry_spans_are_separate_not_added_to_lifecycle_total(caplog):
    with caplog.at_level(logging.DEBUG, logger="solveguide.diagnostics"):
        with Timing("attempt_lifecycle", clock=clock(0, 5)):
            for start in (0.0, 4.0):
                with Timing("provider_sdk", role="answer", clock=clock(start, start + 1)):
                    pass
    assert [e["duration_ms"] for e in records(caplog)] == [1000, 1000, 5000]
    # Retry/backoff is a native policy; the SDK remains max_retries=0.
    assert all(e["sdk_max_retries"] == 0 for e in records(caplog)[:2])
    with provider_scope("answer_supplement"):
        from app.performance import provider_role

        assert provider_role.get() == "answer_supplement"
    assert provider_role.get() is None
