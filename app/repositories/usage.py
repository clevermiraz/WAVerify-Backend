import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.usage_statistic import UsageStatistic
from app.repositories.base import BaseRepository


class UsageRepository(BaseRepository[UsageStatistic]):
    model = UsageStatistic

    def record(
        self,
        *,
        user_id: uuid.UUID,
        day: date,
        succeeded: bool,
        response_time_ms: int,
    ) -> None:
        """Increment today's counters.

        An UPSERT keeps this correct under concurrent requests from the same
        user, which a read-modify-write would not.
        """
        stmt = (
            insert(UsageStatistic)
            .values(
                user_id=user_id,
                date=day,
                total_requests=1,
                successful_requests=1 if succeeded else 0,
                failed_requests=0 if succeeded else 1,
                total_response_time_ms=response_time_ms,
            )
            .on_conflict_do_update(
                constraint="uq_usage_statistics_user_date",
                set_={
                    "total_requests": UsageStatistic.total_requests + 1,
                    "successful_requests": UsageStatistic.successful_requests
                    + (1 if succeeded else 0),
                    "failed_requests": UsageStatistic.failed_requests
                    + (0 if succeeded else 1),
                    "total_response_time_ms": UsageStatistic.total_response_time_ms
                    + response_time_ms,
                },
            )
        )
        self.session.execute(stmt)

    def get_for_day(self, user_id: uuid.UUID, day: date) -> UsageStatistic | None:
        stmt = select(UsageStatistic).where(
            UsageStatistic.user_id == user_id, UsageStatistic.date == day
        )
        return self.session.scalars(stmt).first()

    def range_for_user(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> list[UsageStatistic]:
        stmt = (
            select(UsageStatistic)
            .where(
                UsageStatistic.user_id == user_id,
                UsageStatistic.date >= start,
                UsageStatistic.date <= end,
            )
            .order_by(UsageStatistic.date.asc())
        )
        return list(self.session.scalars(stmt))

    def totals_for_range(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> tuple[int, int, int]:
        """Return `(total, successful, total_response_time_ms)` for the range."""
        row = self.session.execute(
            select(
                func.coalesce(func.sum(UsageStatistic.total_requests), 0),
                func.coalesce(func.sum(UsageStatistic.successful_requests), 0),
                func.coalesce(func.sum(UsageStatistic.total_response_time_ms), 0),
            ).where(
                UsageStatistic.user_id == user_id,
                UsageStatistic.date >= start,
                UsageStatistic.date <= end,
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])
