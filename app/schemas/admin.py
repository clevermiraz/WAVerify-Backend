import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole
from app.schemas.common import ORMModel


class AdminUserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    company: str | None
    role: UserRole
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    total_lookups: int = 0


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: UserRole | None = None


class AdminApiKeyRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class AdminSubscriptionRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: EmailStr
    plan_name: str
    status: str
    current_period_end: datetime


class AdminSearchLogRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    phone_number: str
    status: str
    source: str
    response_time_ms: int
    created_at: datetime


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    verified_users: int
    total_searches: int
    searches_today: int
    active_api_keys: int
    success_rate: float


class SystemSettings(BaseModel):
    """Read-only view of the runtime configuration, for the admin panel."""

    environment: str
    verification_cache_ttl_seconds: int
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    email_backend: str


class AdminPlanCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    price_cents: int = 0
    currency: str = "USD"
    monthly_request_quota: int | None = None
    rate_limit_per_minute: int = 60
    features: list[str] = []
    is_public: bool = True
    is_active: bool = True
    is_contact_sales: bool = False
    is_recommended: bool = False
    sort_order: int = 0


class AdminPlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price_cents: int | None = None
    currency: str | None = None
    monthly_request_quota: int | None = None
    rate_limit_per_minute: int | None = None
    features: list[str] | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    is_contact_sales: bool | None = None
    is_recommended: bool | None = None
    sort_order: int | None = None
