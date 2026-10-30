from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.rag.schemas import DocumentId, Mode
from app.schemas import QuestionObservation, StrictModel

Purpose = Literal[
    "general_learning",
    "certification_practice",
    "interview_preparation",
    "technical_assessment_practice",
    "research_study",
    "custom",
]


NewPurpose = Literal["interview_preparation", "research_study", "custom"]
PURPOSE_MAP = {
    "interview_preparation": "interview_preparation",
    "technical_assessment_practice": "interview_preparation",
    "research_study": "research_study",
    "certification_practice": "research_study",
    "general_learning": "custom",
    "custom": "custom",
}
PURPOSE_LABELS = {
    "interview_preparation": "Interview Preparation",
    "research_study": "Research & Study",
    "custom": "General / Custom",
}
DEFAULT_OBJECTIVE = (
    "Help me understand questions and explore useful answers across learning topics and formats."
)


class DraftInput(StrictModel):
    revision: Annotated[int, Field(ge=1, le=2147483646)] | None = None
    purpose: NewPurpose
    custom_purpose: Annotated[str, Field(max_length=100)] | None = None
    objective: Annotated[str, Field(max_length=2000)] = ""
    document_ids: Annotated[list[DocumentId], Field(max_length=5)] = []
    mode: Mode = "general"
    allow_context_transmission: bool = False

    @model_validator(mode="before")
    @classmethod
    def compatible_purpose(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        original = value.get("purpose")
        if isinstance(original, str) and original in PURPOSE_MAP:
            if original != "custom" and value.get("custom_purpose") is not None:
                raise ValueError("Custom purpose belongs only to General / Custom")
            value["purpose"] = PURPOSE_MAP[original]
            if value["purpose"] == "custom" and value.get("custom_purpose") is None:
                value["custom_purpose"] = PURPOSE_LABELS["custom"]
        return value

    @field_validator("objective", "custom_purpose")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Enter readable text")
        return value.strip()

    @model_validator(mode="after")
    def selection(self):
        self.document_ids = [str(UUID(v)) for v in self.document_ids]
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Duplicate selection")
        if not self.objective:
            if self.purpose != "custom":
                raise ValueError("Enter an objective for this purpose")
            self.objective = DEFAULT_OBJECTIVE
        if self.custom_purpose is not None and not self.custom_purpose:
            raise ValueError("Custom purpose must be readable")
        if (self.purpose == "custom") != (self.custom_purpose is not None):
            raise ValueError("Custom purpose required only for custom")
        return self


class Revision(StrictModel):
    revision: Annotated[int, Field(ge=1, le=2147483646)]


class StartInput(Revision):
    preparation_id: DocumentId
    replace_active_id: DocumentId | None = None


class SessionAnswerRequest(StrictModel):
    observation: QuestionObservation
    session_id: DocumentId
    session_revision: Annotated[int, Field(ge=1, le=2147483646)]


class DocumentReference(StrictModel):
    index_generation: DocumentId | None = None
    id: DocumentId
    title: str
    extraction_status: Literal["ready", "insufficient", "failed", "deleting"]
    index_status: Literal["ready", "failed", "indexing", "not_indexed"]


class SessionView(StrictModel):
    id: DocumentId
    revision: int
    purpose: Purpose
    custom_purpose: str | None
    objective: str
    mode: Mode
    document_ids: list[DocumentId]
    documents: list[DocumentReference]
    allow_context_transmission: bool
    status: Literal["draft", "ready", "active", "ended"]
    ready: bool
    issues: list[str]
    missing_document_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class PreparationState(StrictModel):
    draft: SessionView | None
    active: SessionView | None


class LivenessDocument(StrictModel):
    id: DocumentId
    extraction_status: Literal["ready"]
    index_status: Literal["ready"]
    index_generation: DocumentId


class SessionLiveness(StrictModel):
    id: DocumentId
    revision: int
    status: Literal["active"]
    mode: Mode
    ready: Literal[True]
    documents: list[LivenessDocument]
    document_ids: list[DocumentId]
