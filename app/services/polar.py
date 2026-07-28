"""Thin wrapper over the Polar API.

Polar is the merchant of record: it owns the payment page, the card details
and the tax handling. This module's only jobs are to open a checkout session
and to translate a Polar product back into one of our plans. Credits
themselves are granted by `BillingService`, from the webhook.
"""

import threading

from polar_sdk import Polar

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.models.plan import Plan
from app.models.user import User

logger = get_logger(__name__)

# Key on every Polar product, set by hand in the dashboard, holding the slug of
# the plan it sells. Resolving through metadata rather than product IDs means
# sandbox and production run the same code with no ID table to maintain.
PLAN_SLUG_KEY = "plan_slug"


class BillingUnavailableError(AppError):
    status_code = 503
    code = "billing_unavailable"
    message = "Payments are temporarily unavailable. Please try again shortly."


# Product IDs never change once created, so the slug -> id mapping is cached
# process-wide rather than re-fetched on every checkout. Guarded by a lock
# because uvicorn runs sync endpoints in a thread pool.
_product_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


class PolarService:
    def __init__(self) -> None:
        if not settings.polar_enabled:
            raise BillingUnavailableError(
                "Polar is not configured on this deployment.",
                code="billing_not_configured",
            )
        self.client = Polar(
            access_token=settings.POLAR_ACCESS_TOKEN,
            server=settings.POLAR_SERVER,
        )

    # --- Products ---------------------------------------------------------

    def product_id_for_plan(self, plan: Plan) -> str:
        """Find the Polar product tagged with this plan's slug."""
        cached = _product_cache.get(plan.slug)
        if cached is not None:
            return cached

        try:
            response = self.client.products.list(
                metadata={PLAN_SLUG_KEY: plan.slug},
                is_archived=False,
                limit=2,
            )
        except Exception as exc:
            logger.exception("polar.product_lookup_failed", plan=plan.slug, error=str(exc))
            raise BillingUnavailableError() from exc

        items = list(response.result.items) if response is not None else []
        if not items:
            # Misconfiguration, not a user error: the plan exists in our
            # database but nothing in Polar sells it.
            logger.error("polar.product_missing", plan=plan.slug)
            raise BillingUnavailableError(
                "This plan is not available for purchase right now.",
                code="plan_not_purchasable",
            )
        if len(items) > 1:
            # Ambiguous: two products claim the same slug, so which one the
            # buyer gets would be arbitrary. Take the first but make it loud.
            logger.error(
                "polar.product_ambiguous",
                plan=plan.slug,
                product_ids=[item.id for item in items],
            )

        product_id = items[0].id
        with _cache_lock:
            _product_cache[plan.slug] = product_id
        return product_id

    # --- Invoices ---------------------------------------------------------

    def invoice_url(self, order_id: str) -> str | None:
        """URL of an order's PDF invoice, or `None` while it is being made.

        Polar generates invoices lazily and asynchronously: the first request
        only schedules the job and the PDF appears a few seconds later, so
        callers have to poll. The returned URL is pre-signed and expires,
        which is why it is fetched fresh every time rather than stored.
        """
        url = self._fetch_invoice_url(order_id)
        if url is not None:
            return url

        try:
            # Safe to repeat: Polar no-ops once the invoice exists.
            self.client.orders.generate_invoice(id=order_id)
        except Exception as exc:
            logger.exception(
                "polar.invoice_generate_failed", order_id=order_id, error=str(exc)
            )
            raise BillingUnavailableError(
                "The invoice could not be prepared. Please try again shortly.",
                code="invoice_unavailable",
            ) from exc

        # Usually still building; the caller polls.
        return self._fetch_invoice_url(order_id)

    def _fetch_invoice_url(self, order_id: str) -> str | None:
        try:
            return self.client.orders.invoice(id=order_id).url
        except Exception as exc:
            # An ungenerated invoice does not surface as a clean 404: Polar
            # answers with an `InvoiceDoesNotExist` code that this SDK version
            # cannot deserialise, so it arrives as a validation error. Logged
            # rather than swallowed, because a credentials failure would look
            # identical from here and would otherwise present as a download
            # that never becomes ready.
            logger.info(
                "polar.invoice_not_ready",
                order_id=order_id,
                error_type=type(exc).__name__,
            )
            return None

    # --- Checkout ---------------------------------------------------------

    def create_checkout(self, user: User, plan: Plan) -> str:
        """Open a hosted checkout and return the URL to send the buyer to."""
        product_id = self.product_id_for_plan(plan)

        try:
            checkout = self.client.checkouts.create(
                request={
                    "products": [product_id],
                    "success_url": settings.POLAR_SUCCESS_URL,
                    # Ties the Polar customer to our user permanently, so even
                    # a checkout whose metadata is lost can still be attributed.
                    "external_customer_id": str(user.id),
                    "customer_email": user.email,
                    # Read back on `order.paid` to identify the buyer. Note it
                    # is *not* trusted for how many credits to grant — that
                    # comes from the product, which the buyer cannot influence.
                    "metadata": {"user_id": str(user.id), PLAN_SLUG_KEY: plan.slug},
                }
            )
        except Exception as exc:
            logger.exception(
                "polar.checkout_failed",
                user_id=str(user.id),
                plan=plan.slug,
                error=str(exc),
            )
            raise BillingUnavailableError() from exc

        logger.info(
            "polar.checkout_created",
            user_id=str(user.id),
            plan=plan.slug,
            checkout_id=checkout.id,
        )
        return checkout.url
