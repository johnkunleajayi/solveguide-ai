import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.answer.schemas import AnswerRecommendation
from app.auth.dependencies import required_current_user
from app.config import Settings
from app.database import PlatformError
from app.learning.models import LearningSession, SessionDocument
from app.learning.schemas import DraftInput, SessionAnswerRequest, StartInput
from app.learning.service import SessionService
from app.main import create_app
from app.schemas import QuestionObservation


class MemoryRepository:
    """Transactional domain double, not a substitute for PostgreSQL integration."""

    def __init__(self):
        self.rows, self.refs, self.docs = {}, {}, {}
        self.locks = defaultdict(asyncio.Lock)
        self.document_calls = 0

    @asynccontextmanager
    async def transaction(self, owner):
        async with self.locks[owner]:
            saved = deepcopy((self.rows, self.refs))
            await asyncio.sleep(0)  # Make concurrent requests contend on the account lock.
            repo = self

            class Transaction:
                async def current(self, states):
                    return next(
                        (
                            r
                            for r in repo.rows.values()
                            if r.owner_id == owner and r.status in states
                        ),
                        None,
                    )

                async def get(self, identifier):
                    row = repo.rows.get(identifier)
                    return row if row and row.owner_id == owner else None

                async def links(self, row):
                    return list(repo.refs.get(row.id, []))

                async def documents(self, ids):
                    repo.document_calls += 1
                    return [
                        repo.docs[i][1] for i in ids if i in repo.docs and repo.docs[i][0] == owner
                    ]

                async def put(self, row):
                    repo.rows[row.id] = row

                async def set_links(self, row, ids):
                    repo.refs[row.id] = ids

                async def prune_ended(self):
                    for key in list(repo.rows):
                        if repo.rows[key].owner_id == owner and repo.rows[key].status == "ended":
                            del repo.rows[key]
                            repo.refs.pop(key, None)

            try:
                yield Transaction()
            except BaseException:
                self.rows, self.refs = saved
                raise

    def delete_document(self, identifier):
        self.docs.pop(identifier)
        for key in self.refs:
            self.refs[key] = [i for i in self.refs[key] if i != identifier]


@pytest.fixture
def setup_learning():
    repo = MemoryRepository()
    owner, document = uuid4(), uuid4()
    repo.docs[document] = (
        owner,
        dict(id=str(document), title="Reference", extraction_status="ready", index_status="ready"),
    )
    return NS(repo=repo, service=SessionService(repo), owner=owner, document=document)


def payload(s, **patch):
    return DraftInput.model_validate(
        {**dict(purpose="general_learning", objective="Understand the practice question."), **patch}
    )


async def prepared(s, mode="general"):
    draft = await s.service.save(
        s.owner,
        payload(
            s,
            mode=mode,
            document_ids=[] if mode == "general" else [str(s.document)],
            allow_context_transmission=mode != "general",
        ),
    )
    return await s.service.ready(s.owner, draft["id"], draft["revision"])


async def started(s, mode="general"):
    draft = await prepared(s, mode)
    return await s.service.start(
        s.owner, StartInput(preparation_id=draft["id"], revision=draft["revision"])
    )


@pytest.mark.parametrize(
    "patch",
    [
        dict(purpose="interview_preparation", objective="   "),
        dict(objective="x" * 2001),
        dict(purpose="unknown"),
        dict(purpose="custom", custom_purpose=" "),
        dict(custom_purpose="unexpected"),
        dict(document_ids=["invalid"]),
        dict(allow_context_transmission="yes"),
        dict(revision=0),
    ],
)
def test_preparation_validation(setup_learning, patch):
    with pytest.raises(ValidationError):
        DraftInput.model_validate(
            {**dict(purpose="general_learning", objective="Learn something."), **patch}
        )


def test_draft_update_recovery_and_stale_revision(setup_learning):
    s = setup_learning

    async def run():
        assert await s.service.read(s.owner) == dict(draft=None, active=None)
        draft = await s.service.save(s.owner, payload(s))
        assert draft["status"] == "draft" and draft["document_ids"] == []
        changed = await s.service.save(
            s.owner,
            payload(
                s, revision=draft["revision"], mode="context_guided", document_ids=[str(s.document)]
            ),
        )
        assert changed["mode"] == "context_guided" and not changed["ready"]
        assert (await SessionService(s.repo).read(s.owner))["draft"]["revision"] == changed[
            "revision"
        ]
        with pytest.raises(PlatformError) as error:
            await s.service.save(s.owner, payload(s, revision=draft["revision"]))
        assert error.value.code == "preparation_changed"

    asyncio.run(run())


def test_ownership_and_duplicate_selection(setup_learning):
    s = setup_learning

    async def run():
        with pytest.raises(PlatformError) as error:
            await s.service.save(uuid4(), payload(s, document_ids=[str(s.document)]))
        assert error.value.status == 404
        assert not s.repo.rows
        with pytest.raises(ValidationError):
            payload(s, document_ids=[str(s.document)] * 2)
        active = await started(s)
        with pytest.raises(PlatformError) as error:
            await s.service.end(uuid4(), active["id"], active["revision"])
        assert error.value.status == 404

    asyncio.run(run())


def test_readiness_consent_and_deletion_fail_closed(setup_learning):
    s = setup_learning

    async def run():
        draft = await s.service.save(
            s.owner, payload(s, mode="materials_only", document_ids=[str(s.document)])
        )
        with pytest.raises(PlatformError):
            await s.service.ready(s.owner, draft["id"], draft["revision"])
        draft = await s.service.save(
            s.owner,
            payload(
                s,
                revision=draft["revision"],
                mode="materials_only",
                document_ids=[str(s.document)],
                allow_context_transmission=True,
            ),
        )
        s.repo.docs[s.document][1]["index_status"] = "indexing"
        with pytest.raises(PlatformError):
            await s.service.ready(s.owner, draft["id"], draft["revision"])
        s.repo.docs[s.document][1]["index_status"] = "ready"
        draft = await s.service.ready(s.owner, draft["id"], draft["revision"])
        active = await s.service.start(
            s.owner, StartInput(preparation_id=draft["id"], revision=draft["revision"])
        )
        s.repo.delete_document(s.document)
        recovered = await s.service.active(s.owner)
        assert recovered["missing_document_count"] == 1 and not recovered["ready"]
        with pytest.raises(PlatformError) as error:
            await s.service.configuration(s.owner, active["id"], active["revision"])
        assert error.value.code == "session_materials_changed"

    asyncio.run(run())


def test_concurrent_starts_are_idempotent_and_replacement_requires_exact_confirmation(
    setup_learning,
):
    s = setup_learning

    async def run():
        draft = await prepared(s)
        request = StartInput(preparation_id=draft["id"], revision=draft["revision"])
        first, retry = await asyncio.gather(
            s.service.start(s.owner, request), s.service.start(s.owner, request)
        )
        assert first["id"] == retry["id"]
        assert len([r for r in s.repo.rows.values() if r.status == "active"]) == 1
        draft = await prepared(s)
        with pytest.raises(PlatformError) as error:
            await s.service.start(
                s.owner, StartInput(preparation_id=draft["id"], revision=draft["revision"])
            )
        assert error.value.code == "active_session_exists"
        with pytest.raises(PlatformError):
            await s.service.start(
                s.owner,
                StartInput(
                    preparation_id=draft["id"],
                    revision=draft["revision"],
                    replace_active_id=str(uuid4()),
                ),
            )
        replacement = await s.service.start(
            s.owner,
            StartInput(
                preparation_id=draft["id"],
                revision=draft["revision"],
                replace_active_id=first["id"],
            ),
        )
        assert replacement["id"] != first["id"]
        assert (
            s.repo.rows[next(key for key in s.repo.rows if str(key) == first["id"])].status
            == "ended"
        )
        await s.service.end(s.owner, replacement["id"], replacement["revision"])
        assert await s.service.active(s.owner) is None
        assert len([r for r in s.repo.rows.values() if r.status == "ended"]) == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["general", "context_guided", "materials_only"])
def test_authoritative_reasoning_and_general_isolation(
    setup_learning, observation_data, answer_data, mode
):
    s = setup_learning

    async def run():
        active = await started(s, mode)
        answer, rag = (
            NS(recommend=AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))),
            NS(recommend=AsyncMock(return_value=AnswerRecommendation.model_validate(answer_data))),
        )
        request = SessionAnswerRequest(
            observation=QuestionObservation.model_validate(observation_data),
            session_id=active["id"],
            session_revision=active["revision"],
        )
        s.repo.document_calls = 0
        await s.service.recommend(s.owner, request, answer, rag)
        if mode == "general":
            assert s.repo.document_calls == 0
            answer.recommend.assert_awaited_once()
            rag.recommend.assert_not_awaited()
            assert answer.recommend.call_args.kwargs["context"].objective == active["objective"]
        else:
            routed = rag.recommend.call_args.args[1]
            assert routed.mode == mode and routed.document_ids == [str(s.document)]
            assert routed.allow_context_transmission
            answer.recommend.assert_not_awaited()
        with pytest.raises(PlatformError) as error:
            await s.service.guard_legacy(s.owner)
        assert error.value.code == "session_required"

    asyncio.run(run())


def test_late_answer_is_discarded_after_end(setup_learning, observation_data, answer_data):
    s = setup_learning

    async def run():
        active = await started(s)

        async def provider(*args, **kwargs):
            await s.service.end(s.owner, active["id"], active["revision"])
            return AnswerRecommendation.model_validate(answer_data)

        request = SessionAnswerRequest(
            observation=QuestionObservation.model_validate(observation_data),
            session_id=active["id"],
            session_revision=active["revision"],
        )
        with pytest.raises(PlatformError):
            await s.service.recommend(s.owner, request, NS(recommend=provider), None)

    asyncio.run(run())


def test_schema_metadata_contains_only_preparation_and_enforces_postgresql_guards():
    names = set(LearningSession.__table__.columns.keys())
    assert not names.intersection(
        {"screenshot", "question", "observation", "answer", "provider_payload"}
    )
    indexes = {
        i.name: str(CreateIndex(i).compile(dialect=postgresql.dialect()))
        for i in LearningSession.__table__.indexes
    }
    assert "WHERE status = 'active'" in indexes["uq_learning_active_owner"]
    assert "UNIQUE INDEX" in indexes["uq_learning_draft_owner"]
    assert all(fk.ondelete == "CASCADE" for fk in SessionDocument.__table__.foreign_key_constraints)
    assert all(
        column.type.timezone
        for column in LearningSession.__table__.columns
        if column.name.endswith("_at")
    )


def test_authenticated_routes_and_legacy_bypass_rejection(setup_learning, observation_data):
    s = setup_learning
    app = create_app(Settings(_env_file=None))
    app.state.learning_service = s.service
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/learning/preparation").status_code == 401
        app.dependency_overrides[required_current_user] = lambda: NS(id=s.owner)
        headers = {"Origin": "http://tauri.localhost"}
        response = client.put(
            "/api/v1/learning/preparation", json=payload(s).model_dump(), headers=headers
        )
        assert response.status_code == 200
        draft = response.json()
        ready = client.post(
            f"/api/v1/learning/preparation/{draft['id']}/ready",
            json={"revision": draft["revision"]},
            headers=headers,
        ).json()
        active = client.post(
            "/api/v1/learning/sessions/start",
            json={"preparation_id": ready["id"], "revision": ready["revision"]},
            headers=headers,
        )
        assert active.status_code == 200
        assert client.get("/api/v1/learning/sessions/active").json()["id"] == ready["id"]
        assert (
            client.post("/api/v1/answer", json=observation_data, headers=headers).status_code == 409
        )
        app.dependency_overrides[required_current_user] = lambda: NS(id=uuid4())
        assert client.get("/api/v1/learning/sessions/active").json() is None
        assert (
            client.post(
                f"/api/v1/learning/sessions/{ready['id']}/end",
                json={"revision": active.json()["revision"]},
                headers=headers,
            ).status_code
            == 404
        )


def test_session_answer_rejects_client_configuration_override(observation_data):
    for extra in [{"mode": "general"}, {"document_ids": []}, {"objective": "Override"}]:
        with pytest.raises(ValidationError):
            SessionAnswerRequest.model_validate(
                dict(
                    observation=observation_data,
                    session_id=str(uuid4()),
                    session_revision=1,
                    **extra,
                )
            )


def test_index_generation_metadata_is_bounded_and_does_not_contain_document_text():
    from app.learning.schemas import DocumentReference

    reference = DocumentReference(
        id=str(uuid4()),
        title="Disposable reference",
        extraction_status="ready",
        index_status="ready",
        index_generation=str(uuid4()),
    )
    assert reference.index_generation is not None
    assert "extracted_text" not in reference.model_dump()
    with pytest.raises(ValidationError):
        DocumentReference.model_validate({**reference.model_dump(), "extracted_text": "private"})
    with pytest.raises(ValidationError):
        DocumentReference.model_validate({**reference.model_dump(), "index_generation": "invalid"})


@pytest.mark.parametrize("mode", ["general", "context_guided", "materials_only"])
def test_compact_liveness_ownership_revision_and_readiness(mode):
    owner, identifier, document = uuid4(), uuid4(), uuid4()
    value = dict(
        id=str(identifier),
        revision=3,
        status="active",
        mode=mode,
        selected_count=1,
        allow_context_transmission=True,
        documents=[]
        if mode == "general"
        else [
            dict(
                id=str(document),
                extraction_status="ready",
                index_status="ready",
                index_generation=str(uuid4()),
            )
        ],
    )

    class Repository:
        async def liveness(self, requested_owner, requested_id):
            return (
                deepcopy(value) if (requested_owner, requested_id) == (owner, identifier) else None
            )

    service = SessionService(Repository())

    async def run():
        result = await service.liveness(owner, identifier, 3)
        assert result["ready"] and result["mode"] == mode
        assert not {"objective", "purpose", "title", "extracted_text"} & result.keys()
        if mode == "general":
            assert result["documents"] == []
        with pytest.raises(PlatformError) as error:
            await service.liveness(uuid4(), identifier, 3)
        assert error.value.code == "preparation_not_found"
        with pytest.raises(PlatformError) as error:
            await service.liveness(owner, identifier, 2)
        assert error.value.code == "session_revision_mismatch"
        value["status"] = "ended"
        with pytest.raises(PlatformError) as error:
            await service.liveness(owner, identifier, 3)
        assert error.value.code == "session_not_active"
        value["status"] = "active"
        if mode != "general":
            for patch in [
                dict(documents=[]),
                dict(allow_context_transmission=False),
                dict(documents=[{**value["documents"][0], "index_status": "indexing"}]),
            ]:
                original = deepcopy(value)
                value.update(patch)
                with pytest.raises(PlatformError) as error:
                    await service.liveness(owner, identifier, 3)
                assert error.value.code == "session_materials_not_ready"
                value.clear()
                value.update(original)

    asyncio.run(run())


def test_liveness_endpoint_requires_auth_and_preserves_error_codes():
    owner, identifier = uuid4(), uuid4()
    app = create_app(Settings(_env_file=None))
    service = NS(
        liveness=AsyncMock(side_effect=PlatformError("session_revision_mismatch", "Changed", 409))
    )
    app.state.learning_service = service
    path = f"/api/v1/learning/sessions/{identifier}/validate"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://tauri.localhost"}
        assert client.post(path, json={"revision": 1}, headers=headers).status_code == 401
        service.liveness.assert_not_awaited()
        app.dependency_overrides[required_current_user] = lambda: NS(id=owner)
        result = client.post(path, json={"revision": 1}, headers=headers)
        assert result.status_code == 409
        assert result.json()["error"]["code"] == "session_revision_mismatch"
        service.liveness.assert_awaited_once_with(owner, identifier, 1)


def test_liveness_is_one_owned_projection_without_lifecycle_locks():
    from app.learning.repository import SessionRepository

    owner, identifier = uuid4(), uuid4()

    class Database:
        calls = []

        @asynccontextmanager
        async def transaction(self):
            yield self

        async def execute(self, statement):
            self.calls.append(statement)
            return NS(mappings=lambda: NS(all=lambda: []))

    database = Database()
    assert asyncio.run(SessionRepository(database).liveness(owner, identifier)) is None
    assert len(database.calls) == 1
    compiled = database.calls[0].compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    assert "for update" not in sql
    assert "objective" not in sql and "title" not in sql and "extracted_text" not in sql
    assert "learning_sessions.owner_id =" in sql
    assert "learning_sessions.id =" in sql
    assert "learning_sessions.mode !=" in sql
    assert "context_documents.owner_id =" in sql
    assert "context_indexes.owner_id =" in sql


def test_active_lookup_does_not_load_a_draft(setup_learning):
    s = setup_learning

    async def run():
        active = await started(s)
        await prepared(s, "context_guided")
        s.service.read = AsyncMock(
            side_effect=AssertionError("full preparation must not be loaded")
        )
        result = await s.service.active(s.owner)
        assert result["id"] == active["id"]

    asyncio.run(run())


@pytest.mark.parametrize("code", ["session_expired", "session_revoked"])
def test_liveness_rejects_expired_auth_before_service(code):
    app = create_app(Settings(_env_file=None))
    service = NS(liveness=AsyncMock())
    app.state.learning_service = service

    def expired():
        raise PlatformError(code, "Sign in again.", 401)

    app.dependency_overrides[required_current_user] = expired
    with TestClient(app, base_url="http://127.0.0.1") as client:
        result = client.post(
            f"/api/v1/learning/sessions/{uuid4()}/validate",
            json={"revision": 1},
            headers={"Origin": "http://tauri.localhost"},
        )
    assert result.status_code == 401 and result.json()["error"]["code"] == code
    service.liveness.assert_not_awaited()


def test_liveness_success_is_compact_and_correlated():
    owner, identifier = uuid4(), uuid4()
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[required_current_user] = lambda: NS(id=owner)
    app.state.learning_service = NS(
        liveness=AsyncMock(
            return_value=dict(
                id=str(identifier),
                revision=4,
                status="active",
                ready=True,
                mode="general",
                documents=[],
                document_ids=[],
            )
        )
    )
    request_id, trace_id = str(uuid4()), "live-1-abc-1"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            f"/api/v1/learning/sessions/{identifier}/validate",
            json={"revision": 4},
            headers={
                "Origin": "http://tauri.localhost",
                "X-Request-ID": request_id,
                "X-Solveguide-Trace-ID": trace_id,
            },
        )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-solveguide-trace-id"] == trace_id
    assert set(response.json()) == {
        "id",
        "revision",
        "status",
        "ready",
        "mode",
        "documents",
        "document_ids",
    }


@pytest.mark.parametrize(
    "legacy,canonical",
    [
        ("general_learning", "custom"),
        ("certification_practice", "research_study"),
        ("technical_assessment_practice", "interview_preparation"),
        ("interview_preparation", "interview_preparation"),
        ("research_study", "research_study"),
        ("custom", "custom"),
    ],
)
def test_legacy_purpose_is_read_without_mutation_and_normalized_only_on_edit(
    setup_learning, legacy, canonical
):
    s = setup_learning

    async def run():
        active = await started(s)
        row = next(r for r in s.repo.rows.values() if str(r.id) == active["id"])
        row.purpose = legacy
        row.custom_purpose = "My original purpose" if legacy == "custom" else None
        before = deepcopy((row.purpose, row.custom_purpose, row.revision, row.objective))
        result = await s.service.active(s.owner)
        assert result["purpose"] == legacy and result["revision"] == before[2]
        config = await s.service.configuration(s.owner, row.id, row.revision)
        assert config["objective"] == before[3]
        assert (row.purpose, row.custom_purpose, row.revision, row.objective) == before
        edited = DraftInput(
            purpose=legacy, custom_purpose=row.custom_purpose, objective=row.objective
        )
        assert edited.purpose == canonical
        if canonical == "custom":
            assert edited.custom_purpose
        # A stale edit is still rejected; normalization does not bypass revision checks.
        with pytest.raises(PlatformError):
            await s.service.save(s.owner, edited.model_copy(update={"revision": 999}))

    asyncio.run(run())


def test_general_custom_defaults_and_explicit_objective_validation():
    from typing import get_args

    from app.learning.schemas import DEFAULT_OBJECTIVE, NewPurpose

    assert set(get_args(NewPurpose)) == {"interview_preparation", "research_study", "custom"}
    for fields in [{}, {"objective": ""}, {"objective": "   "}]:
        value = DraftInput(purpose="custom", **fields)
        assert value.objective == DEFAULT_OBJECTIVE and value.custom_purpose == "General / Custom"
    assert DraftInput(purpose="custom", objective="  Learn coding  ").objective == "Learn coding"
    for objective in ["x" * 2001, "\x00", "text\x01"]:
        with pytest.raises(ValidationError):
            DraftInput(purpose="custom", objective=objective)
    for purpose in ["interview_preparation", "research_study"]:
        with pytest.raises(ValidationError):
            DraftInput(purpose=purpose, objective=" ")


@pytest.mark.parametrize("purpose", ["interview_preparation", "research_study", "custom"])
@pytest.mark.parametrize(
    "question_type",
    [
        "multiple_choice",
        "multiple_select",
        "true_false",
        "short_answer",
        "essay",
        "mathematics",
        "code",
        "mixed",
    ],
)
def test_all_purposes_forward_every_question_format_unchanged(
    setup_learning, observation_data, purpose, question_type
):
    s = setup_learning

    async def run():
        row = await s.service.save(s.owner, payload(s, purpose=purpose))
        row = await s.service.ready(s.owner, row["id"], row["revision"])
        row = await s.service.start(
            s.owner, StartInput(preparation_id=row["id"], revision=row["revision"])
        )
        data = {
            **observation_data,
            "question_type": question_type,
            "instructions": ["Preserve these question-specific requirements."],
        }
        if question_type == "multiple_select":
            data["required_selection_count"] = 2
        elif question_type not in ("multiple_choice", "true_false"):
            data.update(options=[], required_selection_count=None)
        observation = QuestionObservation.model_validate(data)
        answer = NS(recommend=AsyncMock(return_value="validated answer"))
        rag = NS(recommend=AsyncMock(side_effect=AssertionError("General must not retrieve")))
        result = await s.service.recommend(
            s.owner,
            SessionAnswerRequest(
                observation=observation, session_id=row["id"], session_revision=row["revision"]
            ),
            answer,
            rag,
        )
        assert result == "validated answer"
        assert answer.recommend.await_args.args == (observation,)
        assert answer.recommend.await_args.kwargs["context"].objective == row["objective"]
        rag.recommend.assert_not_awaited()

    asyncio.run(run())
