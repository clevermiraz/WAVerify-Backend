from sqlalchemy import func, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return self.session.scalars(stmt).first()

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def search(
        self,
        *,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        if query:
            pattern = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                func.lower(User.email).like(pattern)
                | func.lower(func.coalesce(User.full_name, "")).like(pattern)
            )

        total = self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0
        rows = list(
            self.session.scalars(
                stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
            )
        )
        return rows, total

    def count_where_active(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        ) or 0

    def count_where_verified(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(User).where(User.is_email_verified.is_(True))
        ) or 0
