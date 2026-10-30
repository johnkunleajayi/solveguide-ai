import hashlib
import json
import re
from dataclasses import dataclass

from app.diagnostics import emit, span
from app.rag.schemas import Evidence

STOP = set(
    "a an the is are was were what which how why when to of in on for and or with by "
    "from does do should can this that be use select choose answer".split()
)


def lexical_query(value):
    words = sorted(
        {word for word in re.findall(r"\w{2,}", value.casefold()) if len(word) <= 64} - STOP
    )[:64]
    return " | ".join(words)


def bounded_evidence(rows, settings, method):
    result, seen, spans, budget = [], set(), {}, settings.rag_context_tokens
    for chunk, title, score in rows:
        if score < (settings.rag_semantic_threshold if method == "semantic_pgvector" else 0.02):
            continue
        digest = hashlib.sha256(chunk.content.strip().encode()).digest()
        overlap = any(
            max(0, min(end, chunk.end_offset) - max(start, chunk.start_offset))
            > len(chunk.content) / 2
            for start, end in spans.get(chunk.document_id, [])
        )
        if digest in seen or overlap:
            continue
        # UTF-8 bytes are a conservative upper bound on byte-BPE tokens, including
        # metadata allowance. Never truncate a passage and keep its original citation.
        candidate = Evidence(
            document_id=str(chunk.document_id),
            document_title=title,
            chunk_id=str(chunk.id),
            page_number=chunk.page_number,
            location=chunk.location,
            excerpt=chunk.content,
        )
        cost = len(json.dumps(candidate.model_dump(), ensure_ascii=False).encode()) + 100
        if cost > budget:
            continue
        result.append(candidate)
        seen.add(digest)
        spans.setdefault(chunk.document_id, []).append((chunk.start_offset, chunk.end_offset))
        budget -= cost
        if len(result) >= settings.rag_top_k:
            break
    return result


@dataclass(frozen=True)
class Retrieved:
    evidence: list[Evidence]
    method: str
    snapshots: dict
    limitation: str | None = None


class Retriever:
    def __init__(self, repository, embedding, settings):
        self.repository, self.embedding, self.settings = repository, embedding, settings

    @span("retrieval")
    async def retrieve(self, owner, identifiers, observation):
        documents, indexes = await self.repository.selection(owner, identifiers)
        snapshots = {i.document_id: i.generation for i in indexes}
        if (
            len(indexes) != len(identifiers)
            or any(i.status != "ready" for i in indexes)
            or any(d.extraction_status != "ready" for d in documents)
        ):
            emit(
                "retrieval_decision",
                outcome="unavailable",
                reason="index_or_extraction_not_ready",
                selected_count=len(identifiers),
            )
            return Retrieved(
                [],
                "none",
                {},
                "Select ready, indexed documents. Unavailable or incomplete extraction "
                "cannot support an answer.",
            )
        semantic = (
            all(i.method == "semantic_pgvector" for i in indexes)
            and await self.repository.vector_available()
        )
        if semantic and any(
            i.embedding_model != self.settings.openai_embedding_model
            or i.dimensions != self.settings.embedding_dimensions
            for i in indexes
        ):
            emit(
                "retrieval_decision",
                outcome="unavailable",
                reason="embedding_configuration_changed",
                selected_count=len(identifiers),
            )
            return Retrieved(
                [],
                "none",
                {},
                "The embedding configuration changed. Reindex the selected documents.",
            )
        query_parts = [observation.question_text or "", *(o.text for o in observation.options)]
        # Formulas/code/supporting context can be separate from the question sentence.
        # This query remains ephemeral, bounded, and never includes the screenshot.
        for element in getattr(observation, "visual_elements", []):
            query_parts.extend([element.description, element.text or "", element.language or ""])
        query_parts.extend(getattr(observation, "visible_context", []))
        query = "\n".join(query_parts).encode()[:6000].decode("utf-8", errors="ignore")
        vector = (await self.embedding.embed([query]))[0] if semantic else None
        method = "semantic_pgvector" if semantic else "lexical"
        terms = query if semantic else lexical_query(query)
        if not terms:
            emit(
                "retrieval_decision",
                outcome="empty",
                reason="no_searchable_terms",
                selected_count=len(identifiers),
            )
            return Retrieved([], "none", snapshots, "No searchable question terms were available.")
        await self.repository.validate(owner, snapshots)
        rows = await self.repository.rank(owner, identifiers, method, terms, vector)
        await self.repository.validate(owner, snapshots)
        evidence = bounded_evidence(rows, self.settings, method)
        emit(
            "retrieval_decision",
            outcome="retrieved" if evidence else "empty",
            reason="relevant_passages" if evidence else "no_relevant_passages",
            method=method,
            selected_count=len(identifiers),
            evidence_count=len(evidence),
        )
        return Retrieved(evidence, method, snapshots)
