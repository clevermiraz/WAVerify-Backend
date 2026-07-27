import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.wallet import Wallet
from app.repositories.base import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    model = Wallet

    def get_for_user(self, user_id: uuid.UUID) -> Wallet | None:
        stmt = (
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .options(joinedload(Wallet.plan))
        )
        return self.session.scalars(stmt).first()

    def paginate(self, *, limit: int, offset: int) -> tuple[list[Wallet], int]:
        total = self.session.scalar(
            select(func.count()).select_from(Wallet)
        ) or 0
        rows = list(
            self.session.scalars(
                select(Wallet)
                .options(joinedload(Wallet.plan), joinedload(Wallet.user))
                .order_by(Wallet.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total
