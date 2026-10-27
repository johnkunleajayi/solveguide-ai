import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import Float, String, Text, bindparam, cast, delete, func, select, text
from sqlalchemy.types import UserDefinedType

from app.auth.security import now
from app.context_library.models import ContextDocument
from app.context_library.service import ContextService
from app.database import PlatformError
from app.rag.models import DocumentChunk, DocumentIndex


class RagRepository:
    def __init__(self, database):
        self.database = database

    async def vector_available(self):
        async with self.database.transaction() as db:
            return bool(
                await db.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")
                )
            )

    async def document(self, owner, identifier):
        async with self.database.transaction() as db:
            return await ContextService.owned(db, owner, identifier)

    async def catalog(self, owner, cursor=None, selected=None):
        query = (
            select(
                ContextDocument.id,
                ContextDocument.title,
                ContextDocument.extraction_status,
                DocumentIndex.status,
                DocumentIndex.method,
                DocumentIndex.error_code,
                DocumentIndex.generation,
            )
            .outerjoin(
                DocumentIndex,
                (DocumentIndex.document_id == ContextDocument.id)
                & (DocumentIndex.owner_id == owner),
            )
            .where(ContextDocument.owner_id == owner)
        )
        if cursor:
            query = query.where(ContextDocument.id > cursor)
        if selected:
            query = query.where(ContextDocument.id.in_(selected))
        async with self.database.transaction() as db:
            rows = (await db.execute(query.order_by(ContextDocument.id).limit(51))).all()
            return {
                "documents": [
                    dict(
                        id=str(row.id),
                        title=row.title,
                        extraction_status=row.extraction_status,
                        index_status=row.status or "not_indexed",
                        method=row.method,
                        error_code=row.error_code,
                        generation=str(row.generation) if row.generation else None,
                    )
                    for row in rows[:50]
                ],
                "next_cursor": str(rows[49].id) if len(rows) > 50 else None,
            }

    async def start(self, owner, identifier, digest, method, settings, consent, force):
        async with self.database.transaction() as db:
            document = await ContextService.owned(db, owner, identifier, lock=True)
            if document.extraction_status != "ready":
                raise PlatformError(
                    "index_unavailable", "This document has no usable extracted text.", 409
                )
            row = await db.scalar(
                select(DocumentIndex)
                .where(DocumentIndex.document_id == identifier, DocumentIndex.owner_id == owner)
                .with_for_update()
            )
            if row and row.status == "indexing" and row.updated_at > now() - timedelta(minutes=3):
                raise PlatformError("index_busy", "This document is already being indexed.", 409)
            if row and row.status == "ready" and row.version == digest and not force:
                return None
            if row is None:
                row = DocumentIndex(document_id=identifier, owner_id=owner)
                db.add(row)
            row.generation, row.version, row.status, row.method = (
                uuid4(),
                digest,
                "indexing",
                method,
            )
            row.embedding_model = (
                settings.openai_embedding_model if method == "semantic_pgvector" else None
            )
            row.dimensions = (
                settings.embedding_dimensions if method == "semantic_pgvector" else None
            )
            row.consent_at = now() if consent else None
            row.error_code, row.chunk_count = None, 0
            await db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == identifier, DocumentChunk.owner_id == owner
                )
            )
            await db.flush()
            return row.generation

    async def finish(self, owner, identifier, generation, parts, vectors):
        async with self.database.transaction() as db:
            document = await ContextService.owned(db, owner, identifier, lock=True)
            row = await db.scalar(
                select(DocumentIndex)
                .where(DocumentIndex.document_id == identifier, DocumentIndex.owner_id == owner)
                .with_for_update()
            )
            if not row or row.generation != generation or document.extraction_status != "ready":
                raise PlatformError(
                    "context_changed", "The document changed. Refresh and retry.", 409
                )
            for part, vector in zip(parts, vectors, strict=True):
                db.add(
                    DocumentChunk(
                        id=part.id,
                        owner_id=owner,
                        document_id=identifier,
                        generation=generation,
                        ordinal=part.ordinal,
                        start_offset=part.start,
                        end_offset=part.end,
                        page_number=part.page,
                        location=part.location,
                        content=part.text,
                        embedding=vector,
                    )
                )
            row.status, row.error_code, row.chunk_count = "ready", None, len(parts)

    async def failed(self, owner, identifier, generation, code):
        async with self.database.transaction() as db:
            row = await db.scalar(
                select(DocumentIndex)
                .where(
                    DocumentIndex.document_id == identifier,
                    DocumentIndex.owner_id == owner,
                    DocumentIndex.generation == generation,
                )
                .with_for_update()
            )
            if row:
                row.status, row.error_code = "failed", code

    async def selection(self, owner, identifiers):
        async with self.database.transaction() as db:
            documents = list(
                (
                    await db.scalars(
                        select(ContextDocument).where(
                            ContextDocument.owner_id == owner, ContextDocument.id.in_(identifiers)
                        )
                    )
                ).all()
            )
            if {d.id for d in documents} != set(identifiers):
                raise PlatformError(
                    "document_not_found", "A selected document is unavailable.", 404
                )
            indexes = list(
                (
                    await db.scalars(
                        select(DocumentIndex).where(
                            DocumentIndex.owner_id == owner,
                            DocumentIndex.document_id.in_(identifiers),
                        )
                    )
                ).all()
            )
            return documents, indexes

    async def validate(self, owner, snapshots):
        documents, indexes = await self.selection(owner, list(snapshots))
        if (
            any(d.extraction_status != "ready" for d in documents)
            or {i.document_id: i.generation for i in indexes if i.status == "ready"} != snapshots
        ):
            raise PlatformError(
                "context_changed", "Selected materials changed. Refresh and retry.", 409
            )

    async def rank(self, owner, identifiers, method, query, vector=None):
        if method == "semantic_pgvector":
            score = 1 - text_distance()
        else:
            score = func.ts_rank_cd(
                func.to_tsvector(text("'simple'::regconfig"), DocumentChunk.content),
                func.to_tsquery("simple", query),
            )
        statement = (
            select(DocumentChunk, ContextDocument.title, score.label("score"))
            .join(
                DocumentIndex,
                (DocumentIndex.document_id == DocumentChunk.document_id)
                & (DocumentIndex.owner_id == owner)
                & (DocumentIndex.generation == DocumentChunk.generation),
            )
            .join(
                ContextDocument,
                (ContextDocument.id == DocumentChunk.document_id)
                & (ContextDocument.owner_id == owner),
            )
            .where(
                DocumentChunk.owner_id == owner,
                DocumentChunk.document_id.in_(identifiers),
                DocumentIndex.status == "ready",
                ContextDocument.extraction_status == "ready",
            )
        )
        if method == "semantic_pgvector":
            statement = statement.where(DocumentChunk.embedding.is_not(None))
        async with self.database.transaction() as db:
            rows = (
                await db.execute(
                    statement.order_by(
                        score.desc(), DocumentChunk.document_id, DocumentChunk.ordinal
                    ).limit(50),
                    {"query_vector": json.dumps(vector)} if vector else {},
                )
            ).all()
            return [(chunk, title, float(score)) for chunk, title, score in rows]


def text_distance():
    # JSONB keeps schema portable and supports configured dimensions. pgvector performs
    # exact cosine ranking, scoped by owner/document indexes; no ANN capability is claimed.
    return cast(cast(DocumentChunk.embedding, Text), PgVector()).op("<=>", return_type=Float)(
        cast(bindparam("query_vector", type_=String), PgVector())
    )


class PgVector(UserDefinedType):
    """Query-only pgvector cast; persisted schema remains portable JSONB."""

    cache_ok = True

    def get_col_spec(self, **_):
        return "vector"
