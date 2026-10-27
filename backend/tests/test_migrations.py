import asyncio
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.auth.models import User
from app.auth.security import now
from app.config import Settings
from app.context_library.service import ContextService
from app.context_library.storage import LocalDocumentStorage
from app.database import Base, Database
from app.rag.repository import RagRepository
from app.rag.service import RagService
from app.runtime import event_loop

ROOT = Path(__file__).resolve().parents[1]


def config(output=None):
    cfg = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    return cfg


def test_alembic_offline_upgrade_downgrade_upgrade_and_schema_consistency():
    script = ScriptDirectory.from_config(config())
    assert script.get_heads() == ["0003_context_rag"]
    up, down, again = io.StringIO(), io.StringIO(), io.StringIO()
    command.upgrade(config(up), "head", sql=True)
    command.downgrade(config(down), "0003_context_rag:base", sql=True)
    command.upgrade(config(again), "head", sql=True)
    assert up.getvalue() == again.getvalue()
    for name in Base.metadata.tables:
        assert f"CREATE TABLE {name}" in up.getvalue()
        assert f"DROP TABLE {name}" in down.getvalue()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert column.name in up.getvalue()
        for constraint in table.constraints:
            if constraint.name:
                assert f"CONSTRAINT {constraint.name} " in up.getvalue()
        for index in table.indexes:
            assert index.name in up.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in up.getvalue()
    assert "UUID" in up.getvalue()


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL") or os.environ.get("ALLOW_TEST_DATABASE_RESET") != "1",
    reason="Requires a dedicated disposable PostgreSQL database and explicit reset opt-in",
)
def test_real_postgresql_roundtrip_and_constraints(monkeypatch, tmp_path):
    """Destructive only on explicit TEST_DATABASE_URL, never application's DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    command.upgrade(config(), "head")

    async def run():
        database = Database(Settings(_env_file=None, database_url=os.environ["TEST_DATABASE_URL"]))
        try:
            async with database.engine.connect() as connection:

                def compare(sync):
                    return compare_metadata(MigrationContext.configure(sync), Base.metadata)

                assert await connection.run_sync(compare) == []
            async with database.transaction() as db:
                user = User(
                    google_subject="integration-sub",
                    email=" TEST@Example.com ",
                    email_verified=True,
                    display_name="Test",
                    avatar_url=None,
                    last_login_at=now(),
                )
                db.add(user)
            async with database.transaction() as db:
                found = await db.scalar(
                    select(User).where(User.google_subject == "integration-sub")
                )
                assert found.email == "test@example.com" and found.created_at.tzinfo is not None
            service = ContextService(
                database, LocalDocumentStorage(tmp_path / "documents"), Settings(_env_file=None)
            )
            document = await service.create(
                found.id,
                "Disposable notes",
                data=b"Integration reference",
                kind="txt",
                filename="notes.txt",
            )
            rag = RagService(RagRepository(database), None, None, Settings(_env_file=None))
            await rag.index(found.id, document.id, "lexical")
            retrieved = await rag.retriever.retrieve(
                found.id,
                [document.id],
                SimpleNamespace(question_text="Integration reference", options=[]),
            )
            assert retrieved.evidence and retrieved.method == "lexical"
            renamed = await service.rename(found.id, document.id, "Renamed notes")
            assert renamed.title == "Renamed notes" and renamed.updated_at.tzinfo is not None
            assert (
                await service.detail(found.id, document.id)
            ).extracted_text == "Integration reference"
            await service.delete(found.id, document.id)
            async with database.transaction() as db:
                assert await db.scalar(text("SELECT count(*) FROM context_chunks")) == 0
            assert list((tmp_path / "documents").iterdir()) == []
            with pytest.raises(IntegrityError):
                async with database.sessions() as db, db.begin():
                    db.add(
                        User(
                            google_subject="integration-sub",
                            email="other@example.com",
                            email_verified=True,
                            display_name="Duplicate",
                            avatar_url=None,
                            last_login_at=now(),
                        )
                    )
                    await db.flush()
            async with database.transaction() as db:
                await db.execute(text("DELETE FROM users WHERE google_subject = 'integration-sub'"))
        finally:
            await database.close()

    asyncio.run(run(), loop_factory=event_loop)
    command.downgrade(config(), "base")
    command.upgrade(config(), "head")


def test_context_migration_roundtrip_preserves_auth_tables():
    up, down, again = io.StringIO(), io.StringIO(), io.StringIO()
    command.upgrade(config(up), "0001_auth:0002_context_library", sql=True)
    command.downgrade(config(down), "0002_context_library:0001_auth", sql=True)
    command.upgrade(config(again), "0001_auth:0002_context_library", sql=True)
    assert up.getvalue() == again.getvalue()
    assert "CREATE TABLE context_documents" in up.getvalue()
    assert "DROP TABLE context_documents" in down.getvalue()
    for table in ["users", "auth_sessions", "oauth_attempts"]:
        assert f"CREATE TABLE {table}" not in up.getvalue()
        assert f"DROP TABLE {table}" not in down.getvalue()


def test_rag_migration_roundtrip_preserves_documents_and_auth():
    up, down, again = io.StringIO(), io.StringIO(), io.StringIO()
    command.upgrade(config(up), "0002_context_library:0003_context_rag", sql=True)
    command.downgrade(config(down), "0003_context_rag:0002_context_library", sql=True)
    command.upgrade(config(again), "0002_context_library:0003_context_rag", sql=True)
    assert up.getvalue() == again.getvalue()
    for name in ["context_indexes", "context_chunks"]:
        assert f"CREATE TABLE {name}" in up.getvalue() and f"DROP TABLE {name}" in down.getvalue()
    for name in ["context_documents", "users", "auth_sessions", "oauth_attempts"]:
        assert f"DROP TABLE {name}" not in down.getvalue()
    assert "DELETE FROM context_documents" not in up.getvalue()
    assert "DROP EXTENSION" not in down.getvalue()
