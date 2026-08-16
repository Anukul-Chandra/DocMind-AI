"""fix postgres data parity

Adds the documents columns (``classification``, ``extracted_data``) and the
request_logs columns (``method``, ``path``, ``status_code``, ``user_id``)
that the application already reads and writes but that the initial schema
never created. All new columns are added with server defaults (or nullable)
so a populated existing database upgrades safely.

Revision ID: c7a9d31e5b42
Revises: 929856ee0161
Create Date: 2026-08-16 18:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a9d31e5b42'
down_revision: Union[str, None] = '929856ee0161'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration.

    ``classification`` mirrors the JSON registry's ``unknown`` default and the
    ORM's server default; ``extracted_data`` is optional JSON. The request-log
    columns mirror the ORM's empty defaults. Server defaults make the columns
    safe to add to tables that already contain rows.
    """
    op.add_column(
        'documents',
        sa.Column(
            'classification',
            sa.String(length=64),
            nullable=False,
            server_default='unknown',
        ),
    )
    op.add_column(
        'documents',
        sa.Column('extracted_data', sa.JSON(), nullable=True),
    )
    op.add_column(
        'request_logs',
        sa.Column('method', sa.String(length=16), nullable=False, server_default=''),
    )
    op.add_column(
        'request_logs',
        sa.Column('path', sa.String(length=1024), nullable=False, server_default=''),
    )
    op.add_column(
        'request_logs',
        sa.Column('status_code', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'request_logs',
        sa.Column('user_id', sa.String(length=64), nullable=False, server_default=''),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_column('request_logs', 'user_id')
    op.drop_column('request_logs', 'status_code')
    op.drop_column('request_logs', 'path')
    op.drop_column('request_logs', 'method')
    op.drop_column('documents', 'extracted_data')
    op.drop_column('documents', 'classification')