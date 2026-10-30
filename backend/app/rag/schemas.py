from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.answer.schemas import AnswerRecommendation
from app.schemas import QuestionObservation, StrictModel

Mode = Literal["general", "context_guided", "materials_only"]
DocumentId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")]


class ReasoningRequest(StrictModel):
    observation: QuestionObservation
    mode: Mode
    document_ids: Annotated[list[DocumentId], Field(max_length=5)]
    allow_context_transmission: bool = False

    @model_validator(mode="after")
    def selection(self):
        self.document_ids = [str(UUID(value)) for value in self.document_ids]
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Duplicate documents")
        if self.mode != "general" and not self.document_ids:
            raise ValueError("Select documents")
        return self


class Evidence(StrictModel):
    document_id: str
    document_title: str
    chunk_id: str
    page_number: int | None
    location: str
    excerpt: str


class Support(StrictModel):
    target: Literal["answer", "explanation", "key_point"]
    point_index: Annotated[int, Field(ge=0, le=7)] | None
    chunk_ids: Annotated[list[str], Field(min_length=1, max_length=10)]


class GroundedDraft(StrictModel):
    recommendation: AnswerRecommendation
    sufficient_evidence: bool
    contradictory_evidence: bool
    limitation: Annotated[str, Field(max_length=1500)] = ""
    support: Annotated[list[Support], Field(max_length=20)]
    general_reasoning: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=1200)]], Field(max_length=8)
    ]


class GroundingCheck(StrictModel):
    supported: bool
    contradictory: bool
    limitation: Annotated[str, Field(max_length=1500)]


class Citation(Evidence):
    supports: list[str]


class GroundedAnswer(AnswerRecommendation):
    reasoning_mode: Literal["context_guided", "materials_only"]
    grounding_status: Literal[
        "document_supported", "mixed", "general_reasoning", "insufficient_evidence"
    ]
    retrieval_method: Literal["semantic_pgvector", "lexical", "none"]
    citations: list[Citation]
    general_reasoning: list[str]

    @model_validator(mode="after")
    def attribution(self):
        has_answer = self.status in ("answered", "uncertain")
        if self.grounding_status == "general_reasoning":
            if (
                self.reasoning_mode != "context_guided"
                or self.citations
                or not self.general_reasoning
                or not has_answer
            ):
                raise ValueError("General reasoning must be uncited and explicitly labelled")
        elif self.grounding_status == "insufficient_evidence":
            if (
                self.status != "insufficient_information"
                or self.citations
                or self.general_reasoning
            ):
                raise ValueError("Abstention cannot claim source support")
        elif has_answer and not self.citations:
            raise ValueError("Document attribution requires real citations")
        if self.reasoning_mode == "materials_only" and (
            self.general_reasoning or (has_answer and self.grounding_status != "document_supported")
        ):
            raise ValueError("Materials Only cannot use general reasoning")
        if self.grounding_status == "document_supported" and self.general_reasoning:
            raise ValueError("Mixed support must be labelled mixed")
        return self
