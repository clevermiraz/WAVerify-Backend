from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.search_log import SearchLog
    from app.models.wallet import Wallet


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Null for accounts created through Google, which never have a local
    # password. Every read has to tolerate that — see `has_password`.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google's `sub` claim: stable per (user, OAuth client) and immutable, so
    # it survives the user changing their Google email address.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    full_name: Mapped[str | None] = mapped_column(String(150))
    company: Mapped[str | None] = mapped_column(String(150))

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wallet: Mapped["Wallet | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    search_logs: Mapped[list["SearchLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    @property
    def has_password(self) -> bool:
        """False for Google-only accounts, which cannot use password flows."""
        return self.hashed_password is not None

    @property
    def has_google(self) -> bool:
        return self.google_sub is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email}>"


__all__ = ["User", "UserRole"]
