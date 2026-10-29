from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LearningSession(Base):
    __tablename__ = "learning_sessions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_learning_sessions_id_owner"),
        CheckConstraint("status IN ('draft','ready','active','ended')", name="status"),
        CheckConstraint("mode IN ('general','context_guided','materials_only')", name="mode"),
        CheckConstraint(
            "purpose IN "
            "('general_learning','certification_practice','interview_preparation','te"
            "chnical_assessment_practice','research_study','custom')",
            name="purpose",
        ),
        CheckConstraint("length(trim(objective)) BETWEEN 1 AND 2000", name="objective"),
        CheckConstraint(
            "(purpose = 'custom' AND custom_purpose IS NOT NULL AND "
            "length(trim(custom_purpose)) BETWEEN 1 AND 100) OR (purpose <> 'custom' "
            "AND custom_purpose IS NULL)",
            name="custom_purpose",
        ),
        CheckConstraint("revision > 0 AND selected_count BETWEEN 0 AND 5", name="bounds"),
        CheckConstraint(
            "(status IN ('draft','ready') AND started_at IS NULL AND ended_at IS "
            "NULL) OR (status = 'active' AND started_at IS NOT NULL AND ended_at IS "
            "NULL) OR (status = 'ended' AND started_at IS NOT NULL AND ended_at IS "
            "NOT NULL)",
            name="lifecycle",
        ),
        Index(
            "uq_learning_active_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_learning_draft_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("status IN ('draft','ready')"),
        ),
        Index("ix_learning_owner_status", "owner_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    purpose: Mapped[str] = mapped_column(String(40))
    custom_purpose: Mapped[str | None] = mapped_column(String(100))
    objective: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    allow_context_transmission: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(8))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionDocument(Base):
    __tablename__ = "learning_session_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "owner_id"],
            ["learning_sessions.id", "learning_sessions.owner_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_documents.id", "context_documents.owner_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("ordinal BETWEEN 0 AND 4", name="ordinal"),
        UniqueConstraint("session_id", "ordinal"),
        Index("ix_learning_documents_owner", "owner_id", "document_id"),
    )
    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
