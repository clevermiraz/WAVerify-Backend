import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.user import User


class PaymentStatus(StrEnum):
    PAID = "paid"
    REFUNDED = "refunded"
    # Payment took, but the Polar product carried no `plan_slug` we recognise.
    # Nothing was granted and a human has to reconcile it — see
    # `BillingService.record_polar_order`.
    UNMAPPED = "unmapped"


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One settled Polar order.

    This table is the idempotency ledger, not just a receipt. Polar retries a
    webhook up to ten times, and redelivery can be triggered by hand from the
    dashboard, so the same `order.paid` will arrive more than once. The unique
    constraint on `polar_order_id` is what stops the second delivery from
    granting the credits a second time.
    """

    __tablename__ = "payments"

    # The idempotency key. Unique, so a duplicate delivery loses the insert
    # race instead of topping the wallet up again.
    polar_order_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    polar_checkout_id: Mapped[str | None] = mapped_column(String(64), index=True)
    polar_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Null only for UNMAPPED rows, where we could not tell which plan was
    # bought. Keeping the row is the point: the money moved, so it needs a
    # record even though it could not be fulfilled automatically.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        index=True,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=20),
        default=PaymentStatus.PAID,
        nullable=False,
    )
    # What Polar actually charged, which is not `plan.price_cents` when a
    # discount was applied. Stored as charged so finance figures reconcile.
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship()
    plan: Mapped["Plan | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Payment {self.polar_order_id} {self.status}>"


__all__ = ["Payment", "PaymentStatus"]
