from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from test_auth import MemoryDatabase

from app.answer.schemas import AnswerRecommendation
from app.auth.models import AuthSession, User
from app.auth.security import digest, now, secret
from app.config import Settings
from app.database import PlatformError
from app.main import create_app
from app.schemas import QuestionObservation

ORIGIN = {"Origin": "http://tauri.localhost"}


@pytest.fixture
def access(observation_data, answer_data):
    vision = type(
        "Vision",
        (),
        {"observe": AsyncMock(return_value=QuestionObservation.model_validate(observation_data))},
    )()
    answer = type(
        "Answer",
        (),
        {"recommend": AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))},
    )()
    app = create_app(Settings(_env_file=None), vision, answer)
    database = MemoryDatabase()
    app.state.database = database
    token = secret()
    from uuid import uuid4

    user = User(
        id=uuid4(),
        google_subject="access-subject",
        email="test@example.com",
        email_verified=True,
        display_name="Test",
        avatar_url=None,
    )
    session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        token_hash=digest(token),
        created_at=now(),
        expires_at=now() + timedelta(hours=1),
        last_seen_at=now(),
        revoked_at=None,
    )
    database.rows[User].append(user)
    database.rows[AuthSession].append(session)
    return (
        TestClient(app, base_url="http://127.0.0.1", headers=ORIGIN),
        token,
        session,
        vision,
        answer,
    )


@pytest.mark.parametrize("route", ["vision", "answer"])
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired", "revoked"])
def test_providers_never_run_without_valid_session(
    access, image_payload, observation_data, route, credential
):
    client, token, session, vision, answer = access
    headers = {}
    if credential != "missing":
        headers["Authorization"] = "Bearer " + (secret() if credential == "invalid" else token)
    if credential == "expired":
        session.expires_at = now() - timedelta(seconds=1)
    if credential == "revoked":
        session.revoked_at = now()
    path, payload = (
        ("/api/v1/vision/question", image_payload)
        if route == "vision"
        else ("/api/v1/answer", observation_data)
    )
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] in (
        "sign_in_required",
        "invalid_session",
        "session_expired",
        "session_revoked",
    )
    vision.observe.assert_not_awaited()
    answer.recommend.assert_not_awaited()


def test_valid_session_preserves_both_pipelines_and_logout_ends_access(
    access, image_payload, observation_data
):
    client, token, _, vision, answer = access
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert (
        client.post("/api/v1/vision/question", json=image_payload, headers=headers).status_code
        == 200
    )
    assert client.post("/api/v1/answer", json=observation_data, headers=headers).status_code == 200
    vision.observe.assert_awaited_once()
    answer.recommend.assert_awaited_once()
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 204
    for path, payload in [
        ("/api/v1/vision/question", image_payload),
        ("/api/v1/answer", observation_data),
    ]:
        assert client.post(path, json=payload, headers=headers).status_code == 401
        assert client.post(path, json=payload).status_code == 401
    vision.observe.assert_awaited_once()
    answer.recommend.assert_awaited_once()
    assert client.get("/api/health").status_code == 200


def test_database_outage_fails_closed_before_providers(access, image_payload):
    client, token, _, vision, answer = access
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def unavailable():
        raise PlatformError("database_unavailable", "Database unavailable.")
        yield

    client.app.state.database.transaction = unavailable
    response = client.post(
        "/api/v1/vision/question", json=image_payload, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 503
    vision.observe.assert_not_awaited()
    answer.recommend.assert_not_awaited()
