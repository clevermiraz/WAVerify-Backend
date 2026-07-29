"""add email_info verdict to search_logs

Revision ID: d7b3e5c14a92
Revises: c3f1a6b8d240
Create Date: 2026-07-29 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'd7b3e5c14a92'
down_revision: str | None = 'c3f1a6b8d240'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'search_logs',
        sa.Column('email_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('search_logs', 'email_info')
