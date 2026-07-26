import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class ApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A hashed API credential. The plaintext is never stored."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    hashed_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    # First few characters of the plaintext, shown in the UI so a user can
    # tell two keys apart without revealing either.
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="api_keys")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ApiKey {self.prefix}… {self.name}>"
