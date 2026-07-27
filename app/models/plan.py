from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.wallet import Wallet


class PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"


class Plan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A purchasable tier. Seeded from `app.db.init_db`."""

    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(
        String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Stored in cents to keep money arithmetic in integers.
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # `None` means "unmetered" and is used by the Enterprise tier.
    credits_awarded: Mapped[int | None] = mapped_column(Integer)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    features: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False)
    is_contact_sales: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    wallets: Mapped[list["Wallet"]] = relationship(back_populates="plan")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Plan {self.slug}>"
