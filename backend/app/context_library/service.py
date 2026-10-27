from datetime import datetime
from uuid import UUID

import anyio
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import load_only

from app.context_library.extraction import assemble, extract
from app.context_library.models import ContextDocument
from app.context_library.schemas import DocumentDetail, DocumentPage, DocumentSummary
from app.context_library.storage import DocumentStorage, new_storage_key
from app.database import PlatformError


class ContextService:
    def __init__(self, database, storage: DocumentStorage, settings):
        self.database, self.storage, self.settings = database, storage, settings
        self.parsers = anyio.CapacityLimiter(2)

    @staticmethod
    async def owned(db, owner: UUID, identifier: UUID, lock=False):
        query = select(ContextDocument).where(
            ContextDocument.id == identifier, ContextDocument.owner_id == owner
        )
        if lock:
            query = query.with_for_update()
        document = await db.scalar(query)
        if document is None:
            raise PlatformError("document_not_found", "This document is unavailable.", 404)
        return document

    async def list(self, owner, cursor: str | None = None):
        query = (
            select(ContextDocument)
            .options(
                load_only(
                    *(getattr(ContextDocument, name) for name in DocumentSummary.model_fields)
                )
            )
            .where(ContextDocument.owner_id == owner)
        )
        if cursor:
            try:
                stamp, identifier = cursor.split("|")
                stamp, identifier = datetime.fromisoformat(stamp), UUID(identifier)
                if stamp.tzinfo is None:
                    raise ValueError
            except ValueError:
                raise PlatformError("invalid_request", "Invalid library page.", 422) from None
            query = query.where(
                or_(
                    ContextDocument.created_at < stamp,
                    and_(ContextDocument.created_at == stamp, ContextDocument.id < identifier),
                )
            )
        async with self.database.transaction() as db:
            rows = list(
                (
                    await db.scalars(
                        query.order_by(
                            ContextDocument.created_at.desc(), ContextDocument.id.desc()
                        ).limit(51)
                    )
                ).all()
            )
            more = len(rows) > 50
            rows = rows[:50]
            return DocumentPage(
                documents=[DocumentSummary.model_validate(row) for row in rows],
                next_cursor=f"{rows[-1].created_at.isoformat()}|{rows[-1].id}" if more else None,
            )

    async def detail(self, owner, identifier):
        async with self.database.transaction() as db:
            return DocumentDetail.model_validate(await self.owned(db, owner, identifier))

    async def create(self, owner, title, data=None, kind="txt", filename=None, pasted=None):
        if pasted is not None:
            result = assemble([("text", pasted)], self.settings)
            if result.status != "ready":
                raise PlatformError(
                    "invalid_document", "Enter readable text for your library.", 422
                )
        else:
            result = await anyio.to_thread.run_sync(
                extract, data, kind, self.settings, limiter=self.parsers
            )
        key = new_storage_key() if data is not None else None
        if key:
            await anyio.to_thread.run_sync(self.storage.write, key, data)
        try:
            async with self.database.transaction() as db:
                document = ContextDocument(
                    owner_id=owner,
                    title=title,
                    original_filename=filename,
                    document_type=kind,
                    source_type="upload" if key else "pasted_text",
                    storage_key=key,
                    byte_size=len(data) if data is not None else len(pasted.encode("utf-8")),
                    extraction_status=result.status,
                    extraction_error=result.error,
                    extracted_text=result.text,
                    extraction_structure=[segment.model_dump() for segment in result.structure],
                    character_count=len(result.text),
                )
                db.add(document)
                await db.flush()
                response = DocumentDetail.model_validate(document)
            return response
        except BaseException:
            # Also compensate a failed COMMIT, not just a failed flush.
            if key:
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(self.storage.delete, key)
            raise

    async def rename(self, owner, identifier, title):
        async with self.database.transaction() as db:
            document = await self.owned(db, owner, identifier, lock=True)
            if document.extraction_status == "deleting":
                raise PlatformError("deletion_pending", "Finish deleting this document first.", 409)
            document.title = title
            await db.flush()
            return DocumentDetail.model_validate(document)

    async def delete(self, owner, identifier):
        # Durable tombstone first. Storage failure or a later DB failure remains visible
        # and retryable. Missing files are an idempotent success, never silent row loss.
        async with self.database.transaction() as db:
            document = await self.owned(db, owner, identifier, lock=True)
            key = document.storage_key
            document.extraction_status = "deleting"
            document.extraction_error = "deletion_pending"
            document.extracted_text, document.extraction_structure = "", []
            document.character_count = 0
        if key:
            await anyio.to_thread.run_sync(self.storage.delete, key)
        async with self.database.transaction() as db:
            # A simultaneous successful deletion can already have removed the tombstone.
            document = await db.scalar(
                select(ContextDocument)
                .where(ContextDocument.id == identifier, ContextDocument.owner_id == owner)
                .with_for_update()
            )
            if document is not None:
                await db.delete(document)
