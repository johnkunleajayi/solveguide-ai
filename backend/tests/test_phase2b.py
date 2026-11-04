"""Offline reliability/round-trip regressions. Never use configured external services."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from psycopg import OperationalError as DriverError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from test_access import access as access

from app.auth.models import AuthSession, User
from app.auth.security import digest, now, secret
from app.auth.service import read_identity
from app.config import Settings
from app.database import Database, PlatformError
from app.diagnostics import DiagnosticBoundary, configure, span
from app.middleware import VisionRequestBoundary
from app.providers.client import ClientPool, lease
from app.request_lifetime import SessionRequestBoundary
from app.schemas import VisionRequest


def identity_rows(age=0):
    token = secret()
    user = User(id=uuid4(), email="test@example.com")
    session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        token_hash=digest(token),
        expires_at=now() + timedelta(hours=1),
        last_seen_at=now() - timedelta(seconds=age),
    )
    return token, session, user


def test_fresh_joined_authorization_has_no_read_lock_and_no_routine_write():
    token, session, user = identity_rows()
    calls = []

    async def execute(statement):
        calls.append(statement)
        return NS(one_or_none=lambda: (session, user))

    async def run():
        db = NS(execute=execute)
        assert await read_identity(db, token) is user
        assert await read_identity(db, token) is user
        session.revoked_at = now()
        with pytest.raises(PlatformError) as error:
            await read_identity(db, token)
        assert error.value.code == "session_revoked"

    asyncio.run(run())
    assert len(calls) == 3
    sql = str(calls[0].compile(dialect=postgresql.dialect())).lower()
    assert "join users" in sql and "for update" not in sql
    assert all(s.is_select and s.get_execution_options()["populate_existing"] for s in calls)


@pytest.mark.parametrize(
    "patch,code", [("expired", "session_expired"), ("missing", "invalid_session")]
)
def test_fresh_identity_expiry_and_missing_identity_fail_closed(patch, code):
    token, session, user = identity_rows()
    if patch == "expired":
        session.expires_at = now() - timedelta(seconds=1)

    async def execute(statement):
        return NS(one_or_none=lambda: None if patch == "missing" else (session, user))

    with pytest.raises(PlatformError) as error:
        asyncio.run(read_identity(NS(execute=execute), token))
    assert error.value.code == code


def test_last_seen_is_coarse_metadata_not_cached_authorization():
    token, session, user = identity_rows(120)
    calls = []

    async def execute(statement):
        calls.append(statement)
        return NS(one_or_none=lambda: (session, user))

    async def run():
        db = NS(execute=execute)
        await read_identity(db, token, touch=False)
        assert len(calls) == 1
        await read_identity(db, token)

    asyncio.run(run())
    assert len(calls) == 3 and calls[-1].is_update
    sql = str(calls[-1].compile(dialect=postgresql.dialect())).lower()
    assert "revoked_at is null" in sql and "last_seen_at <" in sql


@pytest.mark.parametrize(
    "failure",
    [
        DriverError("private connection secret"),
        OperationalError("private SQL", {}, Exception("private DSN")),
        OSError("private host"),
    ],
)
def test_database_connection_failure_classified_and_next_transaction_recovers(failure, caplog):
    db = Database(Settings(_env_file=None))
    events = []
    failures = [failure]

    class Session:
        @asynccontextmanager
        async def begin(self):
            try:
                yield
            finally:
                events.append("transaction_closed")

        async def execute(self, statement):
            if failures:
                raise failures.pop()

    @asynccontextmanager
    async def sessions():
        try:
            yield Session()
        finally:
            events.append("session_closed")

    db.sessions = sessions

    async def run():
        with pytest.raises(PlatformError) as error:
            async with db.transaction(timeout_seconds=0.2):
                pass
        assert error.value.code == "database_unavailable" and error.value.status == 503
        async with db.transaction(timeout_seconds=0.2):
            pass

    with caplog.at_level(logging.WARNING, logger="solveguide.diagnostics"):
        asyncio.run(run())
    assert events.count("session_closed") == 2 and events.count("transaction_closed") == 2
    assert "private" not in caplog.text


def test_slow_transaction_times_out_and_releases_session():
    db = Database(Settings(_env_file=None))
    events = []

    class Session:
        @asynccontextmanager
        async def begin(self):
            try:
                yield
            finally:
                events.append("rollback")

        async def execute(self, statement):
            await asyncio.Future()

    @asynccontextmanager
    async def sessions():
        try:
            yield Session()
        finally:
            events.append("closed")

    db.sessions = sessions

    async def run():
        with pytest.raises(PlatformError) as error:
            async with db.transaction(timeout_seconds=0.02):
                pass
        assert error.value.code == "database_timeout" and error.value.status == 504

    asyncio.run(run())
    assert events == ["rollback", "closed"]


def test_disconnect_cancels_provider_releases_admission_and_allows_next_request():
    async def run():
        started = asyncio.Event()
        closed = asyncio.Event()
        incoming = asyncio.Queue()
        sent = []
        calls = 0

        async def app(scope, receive, send):
            nonlocal calls
            await receive()
            calls += 1
            if calls == 1:
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    closed.set()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        boundary = VisionRequestBoundary(app)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/vision/question",
            "headers": [
                (b"origin", b"http://tauri.localhost"),
                (b"content-type", b"application/json"),
            ],
        }

        async def send(message):
            sent.append(message)

        await incoming.put({"type": "http.request", "body": b"{}"})
        first = asyncio.create_task(boundary(scope, incoming.get, send))
        await started.wait()
        await boundary(scope, incoming.get, send)
        assert sent[0]["status"] == 503 and calls == 1
        await incoming.put({"type": "http.disconnect"})
        await asyncio.wait_for(first, 0.5)
        assert closed.is_set() and not boundary.slot.locked()
        await incoming.put({"type": "http.request", "body": b"{}"})
        await boundary(scope, incoming.get, send)
        assert calls == 2 and sent[-2]["status"] == 200

    asyncio.run(run())


def test_session_deadline_classifies_and_cleans_up_instead_of_orphaning(monkeypatch, caplog):
    monkeypatch.setattr("app.request_lifetime.SESSION_VALIDATION_SECONDS", 0.03)
    cleaned = []

    @span("session_liveness")
    async def slow():
        try:
            await asyncio.Future()
        finally:
            cleaned.append(True)

    app = FastAPI()

    @app.post("/api/v1/learning/sessions/{identifier}/validate")
    async def route(identifier: str):
        await slow()

    app.add_middleware(SessionRequestBoundary)
    app.add_middleware(DiagnosticBoundary)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                f"/api/v1/learning/sessions/{uuid4()}/validate", json={"revision": 1}
            )

    configure("INFO", "PERFORMANCE")
    try:
        with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
            response = asyncio.run(run())
        assert response.status_code == 504 and cleaned == [True]
        assert response.headers["cache-control"] == "no-store"
        rows = [json.loads(r.message) for r in caplog.records if r.name == "solveguide.diagnostics"]
        failures = [r for r in rows if r["event"] == "session_validation_failure"]
        assert len(failures) == 1 and failures[0]["error_code"] == "session_validation_timeout"
    finally:
        configure("INFO")


def test_unexpected_session_bug_reports_safe_type_and_stage(caplog):
    app = FastAPI()

    @span("session_liveness")
    async def broken():
        raise TypeError("private database URL and question content")

    @app.post("/api/v1/learning/sessions/{identifier}/validate")
    async def route(identifier: str):
        await broken()

    app.add_middleware(DiagnosticBoundary)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(f"/api/v1/learning/sessions/{uuid4()}/validate", json={})

    configure("INFO", "PERFORMANCE")
    try:
        with caplog.at_level(logging.INFO, logger="solveguide.diagnostics"):
            assert asyncio.run(run()).status_code == 500
        rows = [json.loads(r.message) for r in caplog.records if r.name == "solveguide.diagnostics"]
        assert len(rows) == 1 and rows[0]["event"] == "session_validation_failure"
        assert rows[0]["stage"] == "session_liveness" and rows[0]["exception_kind"] == "type_error"
        assert "private" not in caplog.text
    finally:
        configure("INFO")


def test_shared_sdk_transport_reuses_pool_without_changing_request_options():
    from openai import AsyncOpenAI

    clients = []
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"object": "list", "data": []})

    def factory(**kwargs):
        client = AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        clients.append(client)
        return client

    async def run():
        pool = ClientPool()

        async def request(request_seconds):
            async with lease(
                pool,
                factory,
                api_key="fake-key",
                base_url="https://api.openai.com/v1",
                timeout=httpx.Timeout(request_seconds, connect=5),
                max_retries=0,
            ) as client:
                assert client.max_retries == 0 and client.timeout.read == request_seconds
                await client.models.list()

        await asyncio.gather(*(request(timeout) for timeout in [45, 60, 25]))
        assert len(clients) == 1 and not clients[0].is_closed()
        await pool.close()
        assert clients[0].is_closed()

    asyncio.run(run())
    assert len(requests) == 3  # Mock transport only; no extra health/provider request.


def test_shared_sdk_transport_survives_cancelled_request():
    from openai import AsyncOpenAI

    async def run():
        started = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(True)
            if len(calls) == 1:
                started.set()
                await asyncio.Future()
            return httpx.Response(200, json={"object": "list", "data": []})

        def factory(**options):
            return AsyncOpenAI(
                **options, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
            )

        pool = ClientPool()

        async def request():
            async with lease(
                pool,
                factory,
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                timeout=httpx.Timeout(1, connect=1),
                max_retries=0,
            ) as client:
                return await client.models.list()

        task = asyncio.create_task(request())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await request()).data == [] and len(calls) == 2
        await pool.close()

    asyncio.run(run())


def test_session_bound_vision_checks_authority_before_provider(access, image_payload):
    client, token, session, vision, _ = access
    client.app.state.learning_service.liveness = AsyncMock(
        side_effect=PlatformError("session_revision_mismatch", "Changed", 409)
    )
    payload = {**image_payload, "session_id": str(uuid4()), "session_revision": 1}
    response = client.post(
        "/api/v1/vision/question", json=payload, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 409
    vision.observe.assert_not_awaited()
    with pytest.raises(ValueError):
        VisionRequest.model_validate({**image_payload, "session_revision": 1})


@pytest.mark.parametrize(
    "change,status", [("none", 200), ("revoked", 401), ("ended", 409), ("revision", 409)]
)
def test_session_answer_postflight_is_fresh_in_same_config_transaction(
    access, observation_data, answer_data, change, status
):
    from app.answer.schemas import AnswerRecommendation
    from app.learning.models import LearningSession
    from app.learning.service import SessionService

    client, token, credential, _, answer = access
    row = LearningSession(
        id=uuid4(),
        owner_id=credential.user_id,
        revision=1,
        status="active",
        purpose="general_learning",
        objective="Learn",
        mode="general",
        selected_count=0,
        allow_context_transmission=False,
    )
    reads = []
    link_reads = []
    database = client.app.state.database

    class Repository:
        @asynccontextmanager
        async def reading(self, owner):
            assert owner == row.owner_id
            async with database.transaction() as db:
                reads.append(True)

                async def get(identifier):
                    return row if identifier == row.id else None

                async def links(value):
                    link_reads.append(True)
                    return []

                yield NS(db=db, get=get, links=links)

    client.app.state.learning_service = SessionService(Repository())

    async def recommend(*args, **kwargs):
        if change == "revoked":
            credential.revoked_at = now()
        if change == "ended":
            row.status = "ended"
        if change == "revision":
            row.revision += 1
        return AnswerRecommendation.model_validate(answer_data)

    answer.recommend = AsyncMock(side_effect=recommend)
    response = client.post(
        "/api/v1/answer",
        json={"observation": observation_data, "session_id": str(row.id), "session_revision": 1},
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == status and answer.recommend.await_count == 1
    assert len(reads) == 2 and link_reads == []
    if status != 200:
        assert "answer_text" not in response.json()
