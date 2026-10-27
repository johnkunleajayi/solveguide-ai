import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import models  # noqa: F401
from app.config import Settings
from app.context_library import models as context_models  # noqa: F401
from app.database import Base, database_url
from app.runtime import event_loop

target_metadata = Base.metadata


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(
        database_url(Settings()), poolclass=pool.NullPool, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    # PostgreSQL dialect only; offline rendering never needs a real connection/secret.
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    try:
        asyncio.run(online(), loop_factory=event_loop)
    except Exception:
        raise SystemExit(
            "Migration failed. Check DATABASE_URL, connectivity and migration state; "
            "details suppressed to protect credentials."
        ) from None
