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
                await self.db.scalars(
                    select(ContextDocument)
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
        found = {
            d.id: dict(
                id=str(d.id),
                title=d.title,
                extraction_status=d.extraction_status,
                index_status=readiness.get(d.id, "not_indexed"),
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
