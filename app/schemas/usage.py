from datetime import date

from pydantic import BaseModel

from app.schemas.check import SearchLogRead


class UsagePoint(BaseModel):
    date: date
    total: int
    successful: int
    failed: int


class UsageSummary(BaseModel):
    today_requests: int
    month_requests: int
    quota: int | None
    remaining_credits: int | None
    success_rate: float
    average_response_time_ms: int
    period_start: date
    period_end: date


class UsageOverview(BaseModel):
    summary: UsageSummary
    daily: list[UsagePoint]
    recent: list[SearchLogRead]


class DashboardStats(BaseModel):
    total_searches: int
    numbers_on_whatsapp: int
    success_rate: float
    average_response_time_ms: int
    month_requests: int
    quota: int | None
    remaining_credits: int | None
    active_api_keys: int
    plan_name: str
