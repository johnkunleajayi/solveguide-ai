"""Versioned owned indexes and chunks, with optional pgvector exact distance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_context_rag"
down_revision = "0002_context_library"
branch_labels = None
depends_on = None


def upgrade():
    # Extension installation is optional: ordinary PostgreSQL still supports lexical search.
    # Keep it after downgrade because other applications may use this shared extension.
    op.execute("""DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        BEGIN CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN NULL;
        END;
    END IF; END $$;""")
    op.create_unique_constraint(
        "uq_context_documents_id_owner", "context_documents", ["id", "owner_id"]
    )
    op.create_table(
        "context_indexes",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("dimensions", sa.Integer()),
        sa.Column("consent_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("document_id", name="pk_context_indexes"),
        sa.UniqueConstraint("document_id", "owner_id", name="uq_context_indexes_document_id"),
        sa.ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_documents.id", "context_documents.owner_id"],
            ondelete="CASCADE",
            name="fk_context_indexes_document_id_context_documents",
        ),
        sa.CheckConstraint(
            "status IN ('indexing','ready','failed')", name=op.f("ck_context_indexes_status")
        ),
        sa.CheckConstraint(
            "method IN ('semantic_pgvector','lexical')", name=op.f("ck_context_indexes_method")
        ),
    )
    op.create_index("ix_context_indexes_owner_id", "context_indexes", ["owner_id"])
    op.create_table(
        "context_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("location", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB()),
        sa.PrimaryKeyConstraint("id", name="pk_context_chunks"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_context_chunks_document_id"),
        sa.ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["context_indexes.document_id", "context_indexes.owner_id"],
            ondelete="CASCADE",
            name="fk_context_chunks_document_id_context_indexes",
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND start_offset >= 0 AND end_offset > start_offset",
            name=op.f("ck_context_chunks_offsets"),
        ),
    )
    op.create_index(
        "ix_context_chunks_owner_document", "context_chunks", ["owner_id", "document_id"]
    )
    op.create_index(
        "ix_context_chunks_text",
        "context_chunks",
        [sa.text("to_tsvector('simple'::regconfig, content)")],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("ix_context_chunks_text", table_name="context_chunks")
    op.drop_index("ix_context_chunks_owner_document", table_name="context_chunks")
    op.drop_table("context_chunks")
    op.drop_index("ix_context_indexes_owner_id", table_name="context_indexes")
    op.drop_table("context_indexes")
    op.drop_constraint("uq_context_documents_id_owner", "context_documents", type_="unique")
