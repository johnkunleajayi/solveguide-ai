import asyncio
import copy
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.auth.google import GoogleIdentity, validate_identity
from app.auth.models import AuthSession, OAuthAttempt, User
from app.auth.security import digest, now, secret
from app.auth.service import current_session, issue_session, upsert_user
from app.config import Settings
from app.database import Base, Database, PlatformError, database_url
from app.main import create_app

ORIGIN = {"Origin": "http://tauri.localhost"}
IDENTITY = GoogleIdentity(
    subject="google-subject-1",
    email=" Learner@Example.com ",
    email_verified=True,
    display_name="Learner",
)


class MemorySession:
    """Service boundary fake, not a claim of PostgreSQL isolation/constraint verification."""

    def __init__(self, rows):
        self.rows = rows

    def add(self, obj):
        self.rows[type(obj)].append(obj)

    async def flush(self):
        for objects in self.rows.values():
            for obj in objects:
                if obj.id is None:
                    obj.id = uuid4()
                if isinstance(obj, User):
                    obj.created_at = obj.updated_at = now()

    async def get(self, model, identifier):
        return next((row for row in self.rows[model] if row.id == identifier), None)

    async def scalar(self, statement):
        model = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        return next(
            (
                row
                for row in self.rows[model]
                if all(
                    getattr(row, key.rsplit("_", 1)[0]) == value for key, value in params.items()
                )
            ),
            None,
        )

    async def execute(self, statement):
        if statement.is_delete:
            self.rows[OAuthAttempt][:] = [
                row for row in self.rows[OAuthAttempt] if row.expires_at >= now()
            ]
            return None
        params = statement.compile(dialect=postgresql.dialect()).params
        values = {
            k: params[k]
            for k in (
                "google_subject",
                "email",
                "email_verified",
                "display_name",
                "avatar_url",
                "last_login_at",
            )
        }
        user = next(
            (u for u in self.rows[User] if u.google_subject == values["google_subject"]), None
        )
        if user is None:
            user = User(**values)
            self.add(user)
        else:
            for key, value in values.items():
                setattr(user, key, value)
        await self.flush()

        class Result:
            def scalar_one(self):
                return user

        return Result()


class MemoryDatabase:
    def __init__(self):
        self.rows = {User: [], AuthSession: [], OAuthAttempt: []}
        self.rollbacks = 0

    @asynccontextmanager
    async def transaction(self):
        snapshot = copy.deepcopy(self.rows)
        try:
            yield MemorySession(self.rows)
        except Exception:
            self.rows = snapshot
            self.rollbacks += 1
            raise


@pytest.fixture
def platform():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://test:test@localhost/test",
        google_client_id="test-client",
        google_client_secret="test-secret",
        auth_state_encryption_key=Fernet.generate_key().decode(),
    )
    app = create_app(settings)
    database = MemoryDatabase()
    app.state.database = database
    app.state.google_provider = AsyncMock()
    app.state.google_provider.identity.return_value = IDENTITY
    return TestClient(app, base_url="http://127.0.0.1"), app, database, settings


def begin(client):
    response = client.post("/api/v1/auth/desktop/start", json={}, headers=ORIGIN)
    assert response.status_code == 200
    data = response.json()
    query = parse_qs(urlsplit(data["authorization_url"]).query)
    return data["exchange_secret"], query


def complete(client, query, **extra):
    return client.get(
        "/api/v1/auth/google/callback",
        params={"state": query["state"][0], "code": "mock-code", **extra},
    )


def exchange(client, binding):
    return client.post("/api/v1/auth/desktop/exchange", json={"secret": binding}, headers=ORIGIN)


def test_start_pkce_nonce_hashes_encryption_and_no_session_url(platform):
    client, _, database, settings = platform
    binding, query = begin(client)
    attempt = database.rows[OAuthAttempt][0]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [settings.google_redirect_uri]
    assert query["nonce"] == [attempt.nonce]
    assert attempt.state_hash == digest(query["state"][0])
    assert attempt.binding_hash == digest(binding)
    assert binding not in str(query)
    assert "code_verifier" not in query
    assert Fernet(settings.auth_state_encryption_key.get_secret_value().encode()).decrypt(
        attempt.verifier_encrypted.encode()
    )
    assert exchange(client, binding).json() == {"status": "pending", "session_token": None}


def test_desktop_callback_exchange_current_user_logout_and_replay(platform):
    client, app, database, _ = platform
    binding, query = begin(client)
    assert complete(client, query).status_code == 200
    assert complete(client, query).status_code == 400
    token = exchange(client, binding).json()["session_token"]
    assert exchange(client, binding).status_code == 400
    assert database.rows[AuthSession][0].token_hash == digest(token)
    headers = {**ORIGIN, "Authorization": "Bearer " + token}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.json()["email"] == "learner@example.com"
    assert set(response.json()) == {"id", "email", "email_verified", "display_name", "avatar_url"}
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 204
    assert (
        client.get("/api/v1/auth/me", headers=headers).json()["error"]["code"] == "session_revoked"
    )
    assert app.state.google_provider.identity.call_count == 1


def test_existing_subject_updates_user_without_email_linking(platform):
    client, _, database, _ = platform
    for _ in range(2):
        binding, query = begin(client)
        assert complete(client, query).status_code == 200
        assert exchange(client, binding).status_code == 200
    assert len(database.rows[User]) == 1
    assert len(database.rows[AuthSession]) == 2


@pytest.mark.parametrize(
    "failure", ["invalid", "expired", "denied", "missing_code", "provider", "unverified"]
)
def test_failed_callback_never_creates_session(platform, failure):
    client, app, database, _ = platform
    binding, query = begin(client)
    params = {"state": query["state"][0], "code": "mock-code"}
    if failure == "invalid":
        params["state"] = secret()
    elif failure == "expired":
        database.rows[OAuthAttempt][0].expires_at = now() - timedelta(seconds=1)
    elif failure == "denied":
        params["error"] = "access_denied"
    elif failure == "missing_code":
        del params["code"]
    elif failure == "provider":
        app.state.google_provider.identity.side_effect = RuntimeError(
            "sensitive provider exception"
        )
    elif failure == "unverified":
        app.state.google_provider.identity.return_value = IDENTITY.model_copy(
            update={"email_verified": False}
        )
    response = client.get("/api/v1/auth/google/callback", params=params)
    assert response.status_code == 400
    assert not database.rows[AuthSession]
    assert "sensitive" not in response.text
    if failure not in ("invalid", "expired"):
        assert exchange(client, binding).status_code == 401
        assert complete(client, query).status_code == 400


def test_web_browser_binding_cookie_and_same_shared_user(platform):
    client, _, database, _ = platform
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 303
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert complete(client, query).status_code == 200
    assert client.get("/api/v1/auth/me").json()["display_name"] == "Learner"
    assert len(database.rows[User]) == 1
    assert client.post("/api/v1/auth/logout", json={}, headers=ORIGIN).status_code == 204
    assert client.get("/api/v1/auth/me").json() is None


def test_web_callback_rejects_different_browser(platform):
    client, _, database, _ = platform
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    client.cookies.clear()
    assert complete(client, query).status_code == 400
    assert not database.rows[User]


def test_no_session_and_expired_and_invalid_session(platform):
    client, _, database, _ = platform
    assert client.get("/api/v1/auth/me").json() is None
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    binding, query = begin(client)
    complete(client, query)
    token = exchange(client, binding).json()["session_token"]
    database.rows[AuthSession][0].expires_at = now() - timedelta(seconds=1)
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.json()["error"]["code"] == "session_expired"


def test_missing_config_safe_health_and_csrf(platform):
    client = TestClient(create_app(Settings(_env_file=None)), base_url="http://127.0.0.1")
    response = client.post("/api/v1/auth/desktop/start", json={}, headers=ORIGIN)
    assert response.json()["error"]["code"] == "database_not_configured"
    assert client.get("/api/health").json()["database"] == {"configured": False}
    client, app, _, settings = platform
    app.state.settings = settings.model_copy(update={"google_client_id": ""})
    assert (
        client.post("/api/v1/auth/desktop/start", json={}, headers=ORIGIN).json()["error"]["code"]
        == "auth_not_configured"
    )
    assert client.post("/api/v1/auth/logout", json={}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", json={}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/desktop/exchange",
            content=b"x" * 4097,
            headers={**ORIGIN, "Content-Type": "application/json"},
        ).status_code
        == 413
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"aud": "wrong"},
        {"iss": "https://evil.test"},
        {"exp": 1},
        {"nonce": "wrong"},
        {"email_verified": False},
        {"sub": ""},
    ],
)
def test_signed_google_identity_rejects_invalid_claims(platform, patch):
    _, _, _, settings = platform
    key = RSAKey.generate_key(2048)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client",
        "exp": int(now().timestamp()) + 300,
        "iat": int(now().timestamp()),
        "sub": "google1",
        "nonce": "expected",
        "email": "test@example.com",
        "email_verified": True,
    }
    claims.update(patch)
    token = jwt.encode({"alg": "RS256"}, claims, key)
    with pytest.raises((ValueError, JoseError)):
        validate_identity(
            token, {"keys": [key.as_dict(private=False)]}, settings, "expected", "access-token"
        )


def test_valid_signed_identity_and_wrong_signing_key(platform):
    _, _, _, settings = platform
    key = RSAKey.generate_key(2048)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client",
        "exp": int(now().timestamp()) + 300,
        "iat": int(now().timestamp()),
        "sub": "google1",
        "nonce": "expected",
        "email": "test@example.com",
        "email_verified": True,
    }
    token = jwt.encode({"alg": "RS256"}, claims, key)
    assert (
        validate_identity(
            token, {"keys": [key.as_dict(private=False)]}, settings, "expected", "access-token"
        ).subject
        == "google1"
    )
    with pytest.raises((ValueError, JoseError)):
        validate_identity(
            token,
            {"keys": [RSAKey.generate_key(2048).as_dict(private=False)]},
            settings,
            "expected",
            "access-token",
        )


def test_postgres_constraints_metadata_and_url(platform):
    _, _, _, settings = platform
    assert database_url(settings).drivername == "postgresql+psycopg"
    ddl = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in Base.metadata.sorted_tables
    )
    for sql in (
        "UUID",
        "TIMESTAMP WITH TIME ZONE",
        "UNIQUE (google_subject)",
        "UNIQUE (token_hash)",
        "ON DELETE CASCADE",
        "email = lower(trim(email))",
    ):
        assert sql in ddl
    assert set(Base.metadata.tables) == {
        "users",
        "auth_sessions",
        "oauth_attempts",
        "context_documents",
        "context_indexes",
        "context_chunks",
    }
    user = User(email=" Mixed@Example.COM ")
    assert user.email == "mixed@example.com"


def test_transaction_rollback_and_session_creation_lookup(platform):
    _, _, database, settings = platform

    async def run():
        async with database.transaction() as db:
            user = await upsert_user(db, IDENTITY)
            token = await issue_session(db, user.id, settings)
            session = await current_session(db, token)
            assert session.user_id == user.id and session.token_hash != token
        with pytest.raises(RuntimeError):
            async with database.transaction() as db:
                db.add(User(email="rollback@example.com"))
                raise RuntimeError
        assert len(database.rows[User]) == 1 and database.rollbacks == 1

    asyncio.run(run())


def test_database_missing_and_configuration_validation():
    async def run():
        with pytest.raises(PlatformError):
            async with Database(Settings(_env_file=None)).transaction():
                pass

    asyncio.run(run())
    for config in (
        {"database_url": "sqlite:///bad"},
        {"auth_public_base_url": "http://evil.test"},
        {"auth_public_base_url": "https://app.example.com"},
        {"auth_state_encryption_key": "bad"},
    ):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **config)


def test_cancel_invalidates_attempt_and_callback(platform):
    client, _, database, _ = platform
    binding, query = begin(client)
    response = client.post("/api/v1/auth/desktop/cancel", json={"secret": binding}, headers=ORIGIN)
    assert response.status_code == 204
    assert complete(client, query).status_code == 400
    assert exchange(client, binding).status_code == 401
    assert not database.rows[User]


def test_malformed_callback_and_invalid_exchange_never_call_google(platform):
    client, app, _, _ = platform
    assert client.get("/api/v1/auth/google/callback").status_code == 422
    assert client.get("/api/v1/auth/google/callback", params={"state": "bad"}).status_code == 422
    assert exchange(client, secret()).status_code == 400
    assert app.state.google_provider.identity.call_count == 0


def test_required_and_optional_current_user_share_sessions(platform):
    from typing import Annotated

    from fastapi import Depends

    from app.auth.dependencies import required_current_user

    client, app, _, _ = platform

    @app.get("/protected-test")
    async def protected(user: Annotated[User, Depends(required_current_user)]):
        return {"id": str(user.id)}

    assert client.get("/protected-test").status_code == 401
    binding, query = begin(client)
    complete(client, query)
    token = exchange(client, binding).json()["session_token"]
    assert (
        client.get("/protected-test", headers={"Authorization": "Bearer " + token}).status_code
        == 200
    )


def test_actual_database_context_rolls_back_and_sanitizes_failures():
    from sqlalchemy.exc import OperationalError, ProgrammingError

    class Sessions:
        def __init__(self):
            self.closed = self.rolled_back = 0
            self.failure = RuntimeError("business failure")

        async def execute(self, statement):
            assert str(statement) == "SET LOCAL statement_timeout = '10s'"

        @asynccontextmanager
        async def __call__(self):
            try:
                yield self
            finally:
                self.closed += 1

        @asynccontextmanager
        async def begin(self):
            try:
                yield
            except Exception:
                self.rolled_back += 1
                raise

    async def run():
        database = Database(Settings(_env_file=None))
        sessions = Sessions()
        database.sessions = sessions
        with pytest.raises(RuntimeError):
            async with database.transaction():
                raise RuntimeError("business failure")
        assert sessions.closed == sessions.rolled_back == 1
        for exception, code in (
            (OperationalError("hidden", {}, Exception("password-secret")), "database_unavailable"),
            (
                ProgrammingError(
                    "hidden", {}, type("SchemaError", (Exception,), {"sqlstate": "42P01"})()
                ),
                "database_schema",
            ),
        ):
            with pytest.raises(PlatformError) as caught:
                async with database.transaction():
                    raise exception
            assert caught.value.code == code
            assert "password-secret" not in caught.value.message

    asyncio.run(run())


def test_production_cookie_flags_and_auth_only_credential_cors(platform):
    client, app, _, settings = platform
    app.state.settings = settings.model_copy(update={"auth_cookie_secure": True})
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    cors = client.options(
        "/api/v1/auth/logout", headers={**ORIGIN, "Access-Control-Request-Method": "POST"}
    )
    assert cors.headers["access-control-allow-credentials"] == "true"
    assert cors.headers["access-control-allow-origin"] == ORIGIN["Origin"]
    bad = client.options(
        "/api/v1/auth/logout",
        headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_blank_example_config_keeps_platform_optional():
    settings = Settings(
        _env_file=None,
        database_url="",
        google_client_id="",
        google_client_secret="",
        auth_state_encryption_key="",
    )
    assert not settings.auth_configured and not settings.database_configured
