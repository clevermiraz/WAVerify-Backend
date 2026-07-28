import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class PlanRead(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    price_cents: int
    currency: str
    credits_awarded: int | None
    rate_limit_per_minute: int
    features: list[str]
    is_public: bool
    is_active: bool
    is_contact_sales: bool
    is_recommended: bool
    sort_order: int


class WalletRead(ORMModel):
    id: uuid.UUID
    credits_balance: int
    plan: PlanRead


class TopUpRequest(BaseModel):
    plan_slug: str


class BillingOverview(BaseModel):
    wallet: WalletRead
    requests_used_today: int
    requests_remaining: int | None


class CheckoutRequest(BaseModel):
    plan_slug: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class InvoiceResponse(BaseModel):
    """`url` is null while Polar is still building the PDF."""

    status: Literal["ready", "generating"]
    url: str | None = None


class PaymentRead(ORMModel):
    id: uuid.UUID
    status: str
    amount_cents: int
    currency: str
    credits_granted: int
    created_at: datetime
    plan: PlanRead | None
