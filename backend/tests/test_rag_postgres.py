"""Opt-in live PostgreSQL check: temporary shadow tables, always rolled back.

No application rows, user documents or provider calls. Normal suites remain offline.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.context_library.models import ContextDocument
from app.database import Database, PlatformError
from app.rag.models import DocumentChunk, DocumentIndex
from app.rag.repository import RagRepository
from app.rag.service import RagService
from app.runtime import event_loop


@pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_ROLLBACK_TESTS") != "1",
    reason="Explicit opt-in required for temporary-table PostgreSQL validation",
)
def test_live_indexing_ranking_ownership_and_cleanup_without_public_writes():
    async def run():
        database = Database(Settings())
        try:
            async with database.engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(text("SET LOCAL search_path = pg_temp, public"))
                    for name in ("context_documents", "context_indexes", "context_chunks"):
                        # Fixed allowlist; never a caller-provided SQL identifier.
                        await connection.execute(
                            text(
                                f"CREATE TEMP TABLE {name} "
                                f"(LIKE public.{name} INCLUDING ALL) ON COMMIT DROP"
                            )
                        )
                    # LIKE copies checks/indexes but not foreign keys. Add scoped TEMP
                    # FKs to test the production composite ownership/cascade semantics.
                    await connection.execute(
                        text(
                            "ALTER TABLE pg_temp.context_indexes "
                            "ADD FOREIGN KEY (document_id, owner_id) "
                            "REFERENCES pg_temp.context_documents (id, owner_id) "
                            "ON DELETE CASCADE"
                        )
                    )
                    await connection.execute(
                        text(
                            "ALTER TABLE pg_temp.context_chunks "
                            "ADD FOREIGN KEY (document_id, owner_id) "
                            "REFERENCES pg_temp.context_indexes (document_id, owner_id) "
                            "ON DELETE CASCADE"
                        )
                    )

                    class BoundDatabase:
                        @asynccontextmanager
                        async def transaction(self):
                            async with (
                                AsyncSession(
                                    bind=connection,
                                    expire_on_commit=False,
                                    join_transaction_mode="create_savepoint",
                                ) as session,
                                session.begin(),
                            ):
                                yield session

                    bound = BoundDatabase()
                    owner, other_owner = uuid4(), uuid4()
                    identifiers = [uuid4() for _ in range(3)]
                    async with bound.transaction() as session:
                        for identifier, user, content in zip(
                            identifiers,
                            [owner, owner, other_owner],
                            [
                                "Flow automates a Salesforce process.",
                                "Unselected reference material.",
                                "Private other-user reference.",
                            ],
                            strict=True,
                        ):
                            session.add(
                                ContextDocument(
                                    id=identifier,
                                    owner_id=user,
                                    title="Disposable test reference",
                                    original_filename=None,
                                    document_type="txt",
                                    source_type="pasted_text",
                                    storage_key=None,
                                    byte_size=len(content),
                                    extraction_status="ready",
                                    extraction_error=None,
                                    extracted_text=content,
                                    extraction_structure=[
                                        dict(kind="page", number=1, start=0, end=len(content))
                                    ],
                                    character_count=len(content),
                                )
                            )

                    class OfflineEmbedding:
                        async def embed(self, values):
                            return [[1.0] + [0.0] * 63 for _ in values]

                    repository = RagRepository(bound)
                    settings = Settings(_env_file=None, embedding_dimensions=64)
                    service = RagService(repository, OfflineEmbedding(), None, settings)
                    semantic = await repository.vector_available()
                    method = "semantic_pgvector" if semantic else "lexical"
                    for identifier, user in zip(
                        identifiers, [owner, owner, other_owner], strict=True
                    ):
                        await service.index(user, identifier, method, semantic)
                    assert (await service.index(owner, identifiers[0], method, semantic))[
                        "unchanged"
                    ]
                    for mode in ["lexical"] + (["semantic_pgvector"] if semantic else []):
                        ranked = await repository.rank(
                            owner,
                            [identifiers[0], identifiers[2]],
                            mode,
                            "flow | salesforce",
                            [1.0] + [0.0] * 63 if mode == "semantic_pgvector" else None,
                        )
                        assert ranked and all(
                            row[0].document_id == identifiers[0] for row in ranked
                        )
                        assert ranked[0][2] > 0
                    result = await service.retriever.retrieve(
                        owner,
                        [identifiers[0]],
                        SimpleNamespace(
                            question_text="Which Flow automates a Salesforce process?", options=[]
                        ),
                    )
                    assert result.evidence[0].page_number == 1
                    assert result.evidence[0].excerpt == "Flow automates a Salesforce process."
                    with pytest.raises(PlatformError):
                        await repository.selection(owner, [identifiers[2]])
                    async with bound.transaction() as session:
                        row = await session.scalar(
                            select(ContextDocument).where(
                                ContextDocument.owner_id == owner,
                                ContextDocument.id == identifiers[0],
                            )
                        )
                        row.title = "Renamed without re-embedding"
                        await session.flush()
                        assert row.updated_at.tzinfo is not None
                    documents, before = await repository.selection(owner, [identifiers[0]])
                    await service.index(owner, identifiers[0], method, semantic, force=True)
                    with pytest.raises(PlatformError):
                        await repository.validate(owner, {identifiers[0]: before[0].generation})
                    async with bound.transaction() as session:
                        row = await session.scalar(
                            select(ContextDocument).where(
                                ContextDocument.owner_id == owner,
                                ContextDocument.id == identifiers[0],
                            )
                        )
                        await session.delete(row)
                    async with bound.transaction() as session:
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(DocumentIndex)
                                .where(
                                    DocumentIndex.owner_id == owner,
                                    DocumentIndex.document_id == identifiers[0],
                                )
                            )
                            == 0
                        )
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(DocumentChunk)
                                .where(
                                    DocumentChunk.owner_id == owner,
                                    DocumentChunk.document_id == identifiers[0],
                                )
                            )
                            == 0
                        )
                finally:
                    await transaction.rollback()
        finally:
            await database.close()

    asyncio.run(run(), loop_factory=event_loop)
