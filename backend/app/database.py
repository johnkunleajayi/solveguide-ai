import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import MetaData, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings
from app.diagnostics import category, emit


class PlatformError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        self.code, self.message, self.status = code, message, status


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def database_url(settings: Settings):
    if not settings.database_configured:
        raise PlatformError("database_not_configured", "Configure DATABASE_URL in backend/.env.")
    return make_url(settings.database_url.get_secret_value()).set(drivername="postgresql+psycopg")


class Database:
    def __init__(self, settings: Settings):
        self.engine = None
        self.sessions = None
        if settings.database_configured:
            self.engine = create_async_engine(
                database_url(settings),
                pool_pre_ping=True,
                pool_size=3,
                max_overflow=2,
                pool_timeout=5,
                hide_parameters=True,
                connect_args={"connect_timeout": 5},
            )
            self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        if not self.sessions:
            raise PlatformError(
                "database_not_configured", "Configure DATABASE_URL in backend/.env."
            )
        started = time.monotonic()
        try:
            async with self.sessions() as session, session.begin():
                # Poolers may reject startup options. Keep the timeout transaction-local
                # so it also resets before a pooled connection is reused.
                await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                yield session
        except SQLAlchemyError as error:
            code = getattr(getattr(error, "orig", None), "sqlstate", None)
            safe_code = (
                code.lower()
                if isinstance(code, str) and len(code) == 5 and code.isalnum()
                else None
            )
            kind = "database_schema" if code in ("42P01", "42703") else "database_unavailable"
            reason = (
                "database_statement_timeout"
                if code == "57014"
                else "database_deadlock"
                if code == "40P01"
                else "database_lock_unavailable"
                if code == "55P03"
                else "database_pool_timeout"
                if type(error).__name__ == "TimeoutError"
                else "database_operation_failed"
            )
            emit(
                "database_failure",
                reason=reason,
                level=logging.WARNING,
                error_code=kind,
                error_category=category(kind),
                sqlstate=safe_code,
            )
            if code in ("42P01", "42703"):
                raise PlatformError(
                    "database_schema", "Apply the Alembic migrations before signing in."
                ) from None
            raise PlatformError(
                "database_unavailable", "The authentication database is unavailable."
            ) from None

        finally:
            emit(
                "database_transaction",
                level=logging.DEBUG,
                duration_ms=round((time.monotonic() - started) * 1000),
            )

    async def close(self):
        if self.engine:
            await self.engine.dispose()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.transaction() as session:
        yield session
