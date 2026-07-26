import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.api_key import ApiKey
from app.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    model = ApiKey

    def get_by_hash(self, hashed_key: str) -> ApiKey | None:
        stmt = (
            select(ApiKey)
            .where(ApiKey.hashed_key == hashed_key, ApiKey.is_active.is_(True))
            .options(joinedload(ApiKey.user))
        )
        return self.session.scalars(stmt).first()

    def get_for_user(self, key_id: uuid.UUID, user_id: uuid.UUID) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        return self.session.scalars(stmt).first()

    def list_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        stmt = (
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def count_active_for_user(self, user_id: uuid.UUID) -> int:
        return self.session.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
        ) or 0

    def count_active(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(ApiKey).where(ApiKey.is_active.is_(True))
        ) or 0

    def name_taken(
        self, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        stmt = select(ApiKey.id).where(
            ApiKey.user_id == user_id,
            func.lower(ApiKey.name) == name.strip().lower(),
        )
        if exclude_id:
            stmt = stmt.where(ApiKey.id != exclude_id)
        return self.session.scalars(stmt).first() is not None

    def paginate(self, *, limit: int, offset: int) -> tuple[list[ApiKey], int]:
        total = self.count()
        rows = list(
            self.session.scalars(
                select(ApiKey).order_by(ApiKey.created_at.desc()).limit(limit).offset(offset)
            )
        )
        return rows, total
