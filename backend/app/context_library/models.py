from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContextDocument(Base):
    __tablename__ = "context_documents"
    # Async DTO serialization must not issue implicit IO for server-updated timestamps.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("source_type IN ('upload','pasted_text')", name="source_type"),
        CheckConstraint("document_type IN ('pdf','docx','txt')", name="document_type"),
        CheckConstraint(
            "extraction_status IN ('ready','insufficient','failed','deleting')",
            name="extraction_status",
        ),
        CheckConstraint("character_count >= 0 AND byte_size >= 0", name="nonnegative_sizes"),
        CheckConstraint(
            "(source_type = 'upload' AND storage_key IS NOT NULL "
            "AND original_filename IS NOT NULL) OR (source_type = 'pasted_text' "
            "AND storage_key IS NULL AND original_filename IS NULL)",
            name="source_storage",
        ),
        Index("ix_context_documents_owner_created", "owner_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(8))
    source_type: Mapped[str] = mapped_column(String(12))
    storage_key: Mapped[str | None] = mapped_column(String(32), unique=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    extraction_status: Mapped[str] = mapped_column(String(16))
    extraction_error: Mapped[str | None] = mapped_column(String(40))
    extracted_text: Mapped[str] = mapped_column(Text)
    extraction_structure: Mapped[list] = mapped_column(JSONB)
    character_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
