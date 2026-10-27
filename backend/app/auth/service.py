import base64
import hashlib
import hmac
from datetime import timedelta

from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.google import GoogleIdentity, authorization_url
from app.auth.models import AuthSession, OAuthAttempt, User
from app.auth.security import digest, now, secret
from app.config import Settings
from app.database import PlatformError


def require_config(settings: Settings):
    if not settings.database_configured:
        raise PlatformError("database_not_configured", "Configure DATABASE_URL in backend/.env.")
    if not settings.auth_configured:
        raise PlatformError("auth_not_configured", "Configure Google sign-in in backend/.env.")


async def start(db: AsyncSession, settings: Settings, transport: str):
    require_config(settings)
    # Bound retention of temporary secrets; never delete user/session history implicitly.
    await db.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at < now()))
    state, binding, verifier, nonce = secret(), secret(), secret(), secret()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    attempt = OAuthAttempt(
        state_hash=digest(state),
        binding_hash=digest(binding),
        verifier_encrypted=Fernet(settings.auth_state_encryption_key.get_secret_value().encode())
        .encrypt(verifier.encode())
        .decode(),
        nonce=nonce,
        transport=transport,
        status="pending",
        created_at=now(),
        expires_at=now() + timedelta(minutes=10),
    )
    db.add(attempt)
    await db.flush()
    return authorization_url(settings, state, nonce, challenge), binding


async def upsert_user(db: AsyncSession, identity: GoogleIdentity) -> User:
    if not identity.email_verified:
        raise PlatformError("email_unverified", "A verified Google email is required.", 401)
    values = dict(
        google_subject=identity.subject,
        email=identity.email.strip().lower(),
        email_verified=True,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        last_login_at=now(),
    )
    # Atomic identity-key upsert handles simultaneous callbacks; email never links accounts.
    statement = insert(User).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[User.google_subject],
        set_={k: v for k, v in values.items() if k != "google_subject"} | {"updated_at": now()},
    ).returning(User)
    return (await db.execute(statement)).scalar_one()


async def issue_session(db: AsyncSession, user_id, settings: Settings):
    token = secret()
    session = AuthSession(
        user_id=user_id,
        token_hash=digest(token),
        created_at=now(),
        expires_at=now() + timedelta(hours=settings.auth_session_hours),
        last_seen_at=now(),
    )
    db.add(session)
    await db.flush()
    return token


def validate_session(session: AuthSession, token: str):
    if not hmac.compare_digest(session.token_hash, digest(token)):
        raise PlatformError("invalid_session", "Please sign in again.", 401)
    if session.revoked_at is not None:
        raise PlatformError("session_revoked", "This session was signed out. Sign in again.", 401)
    if session.expires_at <= now():
        raise PlatformError("session_expired", "Your session expired. Sign in again.", 401)


async def current_session(db: AsyncSession, token: str):
    if len(token) != 43:
        raise PlatformError("invalid_session", "Please sign in again.", 401)
    session = await db.scalar(
        select(AuthSession).where(AuthSession.token_hash == digest(token)).with_for_update()
    )
    if session is None:
        raise PlatformError("invalid_session", "Please sign in again.", 401)
    validate_session(session, token)
    session.last_seen_at = now()
    return session


async def consume_attempt(db: AsyncSession, state: str, binding: str | None = None):
    attempt = await db.scalar(
        select(OAuthAttempt).where(OAuthAttempt.state_hash == digest(state)).with_for_update()
    )
    if attempt is None or attempt.expires_at <= now() or attempt.status != "pending":
        raise PlatformError(
            "invalid_oauth_state", "Sign-in expired or was already used. Start again.", 400
        )
    if attempt.transport == "web" and (
        not binding or not hmac.compare_digest(attempt.binding_hash, digest(binding))
    ):
        raise PlatformError("invalid_oauth_state", "Use the browser that started sign-in.", 400)
    attempt.status = "processing"
    return attempt


async def exchange(db: AsyncSession, binding: str, settings: Settings):
    attempt = await db.scalar(
        select(OAuthAttempt)
        .where(OAuthAttempt.binding_hash == digest(binding), OAuthAttempt.transport == "desktop")
        .with_for_update()
    )
    if attempt is None or attempt.expires_at <= now() or attempt.status == "consumed":
        raise PlatformError("invalid_exchange", "Desktop sign-in expired. Start again.", 400)
    if attempt.status == "failed":
        raise PlatformError(
            "google_sign_in_failed",
            "Google sign-in was cancelled or could not be verified. Start again.",
            401,
        )
    if attempt.status != "ready":
        return None
    attempt.status = "consumed"
    attempt.verifier_encrypted = ""
    return await issue_session(db, attempt.user_id, settings)
