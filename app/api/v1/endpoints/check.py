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
    summary="Check if a phone number has a WhatsApp account",
    responses={
        401: {"description": "Your API key is missing, wrong, or was deleted"},
        402: {"description": "You have used all the requests in your plan this month"},
        422: {"description": "The phone number is missing, or it is not a real number"},
        429: {"description": "You sent too many requests in one minute"},
        502: {"description": "Our WhatsApp connection is down right now"},
    },
)
def check_number(
    payload: CheckRequest,
    principal: RateLimitedPrincipalDep,
    verification: VerificationServiceDep,
) -> CheckResponse:
    """Check one phone number.

    Send the number in international format: a `+` sign, then the country
    code, then the number. Spaces, dashes and brackets are fine — we remove
    them for you. A number without a country code is rejected; we never guess
    the country.

    Sign the request with an `X-API-Key` header or a Bearer access token.

    A number that has no WhatsApp account is still a successful request: you
    get `200` with `exists: false`. Every request counts as one, whether the
    number was found or not.
    """
    return verification.check(
        user=principal.user,
        raw_phone=payload.phone,
        source=principal.source,
        api_key_id=principal.api_key_id,
        email=payload.email,
    )


@router.get("/searches", response_model=Page[SearchLogRead], tags=["History"])
def list_searches(
    user: CurrentUserDep,
    history: HistoryServiceDep,
    pagination: PaginationDep,
    status: Annotated[
        LookupStatus | None, Query(description="Show only checks with this result.")
    ] = None,
    q: Annotated[
        str | None,
        Query(max_length=20, description="Show only numbers containing this text."),
    ] = None,
) -> Page[SearchLogRead]:
    """List your past checks, one page at a time.

    This shows the checks made by the account you are signed in as.
    """
    return history.list_for_user(
        user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        status=status,
        query=q,
    )
