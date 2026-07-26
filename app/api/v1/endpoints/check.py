from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentUserDep
from app.dependencies.common import PaginationDep
from app.dependencies.rate_limit import RateLimitedPrincipalDep
from app.dependencies.services import HistoryServiceDep, VerificationServiceDep
from app.models.search_log import LookupStatus
from app.schemas.check import CheckRequest, CheckResponse, SearchLogRead
from app.schemas.common import Page

router = APIRouter(tags=["Verification"])


@router.post(
    "/check",
    response_model=CheckResponse,
    summary="Check whether a phone number has a WhatsApp account",
    responses={
        401: {"description": "Missing or invalid credentials"},
        402: {"description": "Monthly quota exhausted"},
        422: {"description": "Invalid phone number"},
        429: {"description": "Rate limit exceeded"},
        502: {"description": "Verification provider unavailable"},
    },
)
def check_number(
    payload: CheckRequest,
    principal: RateLimitedPrincipalDep,
    verification: VerificationServiceDep,
) -> CheckResponse:
    """Verify a single number.

    Authenticate with an `X-API-Key` header or a Bearer access token. Each
    call consumes one request from the plan's monthly quota.
    """
    return verification.check(
        user=principal.user,
        raw_phone=payload.phone,
        source=principal.source,
        api_key_id=principal.api_key_id,
    )


@router.get("/searches", response_model=Page[SearchLogRead], tags=["History"])
def list_searches(
    user: CurrentUserDep,
    history: HistoryServiceDep,
    pagination: PaginationDep,
    status: Annotated[LookupStatus | None, Query(description="Filter by outcome.")] = None,
    q: Annotated[
        str | None, Query(max_length=20, description="Phone number contains.")
    ] = None,
) -> Page[SearchLogRead]:
    """Paginated search history for the signed-in user."""
    return history.list_for_user(
        user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        status=status,
        query=q,
    )
