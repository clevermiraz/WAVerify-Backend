from fastapi import APIRouter

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import BillingServiceDep
from app.schemas.billing import (
    BillingOverview,
    TopUpRequest,
    PlanRead,
    WalletRead,
)

router = APIRouter(tags=["Billing"])


@router.get("/plans", response_model=list[PlanRead], summary="List public plans")
def list_plans(billing: BillingServiceDep) -> list[PlanRead]:
    """Public endpoint — powers the marketing pricing table."""
    return [PlanRead.model_validate(plan) for plan in billing.list_public_plans()]


@router.get("/billing", response_model=BillingOverview)
def billing_overview(user: CurrentUserDep, billing: BillingServiceDep) -> BillingOverview:
    wallet = billing.get_wallet(user.id)
    from datetime import UTC, datetime
    today = datetime.now(UTC).date()
    today_stat = billing.usage.get_for_day(user.id, today)
    used_today = today_stat.total_requests if today_stat else 0
    return BillingOverview(
        wallet=WalletRead.model_validate(wallet),
        requests_used_today=used_today,
        requests_remaining=wallet.credits_balance,
    )


@router.post("/billing/topup", response_model=WalletRead)
def top_up(
    payload: TopUpRequest, user: CurrentUserDep, billing: BillingServiceDep
) -> WalletRead:
    """Buy a credit pack."""
    return WalletRead.model_validate(billing.top_up_wallet(user.id, payload.plan_slug))
