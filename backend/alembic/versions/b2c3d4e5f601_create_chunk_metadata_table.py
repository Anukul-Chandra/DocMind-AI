"""create chunk_metadata table for postgres metadata backend

Adds the ``chunk_metadata`` table used by the optional Postgres/pgvector
``MetadataBackend`` implementation. It stores the same logical fields as the
JSON ``MetadataStore`` (id, workspace_id, filename, chunk_id, document_id,
owner_id, text) plus a gapless 0-based ``chunk_index`` that aligns with
``vector_chunks.chunk_index`` in the companion vector backend. The JSON ``id``
is derived as ``chunk_index + 1`` for drop-in compatibility.

The application keeps using FAISS + JSON until the persistence backend is
switched to ``postgres``; this migration only prepares the schema.

Revision ID: b2c3d4e5f601
Revises: a1b2c3d4e5f6
Create Date: 2026-08-16 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f601"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the chunk_metadata table."""
    op.create_table(
        "chunk_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column("chunk_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("filename", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "owner_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chunk_metadata_chunk_index", "chunk_metadata", ["chunk_index"], unique=True
    )
    op.create_index(
        "ix_chunk_metadata_document_id", "chunk_metadata", ["document_id"]
    )
    op.create_index("ix_chunk_metadata_owner_id", "chunk_metadata", ["owner_id"])
    op.create_index(
        "ix_chunk_metadata_workspace_id", "chunk_metadata", ["workspace_id"]
    )


def downgrade() -> None:
    """Drop the chunk_metadata table."""
    op.drop_index("ix_chunk_metadata_workspace_id", table_name="chunk_metadata")
    op.drop_index("ix_chunk_metadata_owner_id", table_name="chunk_metadata")
    op.drop_index("ix_chunk_metadata_document_id", table_name="chunk_metadata")
    op.drop_index("ix_chunk_metadata_chunk_index", table_name="chunk_metadata")
    op.drop_table("chunk_metadata")
