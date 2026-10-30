import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.database import PlatformError
from app.diagnostics import emit, span
from app.learning.models import LearningSession
from app.rag.schemas import ReasoningRequest


def fail(
    code="preparation_changed",
    message="Preparation changed. Refresh and review it again.",
    status=409,
):
    emit("session_validation_failed", level=logging.DEBUG, error_code=code, status=status)
    raise PlatformError(code, message, status)


def issues(row, ids, docs):
    if row.mode == "general":
        return []
    problems = []
    if not ids or len(ids) != row.selected_count or len(docs) != len(ids):
        problems.append("Selected reference materials are missing. Review your preparation.")
    if any(d["extraction_status"] != "ready" or d["index_status"] != "ready" for d in docs):
        problems.append("Selected materials must have ready text and a ready index.")
    if not row.allow_context_transmission:
        problems.append("Explicit passage-transmission consent is required for grounded reasoning.")
    return problems


class SessionService:
    def __init__(self, repository):
        self.repository = repository

    async def view(self, tx, row):
        if row is None:
            return None
        ids = await tx.links(row)
        docs = await tx.documents(ids)
        problems = issues(row, ids, docs)
        return dict(
            id=str(row.id),
            revision=row.revision,
            purpose=row.purpose,
            custom_purpose=row.custom_purpose,
            objective=row.objective,
            mode=row.mode,
            document_ids=[str(i) for i in ids],
            documents=docs,
            allow_context_transmission=row.allow_context_transmission,
            status=row.status,
            ready=not problems,
            issues=problems,
            missing_document_count=max(0, row.selected_count - len(docs)),
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            ended_at=row.ended_at,
        )

    async def read(self, owner):
        async with self.repository.transaction(owner) as tx:
            return dict(
                draft=await self.view(tx, await tx.current(["draft", "ready"])),
                active=await self.view(tx, await tx.current(["active"])),
            )

    @span("active_session_lookup")
    async def active(self, owner):
        async with self.repository.transaction(owner) as tx:
            active = await self.view(tx, await tx.current(["active"]))
        emit(
            "active_session_lookup",
            level=logging.DEBUG,
            owner_id=owner,
            session_id=active["id"] if active else None,
            revision=active["revision"] if active else None,
            state="active" if active else "no_active_session",
            mode=active["mode"] if active else None,
        )
        return active

    @span("session_liveness")
    async def liveness(self, owner, identifier, revision):
        value = await self.repository.liveness(owner, identifier)
        if value is None:
            fail("preparation_not_found", "This session is unavailable.", 404)
        if value["revision"] != revision:
            emit(
                "session_revision_check",
                level=logging.WARNING,
                session_id=identifier,
                expected_revision=revision,
                actual_revision=value["revision"],
                reason="revision_mismatch",
            )
            fail("session_revision_mismatch", "The session revision changed.")
        if value["status"] != "active":
            fail("session_not_active", "This session is no longer active.")
        docs = value["documents"]
        if value["mode"] != "general" and (
            not docs
            or len(docs) != value["selected_count"]
            or not value["allow_context_transmission"]
            or any(
                d["extraction_status"] != "ready"
                or d["index_status"] != "ready"
                or not d["index_generation"]
                for d in docs
            )
        ):
            fail("session_materials_not_ready", "Session materials changed or are not ready.")
        emit(
            "session_liveness",
            level=logging.DEBUG,
            session_id=identifier,
            revision=revision,
            mode=value["mode"],
            selected_count=len(docs),
            outcome="active",
        )
        return dict(
            id=value["id"],
            revision=value["revision"],
            status="active",
            mode=value["mode"],
            ready=True,
            documents=docs,
            document_ids=[d["id"] for d in docs],
        )

    async def save(self, owner, payload):
        async with self.repository.transaction(owner) as tx:
            row = await tx.current(["draft", "ready"])
            if (row is None and payload.revision is not None) or (
                row is not None and row.revision != payload.revision
            ):
                fail()
            ids = [UUID(v) for v in payload.document_ids]
            docs = await tx.documents(ids)
            if len(docs) != len(ids) or any(d["extraction_status"] == "deleting" for d in docs):
                fail("document_not_found", "A selected document is unavailable.", 404)
            now = datetime.now(UTC)
            if row is None:
                row = LearningSession(id=uuid4(), owner_id=owner, revision=0, created_at=now)
            for field in (
                "purpose",
                "custom_purpose",
                "objective",
                "mode",
                "allow_context_transmission",
            ):
                setattr(row, field, getattr(payload, field))
            row.status, row.selected_count = "draft", len(ids)
            row.revision += 1
            row.updated_at = now
            await tx.put(row)
            await tx.set_links(row, ids)
            return await self.view(tx, row)

    async def owned(self, tx, identifier, revision):
        row = await tx.get(UUID(str(identifier)))
        if row is None:
            emit(
                "session_lookup",
                level=logging.WARNING,
                session_id=identifier,
                reason="ownership_scope_miss",
            )
            fail("preparation_not_found", "This preparation is unavailable.", 404)
        if row.revision != revision:
            emit(
                "session_revision_check",
                level=logging.WARNING,
                session_id=row.id,
                expected_revision=revision,
                actual_revision=row.revision,
                reason="revision_mismatch",
            )
            fail()
        emit(
            "session_lookup",
            level=logging.DEBUG,
            session_id=row.id,
            revision=row.revision,
            state=row.status,
            reason="owned",
        )
        return row

    async def check_ready(self, tx, row):
        view = await self.view(tx, row)
        if not view["ready"]:
            fail(
                "preparation_not_ready",
                "Review selected material readiness and consent before starting.",
            )
        return view

    async def ready(self, owner, identifier, revision):
        async with self.repository.transaction(owner) as tx:
            row = await self.owned(tx, identifier, revision)
            if row.status not in ("draft", "ready"):
                fail()
            await self.check_ready(tx, row)
            if row.status != "ready":
                row.status = "ready"
                row.revision += 1
                row.updated_at = datetime.now(UTC)
                await tx.put(row)
            return await self.view(tx, row)

    async def start(self, owner, payload):
        async with self.repository.transaction(owner) as tx:
            row = await tx.get(UUID(payload.preparation_id))
            if row and row.status == "active" and row.revision == payload.revision + 1:
                return await self.view(tx, row)  # Safe retry of an already accepted start.
            row = await self.owned(tx, payload.preparation_id, payload.revision)
            if row.status != "ready":
                fail("preparation_not_ready", "Review and mark this preparation ready first.")
            await self.check_ready(tx, row)
            active = await tx.current(["active"])
            if (active is not None and str(active.id) != payload.replace_active_id) or (
                active is None and payload.replace_active_id is not None
            ):
                fail(
                    "active_session_exists",
                    "An active session changed or already exists. Confirm ending that "
                    "session before replacement.",
                )
            now = datetime.now(UTC)
            if active:
                await tx.prune_ended()
                active.status, active.ended_at, active.updated_at = "ended", now, now
                active.revision += 1
                await tx.put(active)  # Release the partial unique slot before activation.
            row.status, row.started_at, row.updated_at = "active", now, now
            row.revision += 1
            await tx.put(row)
            return await self.view(tx, row)

    async def end(self, owner, identifier, revision):
        async with self.repository.transaction(owner) as tx:
            row = await self.owned(tx, identifier, revision)
            if row.status != "active":
                fail("session_changed", "This session is no longer active.")
            await tx.prune_ended()
            row.status = "ended"
            row.ended_at = row.updated_at = datetime.now(UTC)
            row.revision += 1
            await tx.put(row)
            return await self.view(tx, row)

    async def guard_legacy(self, owner):
        async with self.repository.transaction(owner) as tx:
            if await tx.current(["active"]):
                fail("session_required", "Use the active session configuration for this answer.")

    async def configuration(self, owner, identifier, revision):
        async with self.repository.transaction(owner) as tx:
            row = await self.owned(tx, identifier, revision)
            if row.status != "active":
                fail(
                    "session_changed",
                    "This session has ended. Prepare or recover an active session.",
                )
            ids = await tx.links(row)
            # General does not read Context Library content, indexes or readiness.
            docs = [] if row.mode == "general" else await tx.documents(ids)
            if issues(row, ids, docs):
                fail(
                    "session_materials_changed",
                    "Session materials or readiness changed. End this session and review a "
                    "new preparation.",
                )
            emit(
                "session_configuration",
                level=logging.DEBUG,
                session_id=row.id,
                revision=row.revision,
                mode=row.mode,
                selected_count=len(ids),
            )
            return dict(
                id=str(row.id),
                revision=row.revision,
                purpose=row.custom_purpose or row.purpose,
                objective=row.objective,
                mode=row.mode,
                document_ids=[] if row.mode == "general" else [str(v) for v in ids],
                allow_context_transmission=row.allow_context_transmission,
            )

    async def recommend(self, owner, payload, answer_service, rag_service):
        config = await self.configuration(owner, payload.session_id, payload.session_revision)
        from app.answer.context import LearningContext

        context = LearningContext(purpose=config["purpose"], objective=config["objective"])
        if config["mode"] == "general":
            result = await answer_service.recommend(payload.observation, context=context)
        else:
            request = ReasoningRequest(
                observation=payload.observation,
                mode=config["mode"],
                document_ids=config["document_ids"],
                allow_context_transmission=config["allow_context_transmission"],
            )
            result = await rag_service.recommend(owner, request, context=context)
        # Do not publish a late recommendation after end/replacement/deletion.
        after = await self.configuration(owner, payload.session_id, payload.session_revision)
        if config != after:
            fail("session_changed", "The active session changed. Request a new answer.")
        return result
