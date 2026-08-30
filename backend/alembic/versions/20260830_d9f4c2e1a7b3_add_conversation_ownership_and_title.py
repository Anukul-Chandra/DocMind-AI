"""add conversation ownership and title

Scopes conversations and chat messages to their owning user and adds a
server-persisted, nullable conversation title. Existing rows are backfilled
with an empty owner_id and NULL title (the app treats an empty owner as
ownerless until ownership is assigned).

Revision ID: d9f4c2e1a7b3
Revises: b2c3d4e5f601
Create Date: 2026-08-30 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9f4c2e1a7b3"
down_revision: Union[str, None] = "b2c3d4e5f601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "conversations",
        sa.Column("title", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"], unique=False)
    op.add_column(
        "chat_messages",
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(op.f("ix_chat_messages_user_id"), "chat_messages", ["user_id"], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index(op.f("ix_chat_messages_user_id"), table_name="chat_messages")
    op.drop_column("chat_messages", "user_id")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_column("conversations", "title")
    op.drop_column("conversations", "user_id")
