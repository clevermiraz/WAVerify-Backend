from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WhatsAppAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "whatsapp_accounts"

    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="initializing", nullable=False)
    total_lookups_performed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lookups_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<WhatsAppAccount {self.id}>"

__all__ = ["WhatsAppAccount"]
