import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.payment import Payment
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    def get_by_order_id(self, polar_order_id: str) -> Payment | None:
        stmt = select(Payment).where(Payment.polar_order_id == polar_order_id)
        return self.session.scalars(stmt).first()

    def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Payment], int]:
        total = self.session.scalar(
            select(func.count()).select_from(Payment).where(Payment.user_id == user_id)
        ) or 0
        rows = list(
            self.session.scalars(
                select(Payment)
                .where(Payment.user_id == user_id)
                .options(joinedload(Payment.plan))
                .order_by(Payment.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total
