"""Add Google sign-in support to users

Makes `hashed_password` nullable (Google accounts never have one) and adds the
Google `sub` claim as a unique identifier.

Revision ID: 0003_add_google_sign_in
Revises: 0002_add_is_active_recommended
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_google_sign_in"
down_revision: str | None = "0002_add_is_active_recommended"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_users_google_sub", "users", ["google_sub"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
    # Rows with a NULL password are Google-only accounts and cannot be made to
    # satisfy a NOT NULL constraint, so refuse rather than lose them.
    connection = op.get_bind()
    orphans = connection.execute(
        sa.text("SELECT count(*) FROM users WHERE hashed_password IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"{orphans} Google-only account(s) have no password; delete or assign "
            "passwords before downgrading."
        )
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
