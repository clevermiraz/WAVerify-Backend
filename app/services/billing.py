"""Plans, wallets and credit accounting."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.payment import Payment, PaymentStatus
from app.models.plan import Plan, PlanTier
from app.models.wallet import Wallet
from app.repositories.payment import PaymentRepository
from app.repositories.plan import PlanRepository
from app.repositories.usage import UsageRepository
from app.repositories.user import UserRepository
from app.repositories.wallet import WalletRepository

logger = get_logger(__name__)

# Metadata key carrying the plan slug. Mirrors `app.services.polar`, kept
# separate so this module has no import dependency on the Polar SDK.
PLAN_SLUG_KEY = "plan_slug"


class BillingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.wallets = WalletRepository(session)
        self.usage = UsageRepository(session)
        self.payments = PaymentRepository(session)
        self.users = UserRepository(session)

    # --- Plans -----------------------------------------------------------

    def list_public_plans(self) -> list[Plan]:
        return self.plans.list_public()

    def get_plan(self, slug: PlanTier | str) -> Plan:
        plan = self.plans.get_by_slug(slug)
        if plan is None:
            raise NotFoundError("Plan not found.")
        return plan

    # --- Wallets ---------------------------------------------------------

    def create_default_wallet(self, user_id: uuid.UUID) -> Wallet:
        """Put a new user on the Free plan."""
        plan = self.get_plan(PlanTier.FREE)
        return self.wallets.create(
            user_id=user_id,
            plan_id=plan.id,
            credits_balance=plan.credits_awarded or 0,
        )

    def get_wallet(self, user_id: uuid.UUID) -> Wallet:
        wallet = self.wallets.get_for_user(user_id)
        if wallet is None:
            logger.warning("billing.missing_wallet", user_id=str(user_id))
            wallet = self.create_default_wallet(user_id)
        return wallet

    def purchasable_plan(self, slug: PlanTier | str) -> Plan:
        """Resolve a slug the buyer asked for, rejecting what cannot be sold."""
        plan = self.get_plan(slug)
        if plan.is_contact_sales:
            raise ValidationError(
                "The requested plan is arranged with our sales team.",
                code="contact_sales_required",
            )
        if plan.slug == PlanTier.FREE:
            raise ValidationError(
                "The free trial can only be claimed once upon registration.",
                code="free_trial_already_claimed",
            )
        if not plan.is_active:
            raise ValidationError(
                "This plan is no longer available.",
                code="plan_unavailable",
            )
        return plan

    def grant_credits(self, user_id: uuid.UUID, plan: Plan) -> Wallet:
        """Add a plan's credits to a wallet and promote the tier if it is higher.

        No "can this be bought" checks: by the time this runs the money has
        already moved, so refusing would take payment and give nothing.
        """
        wallet = self.get_wallet(user_id)
        new_balance = wallet.credits_balance + (plan.credits_awarded or 0)
        new_plan_id = plan.id if plan.sort_order >= wallet.plan.sort_order else wallet.plan.id
        self.wallets.update(wallet, plan_id=new_plan_id, credits_balance=new_balance)
        return wallet

    # --- Polar orders ----------------------------------------------------

    def record_polar_order(self, order: Any) -> Payment | None:
        """Grant credits for a paid Polar order, exactly once.

        Returns the ledger row, or `None` when the order could not be
        attributed to a user at all. Callers must still answer 2xx in that
        case: a retry would fail identically, and Polar disables an endpoint
        after ten consecutive failures.
        """
        already = self.payments.get_by_order_id(order.id)
        if already is not None:
            # Redelivery, or a retry after our response was lost in flight.
            logger.info("billing.polar_order_duplicate", order_id=order.id)
            return already

        user_id = self._user_id_from_order(order)
        if user_id is None:
            logger.error(
                "billing.polar_order_unattributed",
                order_id=order.id,
                customer_id=order.customer_id,
            )
            return None

        plan = self._plan_from_order(order)
        amount_cents = order.total_amount or 0
        currency = (order.currency or "usd").upper()[:3]

        if plan is None:
            # Paid for, but we cannot tell what was bought — the product is
            # missing its `plan_slug`. Bank the record so support can fix it
            # by hand; granting a guessed plan would be worse.
            logger.error(
                "billing.polar_order_unmapped",
                order_id=order.id,
                user_id=str(user_id),
                product_id=order.product_id,
            )
            return self.payments.create(
                polar_order_id=order.id,
                polar_checkout_id=order.checkout_id,
                polar_customer_id=order.customer_id,
                user_id=user_id,
                plan_id=None,
                status=PaymentStatus.UNMAPPED,
                amount_cents=amount_cents,
                currency=currency,
                credits_granted=0,
            )

        credits = plan.credits_awarded or 0
        self.grant_credits(user_id, plan)
        payment = self.payments.create(
            polar_order_id=order.id,
            polar_checkout_id=order.checkout_id,
            polar_customer_id=order.customer_id,
            user_id=user_id,
            plan_id=plan.id,
            status=PaymentStatus.PAID,
            amount_cents=amount_cents,
            currency=currency,
            credits_granted=credits,
        )
        logger.info(
            "billing.polar_order_fulfilled",
            order_id=order.id,
            user_id=str(user_id),
            plan=plan.slug,
            credits=credits,
            amount_cents=amount_cents,
        )
        return payment

    def record_polar_refund(self, order: Any) -> Payment | None:
        """Reverse a refunded order's credits, without going negative."""
        payment = self.payments.get_by_order_id(order.id)
        if payment is None:
            logger.warning("billing.polar_refund_unknown_order", order_id=order.id)
            return None
        if payment.status is PaymentStatus.REFUNDED:
            return payment

        wallet = self.get_wallet(payment.user_id)
        # Floored at zero: the credits may already be spent, and a negative
        # balance would lock the account out of the free tier too.
        clawed_back = min(payment.credits_granted, wallet.credits_balance)
        self.wallets.update(wallet, credits_balance=wallet.credits_balance - clawed_back)
        self.payments.update(payment, status=PaymentStatus.REFUNDED)
        logger.info(
            "billing.polar_order_refunded",
            order_id=order.id,
            user_id=str(payment.user_id),
            granted=payment.credits_granted,
            clawed_back=clawed_back,
        )
        return payment

    def _user_id_from_order(self, order: Any) -> uuid.UUID | None:
        """Both sources are values we set at checkout, never buyer input.

        The account is confirmed to still exist before the id is returned: a
        well-formed UUID for a deleted user would otherwise reach
        `create_default_wallet` and fail on the foreign key, turning a dead
        order into a 500 that Polar retries ten times.
        """
        candidates = [
            (order.metadata or {}).get("user_id"),
            getattr(order.customer, "external_id", None),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                user_id = uuid.UUID(str(candidate))
            except ValueError:
                logger.warning(
                    "billing.polar_order_bad_user_id",
                    order_id=order.id,
                    value=str(candidate),
                )
                continue
            if self.users.get(user_id) is not None:
                return user_id
            logger.warning(
                "billing.polar_order_unknown_user",
                order_id=order.id,
                user_id=str(user_id),
            )
        return None

    def _plan_from_order(self, order: Any) -> Plan | None:
        """Authoritative source for *what was bought*.

        Deliberately reads the slug off the product rather than the checkout
        metadata. Checkout metadata originates from a request; the product is
        configured in the Polar dashboard, so a buyer cannot swap a $9 order
        into an 85,000-credit grant.
        """
        product = getattr(order, "product", None)
        slug = (getattr(product, "metadata", None) or {}).get(PLAN_SLUG_KEY)
        if not slug:
            return None
        return self.plans.get_by_slug(str(slug))

    # --- Quota -----------------------------------------------------------

    def remaining_quota(self, user_id: uuid.UUID, wallet: Wallet | None = None) -> int | None:
        """`None` means unmetered."""
        wallet = wallet or self.get_wallet(user_id)
        if wallet.plan.credits_awarded is None:
            return None
        return max(0, wallet.credits_balance)

    def deduct_quota(self, user_id: uuid.UUID, amount: int = 1) -> None:
        """Deduct credits from the user's wallet. Raises ValueError if insufficient."""
        wallet = self.get_wallet(user_id)
        if wallet.plan.credits_awarded is None:
            return # Unmetered
        
        if wallet.credits_balance < amount:
            raise ValueError("Insufficient credits.")
            
        self.wallets.update(wallet, credits_balance=wallet.credits_balance - amount)
