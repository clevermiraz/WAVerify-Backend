"""Shared FastAPI dependencies: datastores, pagination, service wiring."""

from typing import Annotated

import redis
from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.redis import get_redis
from app.db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]
RedisDep = Annotated[redis.Redis, Depends(get_redis)]

MAX_PAGE_SIZE = 100


class Pagination(BaseModel):
    page: int
    page_size: int


def pagination_params(
    page: Annotated[int, Query(ge=1, description="1-indexed page number.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


PaginationDep = Annotated[Pagination, Depends(pagination_params)]
