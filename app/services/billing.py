"""Plans, subscriptions and quota accounting.

No payment gateway is integrated. Plan changes take effect immediately and
the billing period is advanced in-app; a gateway would later own
`current_period_start/end` and the transition to `PAST_DUE`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.plan import Plan, PlanTier
from app.models.subscription import Subscription, SubscriptionStatus
from app.repositories.plan import PlanRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.usage import UsageRepository

logger = get_logger(__name__)

BILLING_PERIOD = timedelta(days=30)


class BillingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.usage = UsageRepository(session)

    # --- Plans -----------------------------------------------------------

    def list_public_plans(self) -> list[Plan]:
        return self.plans.list_public()

    def get_plan(self, slug: PlanTier | str) -> Plan:
        plan = self.plans.get_by_slug(slug)
        if plan is None:
            raise NotFoundError("Plan not found.")
        return plan

    # --- Subscriptions ---------------------------------------------------

    def create_default_subscription(self, user_id: uuid.UUID) -> Subscription:
        """Put a new user on the Free plan."""
        now = datetime.now(UTC)
        return self.subscriptions.create(
            user_id=user_id,
            plan_id=self.get_plan(PlanTier.FREE).id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + BILLING_PERIOD,
        )

    def get_subscription(self, user_id: uuid.UUID) -> Subscription:
        subscription = self.subscriptions.get_for_user(user_id)
        if subscription is None:
            # Self-heal rather than 500: a user without a subscription can
            # otherwise never reach any quota-gated endpoint.
            logger.warning("billing.missing_subscription", user_id=str(user_id))
            subscription = self.create_default_subscription(user_id)
        return self._roll_period_if_elapsed(subscription)

    def change_plan(self, user_id: uuid.UUID, slug: PlanTier) -> Subscription:
        subscription = self.get_subscription(user_id)
        plan = self.get_plan(slug)
        if plan.is_contact_sales:
            raise ValidationError(
                "The Enterprise plan is arranged with our sales team.",
                code="contact_sales_required",
            )

        now = datetime.now(UTC)
        self.subscriptions.update(
            subscription,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            canceled_at=None,
            current_period_start=now,
            current_period_end=now + BILLING_PERIOD,
        )
        logger.info("billing.plan_changed", user_id=str(user_id), plan=plan.slug)
        # `plan` is a joined relationship; refresh so the response reflects
        # the new plan rather than the stale identity-map value.
        self.session.refresh(subscription)
        return subscription

    def cancel(self, user_id: uuid.UUID) -> Subscription:
        """Downgrade to Free. Kept simple: no end-of-period grace handling."""
        subscription = self.get_subscription(user_id)
        now = datetime.now(UTC)
        self.subscriptions.update(
            subscription,
            plan_id=self.get_plan(PlanTier.FREE).id,
            status=SubscriptionStatus.CANCELED,
            canceled_at=now,
        )
        self.session.refresh(subscription)
        return subscription

    def _roll_period_if_elapsed(self, subscription: Subscription) -> Subscription:
        now = datetime.now(UTC)
        if subscription.current_period_end > now:
            return subscription

        # Advance to the period containing `now` so a dormant account does
        # not come back to a long backlog of expired periods.
        start = subscription.current_period_end
        while start + BILLING_PERIOD <= now:
            start += BILLING_PERIOD
        self.subscriptions.update(
            subscription,
            current_period_start=start,
            current_period_end=start + BILLING_PERIOD,
        )
        return subscription

    # --- Quota -----------------------------------------------------------

    def period_usage(self, user_id: uuid.UUID, subscription: Subscription) -> int:
        total, _, _ = self.usage.totals_for_range(
            user_id,
            subscription.current_period_start.date(),
            subscription.current_period_end.date(),
        )
        return total

    def remaining_quota(
        self, user_id: uuid.UUID, subscription: Subscription | None = None
    ) -> int | None:
        """`None` means unmetered."""
        subscription = subscription or self.get_subscription(user_id)
        quota = subscription.plan.monthly_request_quota
        if quota is None:
            return None
        return max(0, quota - self.period_usage(user_id, subscription))
