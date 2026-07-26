from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import UsageServiceDep
from app.schemas.usage import DashboardStats, UsageOverview

router = APIRouter(tags=["Usage"])


@router.get("/usage", response_model=UsageOverview)
def usage_overview(
    user: CurrentUserDep,
    service: UsageServiceDep,
    days: Annotated[int, Query(ge=7, le=90, description="Size of the daily series.")] = 30,
) -> UsageOverview:
    return service.overview(user, days=days)


@router.get("/dashboard/stats", response_model=DashboardStats, tags=["Dashboard"])
def dashboard_stats(user: CurrentUserDep, service: UsageServiceDep) -> DashboardStats:
    return service.dashboard_stats(user)
