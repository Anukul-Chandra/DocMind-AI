"""add document ownership

Revision ID: 929856ee0161
Revises: 081ffd9766a9
Create Date: 2026-08-13 17:10:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '929856ee0161'
down_revision: Union[str, None] = '081ffd9766a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    op.add_column(
        'documents',
        sa.Column('owner_id', sa.String(length=64), nullable=False, server_default=''),
    )
    op.create_index(op.f('ix_documents_owner_id'), 'documents', ['owner_id'], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index(op.f('ix_documents_owner_id'), table_name='documents')
    op.drop_column('documents', 'owner_id')