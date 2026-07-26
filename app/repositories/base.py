"""Generic CRUD repository.

Repositories own persistence concerns only. They never commit — the request
scoped session in `app.db.session.get_session` owns the transaction boundary
so a whole request succeeds or fails atomically.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(self.model)) or 0

    def create(self, **values: Any) -> ModelT:
        entity = self.model(**values)
        self.session.add(entity)
        self.session.flush()
        return entity

    def update(self, entity: ModelT, **values: Any) -> ModelT:
        for field, value in values.items():
            setattr(entity, field, value)
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)
        self.session.flush()
