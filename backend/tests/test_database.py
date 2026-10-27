import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database import Database


def test_pooler_rejecting_startup_options_still_gets_transaction_timeout(monkeypatch):
    """Reproduce the live mismatch: Alembic connects, app-only startup options fail."""
    events = []
    supplied_query = {"sslmode": "verify-full", "channel_binding": "require"}

    def pooler_engine(url, **kwargs):
        if "options" in kwargs.get("connect_args", {}):
            raise OperationalError(
                "connection", {}, Exception("unsupported startup parameter in options")
            )
        assert url.drivername == "postgresql+psycopg"
        assert dict(url.query) == supplied_query
        assert kwargs["connect_args"]["connect_timeout"] == 5
        return object()

    class Session:
        @asynccontextmanager
        async def __call__(self):
            try:
                yield self
            finally:
                events.append("closed")

        @asynccontextmanager
        async def begin(self):
            events.append("begin")
            try:
                yield
                events.append("commit")
            except RuntimeError:
                events.append("rollback")
                raise

        async def execute(self, statement):
            events.append(str(statement))

    session = Session()
    monkeypatch.setattr("app.database.create_async_engine", pooler_engine)
    monkeypatch.setattr("app.database.async_sessionmaker", lambda *a, **kw: session)
    database = Database(
        Settings(
            _env_file=None,
            database_url="postgresql://test:test@localhost/test"
            "?sslmode=verify-full&channel_binding=require",
        )
    )

    async def run():
        async with database.transaction() as active:
            await active.execute(text("SELECT 1"))
        assert events == [
            "begin",
            "SET LOCAL statement_timeout = '10s'",
            "SELECT 1",
            "commit",
            "closed",
        ]
        events.clear()
        try:
            async with database.transaction():
                raise RuntimeError("request failed")
        except RuntimeError:
            pass
        assert events == ["begin", "SET LOCAL statement_timeout = '10s'", "rollback", "closed"]

    asyncio.run(run())
