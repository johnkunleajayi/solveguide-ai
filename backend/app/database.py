import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import Request
from psycopg import Error as DriverError
from sqlalchemy import MetaData, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings
from app.diagnostics import category, context, emit, performance_enabled
from app.performance import Timing, operation

query_counts: ContextVar[dict | None] = ContextVar("performance_queries", default=None)


def before_query(_connection, _cursor, _statement, _parameters, execution, _many):
    if not performance_enabled():
        return
    execution._solveguide_timing = Timing(
        "database_query", role=operation.get() or "request", bind_parent=False
    ).__enter__()
    execution._solveguide_counts = query_counts.get()
    current = context.get()
    if current:
        current.database_queries += 1


def finish_query(execution, error=None):
    timer = getattr(execution, "_solveguide_timing", None)
    if timer is not None:
        execution._solveguide_timing = None
        counts = execution._solveguide_counts
        if counts is not None:
            counts["count"] += 1
            counts["ms"] += max(0, round((timer.clock() - timer.start) * 1000))
        timer.__exit__(type(error) if error else None, error, None)


def after_query(_connection, _cursor, _statement, _parameters, execution, _many):
    finish_query(execution)


def query_error(error_context):
    if error_context.execution_context is not None:
        finish_query(error_context.execution_context, error_context.original_exception)


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
            event.listen(self.engine.sync_engine, "before_cursor_execute", before_query)
            event.listen(self.engine.sync_engine, "after_cursor_execute", after_query)
            event.listen(self.engine.sync_engine, "handle_error", query_error)

    @asynccontextmanager
    async def transaction(self, *, timeout_seconds=None) -> AsyncIterator[AsyncSession]:
        if not self.sessions:
            raise PlatformError(
                "database_not_configured", "Configure DATABASE_URL in backend/.env."
            )
        started = time.monotonic()
        counts = {"count": 0, "ms": 0}
        counts_token = query_counts.set(counts)
        current = context.get()
        if current and performance_enabled():
            current.database_transactions += 1
        try:
            async with (
                asyncio.timeout(timeout_seconds),
                self.sessions() as session,
                session.begin(),
            ):
                # Poolers may reject startup options. Keep the timeout transaction-local
                # so it also resets before a pooled connection is reused.
                with Timing("database_setup"):
                    await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                yield session
        except (SQLAlchemyError, DriverError, OSError, TimeoutError) as error:
            code = getattr(getattr(error, "orig", error), "sqlstate", None)
            safe_code = (
                code.lower()
                if isinstance(code, str) and len(code) == 5 and code.isalnum()
                else None
            )
            timed_out = isinstance(error, TimeoutError) or code == "57014"
            kind = (
                "database_schema"
                if code in ("42P01", "42703")
                else "database_timeout"
                if timed_out
                else "database_unavailable"
            )
            reason = (
                "database_transaction_timeout"
                if isinstance(error, TimeoutError)
                else "database_statement_timeout"
                if code == "57014"
                else "database_deadlock"
                if code == "40P01"
                else "database_lock_unavailable"
                if code == "55P03"
                else "database_pool_timeout"
                if type(error).__name__ == "TimeoutError"
                else "database_operation_failed"
            )
            if (
                isinstance(error, OSError)
                or (isinstance(code, str) and code.startswith("08"))
                or getattr(error, "connection_invalidated", False)
            ):
                reason = "database_connection_failed"
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
                kind,
                "Account validation timed out. Retry explicitly."
                if timed_out
                else "The account database is unavailable. Retry explicitly.",
                504 if timed_out else 503,
            ) from None

        finally:
            emit(
                "database_transaction",
                level=logging.DEBUG,
                duration_ms=round((time.monotonic() - started) * 1000),
                query_count=counts["count"],
                query_ms=counts["ms"],
            )
            query_counts.reset(counts_token)

    async def close(self):
        if self.engine:
            await self.engine.dispose()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.transaction() as session:
        yield session
