"""Owned reusable materials only; live learning content remains ephemeral."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_context_library"
down_revision = "0001_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "context_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("document_type", sa.String(8), nullable=False),
        sa.Column("source_type", sa.String(12), nullable=False),
        sa.Column("storage_key", sa.String(32)),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("extraction_status", sa.String(16), nullable=False),
        sa.Column("extraction_error", sa.String(40)),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("extraction_structure", postgresql.JSONB(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_context_documents"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_context_documents_owner_id_users",
        ),
        sa.UniqueConstraint("storage_key", name="uq_context_documents_storage_key"),
        sa.CheckConstraint(
            "source_type IN ('upload','pasted_text')", name=op.f("ck_context_documents_source_type")
        ),
        sa.CheckConstraint(
            "document_type IN ('pdf','docx','txt')", name=op.f("ck_context_documents_document_type")
        ),
        sa.CheckConstraint(
            "extraction_status IN ('ready','insufficient','failed','deleting')",
            name=op.f("ck_context_documents_extraction_status"),
        ),
        sa.CheckConstraint(
            "character_count >= 0 AND byte_size >= 0",
            name=op.f("ck_context_documents_nonnegative_sizes"),
        ),
        sa.CheckConstraint(
            "(source_type = 'upload' AND storage_key IS NOT NULL "
            "AND original_filename IS NOT NULL) OR (source_type = 'pasted_text' "
            "AND storage_key IS NULL AND original_filename IS NULL)",
            name=op.f("ck_context_documents_source_storage"),
        ),
    )
    op.create_index(
        "ix_context_documents_owner_created", "context_documents", ["owner_id", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_context_documents_owner_created", table_name="context_documents")
    op.drop_table("context_documents")
