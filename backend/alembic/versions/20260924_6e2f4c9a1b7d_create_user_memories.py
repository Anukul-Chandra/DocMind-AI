"""create persistent user memories

Revision ID: 6e2f4c9a1b7d
Revises: d9f4c2e1a7b3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6e2f4c9a1b7d"
down_revision: Union[str, None] = "d9f4c2e1a7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("memory_key", sa.String(length=128), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "memory_key", name="uq_user_memories_user_key"),
    )
    op.create_index(
        "ix_user_memories_user_id", "user_memories", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_table("user_memories")