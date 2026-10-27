from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentIndex(Base):
    __tablename__ = "context_indexes"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_documents.id", "context_documents.owner_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "owner_id"),
        CheckConstraint("status IN ('indexing','ready','failed')", name="status"),
        CheckConstraint("method IN ('semantic_pgvector','lexical')", name="method"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    generation: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12))
    method: Mapped[str] = mapped_column(String(20))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    dimensions: Mapped[int | None] = mapped_column(Integer)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    chunk_count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "context_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_indexes.document_id", "context_indexes.owner_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "ordinal"),
        CheckConstraint(
            "ordinal >= 0 AND start_offset >= 0 AND end_offset > start_offset", name="offsets"
        ),
        Index("ix_context_chunks_owner_document", "owner_id", "document_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    generation: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSONB)


Index(
    "ix_context_chunks_text",
    func.to_tsvector(text("'simple'::regconfig"), DocumentChunk.content),
    postgresql_using="gin",
)
