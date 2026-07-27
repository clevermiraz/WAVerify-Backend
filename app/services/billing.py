"""Plans, wallets and credit accounting."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.plan import Plan, PlanTier
from app.models.wallet import Wallet
from app.repositories.plan import PlanRepository
from app.repositories.usage import UsageRepository
from app.repositories.wallet import WalletRepository

logger = get_logger(__name__)


class BillingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.wallets = WalletRepository(session)
        self.usage = UsageRepository(session)

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

    def top_up_wallet(self, user_id: uuid.UUID, slug: PlanTier) -> Wallet:
        wallet = self.get_wallet(user_id)
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

        new_balance = wallet.credits_balance + (plan.credits_awarded or 0)
        
        # Only upgrade plan if sort_order is higher (i.e. tier is higher)
        new_plan_id = plan.id if plan.sort_order >= wallet.plan.sort_order else wallet.plan.id
        
        self.wallets.update(
            wallet,
            plan_id=new_plan_id,
            credits_balance=new_balance,
        )
        logger.info("billing.wallet_topped_up", user_id=str(user_id), plan=plan.slug, balance=new_balance)
        self.session.refresh(wallet)
        return wallet

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
