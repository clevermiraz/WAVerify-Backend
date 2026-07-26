"""Importing this package registers every model with the SQLAlchemy mapper.

Relationships are declared with string targets, so all classes must be
imported before the first mapper configuration or resolution fails.
"""

from app.models.api_key import ApiKey
from app.models.base import Base
from app.models.plan import Plan, PlanTier
from app.models.search_log import LookupSource, LookupStatus, SearchLog
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.usage_statistic import UsageStatistic
from app.models.user import User, UserRole
from app.models.whatsapp_account import WhatsAppAccount

__all__ = [
    "ApiKey",
    "Base",
    "LookupSource",
    "LookupStatus",
    "Plan",
    "PlanTier",
    "SearchLog",
    "Subscription",
    "SubscriptionStatus",
    "UsageStatistic",
    "User",
    "UserRole",
    "WhatsAppAccount",
]
