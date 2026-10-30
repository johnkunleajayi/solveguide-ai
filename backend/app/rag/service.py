import asyncio
from uuid import UUID

from app.answer.errors import AnswerError
from app.answer.service import abstain, validate_recommendation
from app.database import PlatformError
from app.diagnostics import emit, span
from app.rag.chunking import chunks, version
from app.rag.embedding import validate_vectors
from app.rag.retrieval import Retrieved, Retriever
from app.rag.schemas import Citation, GroundedAnswer, GroundedDraft


def grounded_result(observation, mode, retrieved, draft=None, limitation=None, reason=None):
    evidence = {e.chunk_id: e for e in retrieved.evidence}
    if (
        limitation
        or draft is None
        or not draft.sufficient_evidence
        or draft.contradictory_evidence
        or draft.recommendation.status in ("insufficient_information", "unsupported")
    ):
        decision = reason or (
            "contradictory_evidence"
            if draft and draft.contradictory_evidence
            else "provider_insufficient_evidence"
            if draft
            else "no_supported_evidence"
        )
        emit(
            "answer_decision",
            mode=mode,
            outcome="insufficient_information",
            reason=decision,
            evidence_count=len(evidence),
            method=retrieved.method,
        )
        answer = abstain(
            observation,
            "insufficient_information",
            limitation
            or (draft.limitation if draft else None)
            or (
                draft.recommendation.explanation[:1500]
                if draft
                and draft.recommendation.status in ("insufficient_information", "unsupported")
                else None
            )
            or "The selected passages do not support a reliable answer, or contain conflicting "
            "evidence. Review or add relevant materials.",
        )
        return GroundedAnswer(
            **answer.model_dump(),
            reasoning_mode=mode,
            grounding_status="insufficient_evidence",
            retrieval_method=retrieved.method,
            citations=[],
            general_reasoning=[],
        )
    answer = validate_recommendation(observation, draft.recommendation)
    refs = {}
    for support in draft.support:
        if support.target != "key_point" and support.point_index is not None:
            raise ValueError("Invalid support target")
        if support.target == "key_point" and (
            support.point_index is None or support.point_index >= len(answer.key_points)
        ):
            raise ValueError("Invalid key point")
        target = (
            f"key_point:{support.point_index}" if support.target == "key_point" else support.target
        )
        for key in support.chunk_ids:
            if key not in evidence:
                raise ValueError("Unretrieved citation")
            refs.setdefault(key, set()).add(target)
    if mode == "materials_only" and answer.status in ("answered", "uncertain"):
        required = {"answer", "explanation"} | {
            f"key_point:{i}" for i in range(len(answer.key_points))
        }
        covered = set().union(*refs.values()) if refs else set()
        if draft.general_reasoning or not required <= covered:
            return grounded_result(
                observation,
                mode,
                retrieved,
                limitation="The materials did not support every part of a reliable answer.",
                reason="incomplete_citation_support",
            )
    if not refs and mode == "context_guided":
        return grounded_result(
            observation,
            mode,
            retrieved,
            limitation="No document-supported explanation could be validated. "
            "Try General mode explicitly if appropriate.",
            reason="no_validated_citations",
        )
    citations = [
        Citation(**evidence[key].model_dump(), supports=sorted(targets))
        for key, targets in sorted(refs.items())
    ]
    emit(
        "answer_decision",
        mode=mode,
        outcome=answer.status,
        reason="validated_document_support",
        evidence_count=len(evidence),
        citation_count=len(citations),
        method=retrieved.method,
    )
    return GroundedAnswer(
        **answer.model_dump(),
        reasoning_mode=mode,
        grounding_status="mixed" if draft.general_reasoning else "document_supported",
        retrieval_method=retrieved.method,
        citations=citations,
        general_reasoning=draft.general_reasoning,
    )


class RagService:
    def __init__(self, repository, embedding, answer_service, settings):
        self.repository, self.embedding, self.answer_service, self.settings = (
            repository,
            embedding,
            answer_service,
            settings,
        )
        self.retriever = Retriever(repository, embedding, settings)

    async def index(self, owner, identifier, method, consent=False, force=False):
        document = await self.repository.document(owner, identifier)  # before any provider
        if method == "semantic_pgvector" and not consent:
            raise PlatformError(
                "context_consent_required",
                "Allow sending this document text to OpenAI before semantic indexing.",
                409,
            )
        if method == "semantic_pgvector" and not await self.repository.vector_available():
            raise PlatformError(
                "semantic_unavailable",
                "pgvector is unavailable. Choose local lexical indexing.",
                409,
            )
        digest = version(
            document.extracted_text, document.extraction_structure, self.settings, method
        )
        generation = await self.repository.start(
            owner, identifier, digest, method, self.settings, consent, force
        )
        if generation is None:
            return {"status": "ready", "unchanged": True}
        try:
            async with asyncio.timeout(120):
                parts = chunks(
                    identifier,
                    document.extracted_text,
                    document.extraction_structure,
                    self.settings.rag_chunk_characters,
                )
                if not parts or len(parts) > 2500:
                    raise PlatformError(
                        "index_unavailable", "The document exceeds indexing bounds.", 422
                    )
                vectors = []
                for start in range(0, len(parts), 16):
                    batch = parts[start : start + 16]
                    if method == "semantic_pgvector":
                        values = await self.embedding.embed([c.text for c in batch])
                        vectors.extend(
                            validate_vectors(values, len(batch), self.settings.embedding_dimensions)
                        )
                    else:
                        vectors.extend([None] * len(batch))
                await self.repository.finish(owner, identifier, generation, parts, vectors)
        except BaseException as error:
            code = error.code if isinstance(error, PlatformError) else "index_failed"
            await self.repository.failed(owner, identifier, generation, code)
            if isinstance(error, PlatformError):
                raise
            if isinstance(error, asyncio.CancelledError):
                raise
            raise PlatformError(
                "index_failed", "Indexing could not complete. Retry explicitly."
            ) from None
        return {"status": "ready", "unchanged": False}

    @span("grounded_answer")
    async def recommend(self, owner, request, context=None):
        if request.mode == "general":
            return (
                await self.answer_service.recommend(request.observation, context=context)
                if context is not None
                else await self.answer_service.recommend(request.observation)
            )
        ids = [UUID(value) for value in request.document_ids]
        # Ownership before consent/provider execution; never broaden selection on failure.
        await self.repository.selection(owner, ids)
        observation = request.observation
        invalid = (
            observation.status != "detected"
            or not observation.question_text
            or observation.question_type == "unknown"
        )
        if observation.question_type in (
            "multiple_choice",
            "true_false",
        ) and observation.required_selection_count not in (None, 1):
            invalid = True
        if observation.question_type in ("multiple_choice", "multiple_select") and (
            not observation.options
            or (
                observation.required_selection_count is not None
                and observation.required_selection_count > len(observation.options)
            )
        ):
            invalid = True
        if invalid:
            return grounded_result(
                observation,
                request.mode,
                Retrieved([], "none", {}),
                limitation="Read a complete, consistent question before using document evidence.",
                reason="observation_incomplete",
            )
        if not request.allow_context_transmission:
            raise PlatformError(
                "context_consent_required",
                "Allow sending selected passages to OpenAI before requesting a grounded answer.",
                409,
            )
        retrieved = await self.retriever.retrieve(owner, ids, request.observation)
        if not retrieved.evidence:
            return grounded_result(
                request.observation,
                request.mode,
                retrieved,
                limitation=retrieved.limitation
                or "No sufficiently relevant passages were found in the selected materials. "
                "Add relevant material or use General explicitly.",
                reason="retrieval_unavailable_or_empty",
            )
        provider = self.answer_service.provider
        try:
            draft = GroundedDraft.model_validate(
                (
                    await provider.recommend_grounded(
                        request.observation,
                        request.mode,
                        retrieved.evidence,
                        **({"context": context} if context is not None else {}),
                    )
                ).model_dump()
            )
            result = grounded_result(request.observation, request.mode, retrieved, draft)
        except (AnswerError, PlatformError):
            raise
        except Exception:
            raise AnswerError(
                "invalid_answer_response", "Source support could not be validated. Try again."
            ) from None
        await self.repository.validate(owner, retrieved.snapshots)
        return result
