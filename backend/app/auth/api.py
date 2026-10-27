from typing import Annotated

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from starlette.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import SESSION_COOKIE, STATE_COOKIE, credential, optional_current_user
from app.auth.models import OAuthAttempt, User
from app.auth.schemas import ExchangeRequest, PublicUser
from app.auth.security import now
from app.auth.service import (
    consume_attempt,
    current_session,
    exchange,
    issue_session,
    require_config,
    start,
    upsert_user,
)
from app.database import PlatformError

router = APIRouter(prefix="/api/v1/auth")


def cookie(response: Response, request: Request, name: str, value: str, seconds: int):
    response.set_cookie(
        name,
        value,
        max_age=seconds,
        httponly=True,
        secure=request.app.state.settings.auth_cookie_secure,
        samesite="lax",
        path="/api" if name == SESSION_COOKIE else "/api/v1/auth",
    )


@router.post("/desktop/start")
async def desktop_start(request: Request):
    require_config(request.app.state.settings)
    async with request.app.state.database.transaction() as db:
        url, binding = await start(db, request.app.state.settings, "desktop")
    return {"authorization_url": url, "exchange_secret": binding, "expires_in": 600}


@router.get("/google/start")
async def web_start(request: Request):
    require_config(request.app.state.settings)
    async with request.app.state.database.transaction() as db:
        url, binding = await start(db, request.app.state.settings, "web")
    response = RedirectResponse(url, status_code=303)
    cookie(response, request, STATE_COOKIE, binding, 600)
    return response


@router.get("/google/callback")
async def callback(
    request: Request,
    state: Annotated[str, Query(min_length=43, max_length=100)],
    code: Annotated[str | None, Query(max_length=4096)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
):
    settings = request.app.state.settings
    require_config(settings)
    # Claim/commit before provider I/O: callbacks cannot replay even after a provider failure.
    async with request.app.state.database.transaction() as db:
        attempt = await consume_attempt(db, state, request.cookies.get(STATE_COOKIE))
        attempt_id, nonce, encrypted, transport = (
            attempt.id,
            attempt.nonce,
            attempt.verifier_encrypted,
            attempt.transport,
        )
    token = None
    successful = False
    try:
        if error or not code:
            raise PlatformError("google_denied", "Google sign-in was cancelled.", 400)
        verifier = (
            Fernet(settings.auth_state_encryption_key.get_secret_value().encode())
            .decrypt(encrypted.encode(), ttl=600)
            .decode()
        )
        identity = await request.app.state.google_provider.identity(code, verifier, nonce)
        async with request.app.state.database.transaction() as db:
            user = await upsert_user(db, identity)
            attempt = await db.scalar(
                select(OAuthAttempt).where(OAuthAttempt.id == attempt_id).with_for_update()
            )
            if not attempt or attempt.status != "processing" or attempt.expires_at <= now():
                raise PlatformError("invalid_oauth_state", "Sign-in was cancelled or expired.", 400)
            attempt.user_id, attempt.verifier_encrypted, attempt.status = user.id, "", "ready"
            if transport == "web":
                token = await issue_session(db, user.id, settings)
                attempt.status = "consumed"
        successful = True
    except Exception:
        async with request.app.state.database.transaction() as db:
            attempt = await db.get(OAuthAttempt, attempt_id)
            if attempt:
                attempt.status, attempt.verifier_encrypted = "failed", ""
    message = (
        "Sign-in complete. Return to SolveGuide."
        if successful
        else "Sign-in could not be completed. Return to SolveGuide and start again."
    )
    response = HTMLResponse(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'>"
        "<title>SolveGuide sign-in</title><body><h1>SolveGuide AI</h1><p>"
        + message
        + "</p></body></html>",
        status_code=200 if successful else 400,
        headers={
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
        },
    )
    response.delete_cookie(STATE_COOKIE, path="/api/v1/auth")
    if token:
        cookie(response, request, SESSION_COOKIE, token, settings.auth_session_hours * 3600)
    return response


@router.post("/desktop/exchange")
async def desktop_exchange(payload: ExchangeRequest, request: Request):
    async with request.app.state.database.transaction() as db:
        token = await exchange(db, payload.secret, request.app.state.settings)
    return {"status": "ready" if token else "pending", "session_token": token}


@router.get("/me", response_model=PublicUser | None)
async def me(user: Annotated[User | None, Depends(optional_current_user)]):
    return PublicUser.model_validate(user) if user else None


@router.post("/desktop/cancel", status_code=204)
async def desktop_cancel(payload: ExchangeRequest, request: Request):
    from app.auth.security import digest

    async with request.app.state.database.transaction() as db:
        attempt = await db.scalar(
            select(OAuthAttempt)
            .where(
                OAuthAttempt.binding_hash == digest(payload.secret),
                OAuthAttempt.transport == "desktop",
            )
            .with_for_update()
        )
        if attempt and attempt.status != "consumed":
            attempt.status, attempt.verifier_encrypted = "failed", ""
    return Response(status_code=204)


@router.post("/logout", status_code=204)
async def logout(request: Request):
    token = credential(request)
    if token:
        try:
            async with request.app.state.database.transaction() as db:
                session = await current_session(db, token)
                session.revoked_at = now()
        except PlatformError as failure:
            if failure.status != 401:
                raise
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/api")
    return response
