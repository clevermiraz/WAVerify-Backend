import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80, examples=["Production server"])


class ApiKeyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ApiKeyRead(ORMModel):
    id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyRead):
    """Returned once, at creation. `key` is never retrievable again."""

    key: str
