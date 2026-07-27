"""Seeds reference data.

Idempotent: safe to run on every deploy. Plans are reference data the
application depends on (a user cannot exist without one), so they are seeded
here rather than in a migration.
"""


from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.plan import PlanTier
from app.repositories.plan import PlanRepository

logger = get_logger(__name__)

PLAN_SEED: list[dict] = [
    {
        "slug": PlanTier.FREE,
        "name": "Free / Trial",
        "description": "Try out WAVerify before you commit.",
        "price_cents": 0,
        "credits_awarded": 20,
        "rate_limit_per_minute": 10,
        "features": [
            "Basic API Access",
            "1 API Key",
            "Rate-limited",
        ],
        "sort_order": 1,
    },
    {
        "slug": PlanTier.STARTER,
        "name": "Starter",
        "description": "For side projects and small products.",
        "price_cents": 900,
        "credits_awarded": 7500,
        "rate_limit_per_minute": 60,
        "features": [
            "Full Speed API",
            "Bulk CSV Upload",
            "Email Support",
            "Everything in Free",
        ],
        "sort_order": 2,
    },
    {
        "slug": PlanTier.GROWTH,
        "name": "Growth",
        "description": "For growing businesses.",
        "price_cents": 2900,
        "credits_awarded": 30000,
        "rate_limit_per_minute": 120,
        "features": [
            "Up to 5 API Keys",
            "Priority Queue",
            "Priority Support",
            "Everything in Starter",
        ],
        "is_recommended": True,
        "sort_order": 3,
    },
    {
        "slug": PlanTier.PRO,
        "name": "Pro / Scale",
        "description": "For production workloads that need headroom.",
        "price_cents": 6900,
        "credits_awarded": 85000,
        "rate_limit_per_minute": 300,
        "features": [
            "Higher Rate Limits",
            "Full Validation Logs",
            "Custom SLA & Dedicated Support",
            "Everything in Growth",
        ],
        "sort_order": 4,
    },
]


def seed_plans(session: Session) -> None:
    repo = PlanRepository(session)
    for data in PLAN_SEED:
        existing = repo.get_by_slug(data["slug"])
        if existing is None:
            repo.create(**data)
            logger.info("seed.plan_created", slug=data["slug"])
        else:
            # Keep pricing and limits in sync with the code on redeploy,
            # without disturbing anyone's subscription.
            repo.update(existing, **{k: v for k, v in data.items() if k != "slug"})


def init_db(session: Session) -> None:
    seed_plans(session)
    session.commit()


def main() -> None:  # pragma: no cover - operational entry point
    from app.core.logging import configure_logging
    from app.db.session import SessionLocal

    configure_logging()
    with SessionLocal() as session:
        init_db(session)
    logger.info("seed.completed")


if __name__ == "__main__":  # pragma: no cover
    main()
