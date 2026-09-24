"""add persisted images to chat messages

Revision ID: 7f3a5b1c9d2e
Revises: 6e2f4c9a1b7d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f3a5b1c9d2e"
down_revision: Union[str, None] = "6e2f4c9a1b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("images", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "images")