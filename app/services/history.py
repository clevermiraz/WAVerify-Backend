"""Paginated search history."""

import uuid

from sqlalchemy.orm import Session

from app.models.search_log import LookupStatus
from app.repositories.search_log import SearchLogRepository
from app.schemas.check import SearchLogRead
from app.schemas.common import Page


class SearchHistoryService:
    def __init__(self, session: Session) -> None:
        self.logs = SearchLogRepository(session)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        status: LookupStatus | None = None,
        query: str | None = None,
    ) -> Page[SearchLogRead]:
        rows, total = self.logs.paginate(
            user_id=user_id,
            status=status,
            query=query,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return Page.create(
            items=[SearchLogRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
