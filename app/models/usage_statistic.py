import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UsageStatistic(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-user, per-day request rollup.

    Denormalised on purpose: usage dashboards and quota checks read this
    instead of aggregating `search_logs`, which keeps them cheap as the log
    table grows.
    """

    __tablename__ = "usage_statistics"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_usage_statistics_user_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Running sum, divided by `total_requests` to get the mean without
    # keeping every sample around.
    total_response_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def average_response_time_ms(self) -> int:
        if not self.total_requests:
            return 0
        return round(self.total_response_time_ms / self.total_requests)
