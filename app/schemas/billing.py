import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.subscription import SubscriptionStatus
from app.schemas.common import ORMModel


class PlanRead(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    price_cents: int
    currency: str
    monthly_request_quota: int | None
    rate_limit_per_minute: int
    features: list[str]
    is_public: bool
    is_active: bool
    is_contact_sales: bool
    is_recommended: bool
    sort_order: int


class SubscriptionRead(ORMModel):
    id: uuid.UUID
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None
    plan: PlanRead


class ChangePlanRequest(BaseModel):
    plan_slug: str


class BillingOverview(BaseModel):
    subscription: SubscriptionRead
    requests_used: int
    requests_remaining: int | None
    quota: int | None
