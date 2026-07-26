import uuid
from datetime import datetime

from sqlalchemy import Select, func, select

from app.models.search_log import LookupStatus, SearchLog
from app.repositories.base import BaseRepository


class SearchLogRepository(BaseRepository[SearchLog]):
    model = SearchLog

    def _scoped(self, user_id: uuid.UUID | None) -> Select:
        stmt = select(SearchLog)
        if user_id is not None:
            stmt = stmt.where(SearchLog.user_id == user_id)
        return stmt

    def paginate(
        self,
        *,
        user_id: uuid.UUID | None = None,
        status: LookupStatus | None = None,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SearchLog], int]:
        from sqlalchemy.orm import joinedload

        from app.models.user import User

        stmt = self._scoped(user_id)
        total_stmt = select(func.count()).select_from(SearchLog)
        if user_id is not None:
            total_stmt = total_stmt.where(SearchLog.user_id == user_id)

        if status is not None:
            stmt = stmt.where(SearchLog.status == status)
            total_stmt = total_stmt.where(SearchLog.status == status)

        if query:
            pattern = f"%{query.strip().lower()}%"
            stmt = stmt.join(User, SearchLog.user_id == User.id).where(
                SearchLog.phone_number.like(pattern) |
                func.lower(User.email).like(pattern)
            )
            total_stmt = total_stmt.join(User, SearchLog.user_id == User.id).where(
                SearchLog.phone_number.like(pattern) |
                func.lower(User.email).like(pattern)
            )

        stmt = stmt.options(joinedload(SearchLog.user))

        total = self.session.scalar(total_stmt) or 0
        rows = list(
            self.session.scalars(
                stmt.order_by(SearchLog.created_at.desc()).limit(limit).offset(offset)
            )
        )
        return rows, total

    def recent_for_user(self, user_id: uuid.UUID, limit: int = 5) -> list[SearchLog]:
        stmt = (
            select(SearchLog)
            .where(SearchLog.user_id == user_id)
            .order_by(SearchLog.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def count_since(self, since: datetime, user_id: uuid.UUID | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(SearchLog)
            .where(SearchLog.created_at >= since)
        )
        if user_id is not None:
            stmt = stmt.where(SearchLog.user_id == user_id)
        return self.session.scalar(stmt) or 0

    def count_existing_for_user(self, user_id: uuid.UUID) -> int:
        return self.session.scalar(
            select(func.count())
            .select_from(SearchLog)
            .where(
                SearchLog.user_id == user_id,
                SearchLog.exists_on_whatsapp.is_(True),
            )
        ) or 0

    def get_counts_for_users(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        stmt = (
            select(SearchLog.user_id, func.count(SearchLog.id))
            .where(SearchLog.user_id.in_(user_ids))
            .group_by(SearchLog.user_id)
        )
        return {row[0]: row[1] for row in self.session.execute(stmt)}

    def global_success_rate(self) -> float:
        total = self.session.scalar(select(func.count()).select_from(SearchLog)) or 0
        if not total:
            return 100.0
        failed = self.session.scalar(
            select(func.count())
            .select_from(SearchLog)
            .where(SearchLog.status == LookupStatus.FAILED)
        ) or 0
        return round((total - failed) / total * 100, 2)
