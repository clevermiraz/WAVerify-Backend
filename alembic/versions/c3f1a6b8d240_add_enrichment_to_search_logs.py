"""add number_info and gravatar enrichment to search_logs

Revision ID: c3f1a6b8d240
Revises: b1c4f7a92e10
Create Date: 2026-07-29 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'c3f1a6b8d240'
down_revision: str | None = 'b1c4f7a92e10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'search_logs',
        sa.Column('number_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'search_logs',
        sa.Column('gravatar', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('search_logs', 'gravatar')
    op.drop_column('search_logs', 'number_info')
