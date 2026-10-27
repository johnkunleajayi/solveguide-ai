from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Title(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Enter a title without control characters")
        return value


class PastedDocument(Title):
    text: str = Field(min_length=1, max_length=1_000_000)


class Segment(BaseModel):
    kind: Literal["page", "paragraph", "table", "text"]
    number: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    original_filename: str | None
    document_type: Literal["pdf", "docx", "txt"]
    source_type: Literal["upload", "pasted_text"]
    byte_size: int
    extraction_status: Literal["ready", "insufficient", "failed", "deleting"]
    extraction_error: str | None
    character_count: int
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    extracted_text: str
    extraction_structure: list[Segment]


class DocumentPage(BaseModel):
    documents: list[DocumentSummary]
    next_cursor: str | None
