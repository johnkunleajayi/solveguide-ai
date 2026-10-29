"""Owned preparation and bounded learning-session lifecycle metadata only."""

import sqlalchemy as sa
from alembic import op

revision = "0004_session_preparation"
down_revision = "0003_context_rag"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("custom_purpose", sa.String(100)),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("allow_context_transmission", sa.Boolean(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_learning_sessions"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_learning_sessions_owner_id_users",
        ),
        sa.UniqueConstraint("id", "owner_id", name="uq_learning_sessions_id_owner"),
        sa.CheckConstraint(
            "status IN ('draft','ready','active','ended')", name=op.f("ck_learning_sessions_status")
        ),
        sa.CheckConstraint(
            "mode IN ('general','context_guided','materials_only')",
            name=op.f("ck_learning_sessions_mode"),
        ),
        sa.CheckConstraint(
            "purpose IN "
            "('general_learning','certification_practice','interview_preparation','te"
            "chnical_assessment_practice','research_study','custom')",
            name=op.f("ck_learning_sessions_purpose"),
        ),
        sa.CheckConstraint(
            "length(trim(objective)) BETWEEN 1 AND 2000",
            name=op.f("ck_learning_sessions_objective"),
        ),
        sa.CheckConstraint(
            "(purpose = 'custom' AND custom_purpose IS NOT NULL AND "
            "length(trim(custom_purpose)) BETWEEN 1 AND 100) OR (purpose <> 'custom' "
            "AND custom_purpose IS NULL)",
            name=op.f("ck_learning_sessions_custom_purpose"),
        ),
        sa.CheckConstraint(
            "revision > 0 AND selected_count BETWEEN 0 AND 5",
            name=op.f("ck_learning_sessions_bounds"),
        ),
        sa.CheckConstraint(
            "(status IN ('draft','ready') AND started_at IS NULL AND ended_at IS "
            "NULL) OR (status = 'active' AND started_at IS NOT NULL AND ended_at IS "
            "NULL) OR (status = 'ended' AND started_at IS NOT NULL AND ended_at IS "
            "NOT NULL)",
            name=op.f("ck_learning_sessions_lifecycle"),
        ),
    )
    op.create_index(
        "uq_learning_active_owner",
        "learning_sessions",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_learning_draft_owner",
        "learning_sessions",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft','ready')"),
    )
    op.create_index("ix_learning_owner_status", "learning_sessions", ["owner_id", "status"])
    op.create_table(
        "learning_session_documents",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "document_id", name="pk_learning_session_documents"),
        sa.ForeignKeyConstraint(
            ["session_id", "owner_id"],
            ["learning_sessions.id", "learning_sessions.owner_id"],
            ondelete="CASCADE",
            name="fk_learning_session_documents_session_id_learning_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_documents.id", "context_documents.owner_id"],
            ondelete="CASCADE",
            name="fk_learning_session_documents_document_id_context_documents",
        ),
        sa.UniqueConstraint(
            "session_id", "ordinal", name="uq_learning_session_documents_session_id"
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 0 AND 4", name=op.f("ck_learning_session_documents_ordinal")
        ),
    )
    op.create_index(
        "ix_learning_documents_owner", "learning_session_documents", ["owner_id", "document_id"]
    )


def downgrade():
    op.drop_index("ix_learning_documents_owner", table_name="learning_session_documents")
    op.drop_table("learning_session_documents")
    op.drop_index("ix_learning_owner_status", table_name="learning_sessions")
    op.drop_index("uq_learning_draft_owner", table_name="learning_sessions")
    op.drop_index("uq_learning_active_owner", table_name="learning_sessions")
    op.drop_table("learning_sessions")
