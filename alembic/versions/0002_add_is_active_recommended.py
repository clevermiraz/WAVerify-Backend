"""add is_active and is_recommended to plan

Revision ID: 0002_add_is_active_recommended
Revises: a8285b20f7ed
Create Date: 2026-07-26 18:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002_add_is_active_recommended'
down_revision: str | None = 'a8285b20f7ed'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('plans', sa.Column('is_recommended', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('plans', 'is_recommended')
    op.drop_column('plans', 'is_active')
