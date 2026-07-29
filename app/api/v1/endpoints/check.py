import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentUserDep
from app.dependencies.common import PaginationDep
from app.dependencies.rate_limit import RateLimitedPrincipalDep
from app.dependencies.services import HistoryServiceDep, VerificationServiceDep
from app.models.search_log import LookupStatus
from app.schemas.check import (
    CheckRequest,
    CheckResponse,
    EmailCheckRequest,
    EmailCheckResponse,
    SearchLogDetail,
    SearchLogRead,
)
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


@router.post(
    "/check/email",
    response_model=EmailCheckResponse,
    summary="Check an email address on its own",
    responses={
        401: {"description": "Your API key is missing, wrong, or was deleted"},
        422: {"description": "The email is missing or longer than 254 characters"},
        429: {"description": "You sent too many requests in one minute"},
        502: {"description": "Email checking is turned off on this server"},
    },
)
def check_email(
    payload: EmailCheckRequest,
    principal: RateLimitedPrincipalDep,
    verification: VerificationServiceDep,
) -> EmailCheckResponse:
    """Check one email address, with no phone number involved.

    Use this when the email is all you have. You get the same `email_info`
    that `POST /check` returns, plus any public Gravatar profile.

    This never contacts WhatsApp, so it keeps working even when a number
    lookup cannot — and it does not use up any of your monthly requests. Only
    the per-minute rate limit applies.

    A malformed address is a successful request: you get `200` with
    `email_info.syntax_valid: false`, never a `422`.
    """
    return verification.check_email(user=principal.user, raw_email=payload.email)


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


@router.get(
    "/searches/{search_id}",
    response_model=SearchLogDetail,
    tags=["History"],
    responses={404: {"description": "No such check, or it belongs to another account"}},
)
def get_search(
    search_id: uuid.UUID,
    user: CurrentUserDep,
    history: HistoryServiceDep,
) -> SearchLogDetail:
    """Get the full detail of one past check.

    Use this for the history detail view — it returns everything that was found
    for that number at the time: WhatsApp result, number facts and any Gravatar
    profile. You can only read checks made by the account you are signed in as.
    """
    return history.get_for_user(user.id, search_id)
