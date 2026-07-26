import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.subscription import Subscription
from app.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription

    def get_for_user(self, user_id: uuid.UUID) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .options(joinedload(Subscription.plan))
        )
        return self.session.scalars(stmt).first()

    def paginate(self, *, limit: int, offset: int) -> tuple[list[Subscription], int]:
        total = self.session.scalar(
            select(func.count()).select_from(Subscription)
        ) or 0
        rows = list(
            self.session.scalars(
                select(Subscription)
                .options(joinedload(Subscription.plan), joinedload(Subscription.user))
                .order_by(Subscription.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total
