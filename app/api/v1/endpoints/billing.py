from fastapi import APIRouter

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import BillingServiceDep
from app.schemas.billing import (
    BillingOverview,
    ChangePlanRequest,
    PlanRead,
    SubscriptionRead,
)

router = APIRouter(tags=["Billing"])


@router.get("/plans", response_model=list[PlanRead], summary="List public plans")
def list_plans(billing: BillingServiceDep) -> list[PlanRead]:
    """Public endpoint — powers the marketing pricing table."""
    return [PlanRead.model_validate(plan) for plan in billing.list_public_plans()]


@router.get("/billing", response_model=BillingOverview)
def billing_overview(user: CurrentUserDep, billing: BillingServiceDep) -> BillingOverview:
    subscription = billing.get_subscription(user.id)
    used = billing.period_usage(user.id, subscription)
    quota = subscription.plan.monthly_request_quota
    return BillingOverview(
        subscription=SubscriptionRead.model_validate(subscription),
        requests_used=used,
        requests_remaining=None if quota is None else max(0, quota - used),
        quota=quota,
    )


@router.post("/billing/plan", response_model=SubscriptionRead)
def change_plan(
    payload: ChangePlanRequest, user: CurrentUserDep, billing: BillingServiceDep
) -> SubscriptionRead:
    """Switch plans.

    No payment is taken — this MVP models the subscription only, so the
    change applies immediately.
    """
    return SubscriptionRead.model_validate(billing.change_plan(user.id, payload.plan_slug))


@router.post("/billing/cancel", response_model=SubscriptionRead)
def cancel_subscription(
    user: CurrentUserDep, billing: BillingServiceDep
) -> SubscriptionRead:
    return SubscriptionRead.model_validate(billing.cancel(user.id))
