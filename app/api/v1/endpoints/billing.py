import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from polar_sdk.webhooks import (
    WebhookUnknownTypeError,
    WebhookVerificationError,
    validate_event,
)

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import BillingServiceDep, PolarServiceDep
from app.schemas.billing import (
    BillingOverview,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceResponse,
    PaymentRead,
    PlanRead,
    PortalResponse,
    WalletRead,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Billing"])


@router.get("/plans", response_model=list[PlanRead], summary="List public plans")
def list_plans(billing: BillingServiceDep) -> list[PlanRead]:
    """Public endpoint — powers the marketing pricing table."""
    return [PlanRead.model_validate(plan) for plan in billing.list_public_plans()]


@router.get("/billing", response_model=BillingOverview)
def billing_overview(user: CurrentUserDep, billing: BillingServiceDep) -> BillingOverview:
    wallet = billing.get_wallet(user.id)
    today = datetime.now(UTC).date()
    today_stat = billing.usage.get_for_day(user.id, today)
    used_today = today_stat.total_requests if today_stat else 0
    return BillingOverview(
        wallet=WalletRead.model_validate(wallet),
        requests_used_today=used_today,
        requests_remaining=wallet.credits_balance,
    )


@router.get("/billing/payments", response_model=list[PaymentRead])
def list_payments(user: CurrentUserDep, billing: BillingServiceDep) -> list[PaymentRead]:
    """Purchase history for the signed-in user."""
    rows, _ = billing.payments.list_for_user(user.id)
    return [PaymentRead.model_validate(row) for row in rows]


@router.post("/billing/portal", response_model=PortalResponse)
def create_portal_session(
    user: CurrentUserDep, polar: PolarServiceDep
) -> PortalResponse:
    """Open Polar's customer portal, where the buyer manages their own
    invoices and billing details. 404s until they have bought something."""
    return PortalResponse(portal_url=polar.customer_portal_url(user))


@router.get("/billing/payments/{payment_id}/invoice", response_model=InvoiceResponse)
def get_invoice(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    billing: BillingServiceDep,
    polar: PolarServiceDep,
) -> InvoiceResponse:
    """Link to a purchase's PDF invoice.

    Answers `generating` on the first call for an order, because Polar builds
    the PDF asynchronously — the client polls until `ready`.
    """
    payment = billing.payments.get(payment_id)
    # A missing row and someone else's row are answered identically, so this
    # cannot be used to probe which payment ids exist.
    if payment is None or payment.user_id != user.id:
        raise NotFoundError("Purchase not found.")

    url = polar.invoice_url(payment.polar_order_id)
    if url is None:
        return InvoiceResponse(status="generating")
    return InvoiceResponse(status="ready", url=url)


@router.post("/billing/checkout", response_model=CheckoutResponse)
def create_checkout(
    payload: CheckoutRequest,
    user: CurrentUserDep,
    billing: BillingServiceDep,
    polar: PolarServiceDep,
) -> CheckoutResponse:
    """Open a Polar checkout for a credit pack.

    Nothing is granted here. Credits are added only when Polar confirms the
    payment on `POST /billing/polar/webhook`.
    """
    plan = billing.purchasable_plan(payload.plan_slug)
    return CheckoutResponse(checkout_url=polar.create_checkout(user, plan))


@router.post(
    "/billing/polar/webhook",
    include_in_schema=False,
    status_code=status.HTTP_202_ACCEPTED,
)
async def polar_webhook(request: Request, billing: BillingServiceDep) -> Response:
    """Fulfilment callback from Polar. Unauthenticated by design — the
    signature over the raw body is what proves the caller is Polar.

    Answering non-2xx makes Polar retry, up to ten times, and it disables the
    endpoint after ten consecutive failures. So only genuinely transient
    problems are allowed to raise; anything a retry cannot fix is logged and
    acknowledged.
    """
    if not settings.polar_enabled:
        logger.error("polar.webhook_not_configured")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Must be the raw bytes: re-serialising the JSON would change the payload
    # the signature was computed over.
    body = await request.body()

    try:
        event = validate_event(
            body=body,
            headers=dict(request.headers),
            secret=settings.POLAR_WEBHOOK_SECRET,
        )
    except WebhookVerificationError:
        # Either a forgery or a stale secret. 403 rather than a retry.
        logger.warning("polar.webhook_bad_signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    except WebhookUnknownTypeError as exc:
        # Signature was good; Polar has simply added an event type this SDK
        # version predates. Acknowledge so it is not retried forever.
        logger.info("polar.webhook_unknown_type", event_type=exc.event_type)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    # `TYPE`, not `type`: the SDK names the field in caps and exposes `type`
    # only as a serialisation alias.
    event_type = event.TYPE

    if event_type == "order.paid":
        billing.record_polar_order(event.data)
    elif event_type == "order.refunded":
        billing.record_polar_refund(event.data)
    else:
        # Subscribed to in the dashboard but not acted on here.
        logger.debug("polar.webhook_ignored", event_type=event_type)

    # The session commits on the way out of the request, so a database failure
    # surfaces as a 500 and Polar retries — which is what we want, because the
    # idempotency key makes the retry safe.
    return Response(status_code=status.HTTP_202_ACCEPTED)
