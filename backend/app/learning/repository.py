from contextlib import asynccontextmanager

from sqlalchemy import and_, delete, select

from app.auth.models import User
from app.context_library.models import ContextDocument
from app.database import PlatformError
from app.learning.models import LearningSession, SessionDocument
from app.rag.models import DocumentIndex


class SessionRepository:
    def __init__(self, database):
        self.database = database

    async def liveness(self, owner, identifier):
        statement = (
            select(
                LearningSession.id,
                LearningSession.revision,
                LearningSession.status,
                LearningSession.mode,
                LearningSession.selected_count,
                LearningSession.allow_context_transmission,
                SessionDocument.document_id,
                ContextDocument.extraction_status,
                DocumentIndex.status.label("index_status"),
                DocumentIndex.generation,
            )
            .outerjoin(
                SessionDocument,
                and_(
                    SessionDocument.session_id == LearningSession.id,
                    SessionDocument.owner_id == owner,
                    LearningSession.mode != "general",
                ),
            )
            .outerjoin(
                ContextDocument,
                and_(
                    ContextDocument.id == SessionDocument.document_id,
                    ContextDocument.owner_id == owner,
                ),
            )
            .outerjoin(
                DocumentIndex,
                and_(
                    DocumentIndex.document_id == ContextDocument.id,
                    DocumentIndex.owner_id == owner,
                ),
            )
            .where(LearningSession.owner_id == owner, LearningSession.id == identifier)
            .order_by(SessionDocument.ordinal)
        )
        async with self.database.transaction() as db:
            rows = (await db.execute(statement)).mappings().all()
        if not rows:
            return None
        first = rows[0]
        return dict(
            id=str(first["id"]),
            revision=first["revision"],
            status=first["status"],
            mode=first["mode"],
            selected_count=first["selected_count"],
            allow_context_transmission=first["allow_context_transmission"],
            documents=[
                dict(
                    id=str(r["document_id"]),
                    extraction_status=r["extraction_status"],
                    index_status=r["index_status"],
                    index_generation=str(r["generation"]) if r["generation"] else None,
                )
                for r in rows
                if r["document_id"] is not None
            ],
        )

    @asynccontextmanager
    async def transaction(self, owner):
        async with self.database.transaction() as db:
            # All lifecycle operations lock the same durable account row. This also
            # serializes first-draft creation, where no preparation row exists yet.
            if await db.scalar(select(User.id).where(User.id == owner).with_for_update()) is None:
                raise PlatformError("invalid_session", "Sign in again.", 401)
            yield Transaction(db, owner)


class Transaction:
    def __init__(self, db, owner):
        self.db, self.owner = db, owner

    async def current(self, statuses):
        return await self.db.scalar(
            select(LearningSession).where(
                LearningSession.owner_id == self.owner, LearningSession.status.in_(statuses)
            )
        )

    async def get(self, identifier):
        return await self.db.scalar(
            select(LearningSession).where(
                LearningSession.owner_id == self.owner, LearningSession.id == identifier
            )
        )

    async def links(self, row):
        return list(
            (
                await self.db.scalars(
                    select(SessionDocument.document_id)
                    .where(
                        SessionDocument.owner_id == self.owner, SessionDocument.session_id == row.id
                    )
                    .order_by(SessionDocument.ordinal)
                )
            ).all()
        )

    async def documents(self, ids):
        if not ids:
            return []
        # Lock documents before accepting new references; concurrent deletion cannot
        # create a valid-looking preparation containing a pending-deletion document.
        docs = list(
            (
                await self.db.execute(
                    select(
                        ContextDocument.id, ContextDocument.title, ContextDocument.extraction_status
                    )
                    .where(ContextDocument.owner_id == self.owner, ContextDocument.id.in_(ids))
                    .with_for_update()
                )
            ).all()
        )
        indexes = list(
            (
                await self.db.scalars(
                    select(DocumentIndex).where(
                        DocumentIndex.owner_id == self.owner, DocumentIndex.document_id.in_(ids)
                    )
                )
            ).all()
        )
        readiness = {i.document_id: i.status for i in indexes}
        generations = {i.document_id: str(i.generation) for i in indexes}
        found = {
            d.id: dict(
                id=str(d.id),
                title=d.title,
                extraction_status=d.extraction_status,
                index_status=readiness.get(d.id, "not_indexed"),
                index_generation=generations.get(d.id),
            )
            for d in docs
        }
        return [found[i] for i in ids if i in found]

    async def put(self, row):
        self.db.add(row)
        await self.db.flush()

    async def set_links(self, row, ids):
        await self.db.execute(
            delete(SessionDocument).where(
                SessionDocument.session_id == row.id, SessionDocument.owner_id == self.owner
            )
        )
        self.db.add_all(
            [
                SessionDocument(
                    session_id=row.id, owner_id=self.owner, document_id=value, ordinal=i
                )
                for i, value in enumerate(ids)
            ]
        )
        await self.db.flush()

    async def prune_ended(self):
        await self.db.execute(
            delete(LearningSession).where(
                and_(LearningSession.owner_id == self.owner, LearningSession.status == "ended")
            )
        )
