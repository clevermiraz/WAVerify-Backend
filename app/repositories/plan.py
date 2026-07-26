from sqlalchemy import select

from app.models.plan import Plan, PlanTier
from app.repositories.base import BaseRepository


class PlanRepository(BaseRepository[Plan]):
    model = Plan

    def get_by_slug(self, slug: PlanTier | str) -> Plan | None:
        value = slug.value if isinstance(slug, PlanTier) else slug
        return self.session.scalars(select(Plan).where(Plan.slug == value)).first()

    def list_public(self) -> list[Plan]:
        stmt = (
            select(Plan)
            .where(Plan.is_public.is_(True))
            .order_by(Plan.sort_order.asc())
        )
        return list(self.session.scalars(stmt))
