"""Usage aggregation for the dashboard and usage pages."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.api_key import ApiKeyRepository
from app.repositories.search_log import SearchLogRepository
from app.repositories.usage import UsageRepository
from app.schemas.check import SearchLogRead
from app.schemas.usage import DashboardStats, UsageOverview, UsagePoint, UsageSummary
from app.services.billing import BillingService

DEFAULT_WINDOW_DAYS = 30


class UsageService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.usage = UsageRepository(session)
        self.logs = SearchLogRepository(session)
        self.api_keys = ApiKeyRepository(session)
        self.billing = BillingService(session)

    def overview(self, user: User, *, days: int = DEFAULT_WINDOW_DAYS) -> UsageOverview:
        today = datetime.now(UTC).date()
        window_start = today - timedelta(days=days - 1)
        subscription = self.billing.get_subscription(user.id)

        summary = self._summary(user.id, today, subscription)
        daily = self._daily_series(user.id, window_start, today)
        recent = [
            SearchLogRead.model_validate(log)
            for log in self.logs.recent_for_user(user.id, limit=10)
        ]
        return UsageOverview(summary=summary, daily=daily, recent=recent)

    def dashboard_stats(self, user: User) -> DashboardStats:
        subscription = self.billing.get_subscription(user.id)
        period_start = subscription.current_period_start.date()
        period_end = subscription.current_period_end.date()

        month_total, month_success, month_time = self.usage.totals_for_range(
            user.id, period_start, period_end
        )
        total_searches = self.logs.count_since(
            datetime.fromtimestamp(0, tz=UTC), user_id=user.id
        )
        quota = subscription.plan.monthly_request_quota

        return DashboardStats(
            total_searches=total_searches,
            numbers_on_whatsapp=self.logs.count_existing_for_user(user.id),
            success_rate=_rate(month_success, month_total),
            average_response_time_ms=_mean(month_time, month_total),
            month_requests=month_total,
            quota=quota,
            remaining_credits=None if quota is None else max(0, quota - month_total),
            active_api_keys=self.api_keys.count_active_for_user(user.id),
            plan_name=subscription.plan.name,
        )

    # --- Internals -------------------------------------------------------

    def _summary(self, user_id: uuid.UUID, today: date, subscription) -> UsageSummary:
        period_start = subscription.current_period_start.date()
        period_end = subscription.current_period_end.date()

        today_stat = self.usage.get_for_day(user_id, today)
        month_total, month_success, month_time = self.usage.totals_for_range(
            user_id, period_start, period_end
        )
        quota = subscription.plan.monthly_request_quota

        return UsageSummary(
            today_requests=today_stat.total_requests if today_stat else 0,
            month_requests=month_total,
            quota=quota,
            remaining_credits=None if quota is None else max(0, quota - month_total),
            success_rate=_rate(month_success, month_total),
            average_response_time_ms=_mean(month_time, month_total),
            period_start=period_start,
            period_end=period_end,
        )

    def _daily_series(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> list[UsagePoint]:
        by_date = {row.date: row for row in self.usage.range_for_user(user_id, start, end)}
        points: list[UsagePoint] = []
        cursor = start
        while cursor <= end:
            row = by_date.get(cursor)
            points.append(
                UsagePoint(
                    date=cursor,
                    total=row.total_requests if row else 0,
                    successful=row.successful_requests if row else 0,
                    failed=row.failed_requests if row else 0,
                )
            )
            cursor += timedelta(days=1)
        return points


def _rate(successful: int, total: int) -> float:
    if not total:
        return 100.0
    return round(successful / total * 100, 2)


def _mean(total_ms: int, total: int) -> int:
    if not total:
        return 0
    return round(total_ms / total)
