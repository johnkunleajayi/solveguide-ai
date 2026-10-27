from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import current_session
from app.database import PlatformError, get_db

SESSION_COOKIE = "solveguide_session"
STATE_COOKIE = "solveguide_oauth"


def credential(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth:
        if not auth.startswith("Bearer "):
            raise PlatformError("invalid_session", "Please sign in again.", 401)
        return auth[7:]
    return request.cookies.get(SESSION_COOKIE)


async def optional_current_user(request: Request) -> User | None:
    token = credential(request)
    if not token:
        return None
    async with request.app.state.database.transaction() as db:
        session = await current_session(db, token)
        user = await db.get(User, session.user_id)
        if user is None:
            raise PlatformError("invalid_session", "Please sign in again.", 401)
        return user


async def required_current_user(
    user: Annotated[User | None, Depends(optional_current_user)],
) -> User:
    if user is None:
        raise PlatformError("sign_in_required", "Sign in to continue.", 401)
    return user


# Re-export the transaction dependency for future user-owned services.
DatabaseSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
