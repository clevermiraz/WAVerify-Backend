"""Paginated search history."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.search_log import LookupStatus
from app.repositories.search_log import SearchLogRepository
from app.schemas.check import SearchLogDetail, SearchLogRead
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

    def get_for_user(
        self, user_id: uuid.UUID, search_id: uuid.UUID
    ) -> SearchLogDetail:
        log = self.logs.get_for_user(search_id, user_id)
        if log is None:
            raise NotFoundError("That check was not found.")
        return SearchLogDetail.model_validate(log)
