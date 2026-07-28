"""add payments table for Polar orders

Revision ID: b1c4f7a92e10
Revises: 9ea9210c6114
Create Date: 2026-07-28 10:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b1c4f7a92e10'
down_revision: str | None = '9ea9210c6114'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("polar_order_id", sa.String(length=64), nullable=False),
        sa.Column("polar_checkout_id", sa.String(length=64), nullable=True),
        sa.Column("polar_customer_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    # The unique index is the idempotency guarantee, not an optimisation:
    # it is what stops a redelivered `order.paid` granting credits twice.
    op.create_index(
        "ix_payments_polar_order_id", "payments", ["polar_order_id"], unique=True
    )
    op.create_index("ix_payments_polar_checkout_id", "payments", ["polar_checkout_id"])
    op.create_index("ix_payments_polar_customer_id", "payments", ["polar_customer_id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_plan_id", "payments", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_plan_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_polar_customer_id", table_name="payments")
    op.drop_index("ix_payments_polar_checkout_id", table_name="payments")
    op.drop_index("ix_payments_polar_order_id", table_name="payments")
    op.drop_table("payments")
