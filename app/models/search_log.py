import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class LookupStatus(StrEnum):
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    FAILED = "failed"


class LookupSource(StrEnum):
    DASHBOARD = "dashboard"
    API = "api"


class SearchLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One verification attempt. Backs both search history and usage stats."""

    __tablename__ = "search_logs"
    __table_args__ = (
        Index("ix_search_logs_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
    )

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(4))

    status: Mapped[LookupStatus] = mapped_column(
        Enum(LookupStatus, name="lookup_status", native_enum=False, length=20),
        nullable=False,
    )
    source: Mapped[LookupSource] = mapped_column(
        Enum(LookupSource, name="lookup_source", native_enum=False, length=20),
        default=LookupSource.DASHBOARD,
        nullable=False,
    )

    exists_on_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    display_name: Mapped[str | None] = mapped_column(String(150))
    about: Mapped[str | None] = mapped_column(String(255))
    is_business: Mapped[bool | None] = mapped_column(Boolean)
    profile_photo_url: Mapped[str | None] = mapped_column(String(2048))

    # Enrichment snapshots stored as-returned, so history shows exactly what the
    # caller saw. number_info is derived from the phone (always available, even
    # for failures); email_info is set whenever an email was supplied, whether
    # or not it verified; gravatar only when that email had a public profile.
    number_info: Mapped[dict | None] = mapped_column(JSONB)
    email_info: Mapped[dict | None] = mapped_column(JSONB)
    gravatar: Mapped[dict | None] = mapped_column(JSONB)

    response_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))

    user: Mapped["User"] = relationship(back_populates="search_logs")

    @property
    def succeeded(self) -> bool:
        return self.status is not LookupStatus.FAILED
