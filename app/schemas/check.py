import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.search_log import LookupSource, LookupStatus
from app.schemas.common import ORMModel


class CheckRequest(BaseModel):
    phone: str = Field(
        min_length=6,
        max_length=20,
        description="Phone number in international format, e.g. +8801712345678.",
        examples=["+8801712345678"],
    )


class CheckResponse(BaseModel):
    """Public API contract for `POST /api/v1/check`."""

    success: bool = True
    phone: str
    exists: bool
    display_name: str | None = None
    about: str | None = None
    business: bool = False
    profile_photo: str | None = None
    response_time_ms: int
    cached: bool = False
    checked_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "phone": "+8801712345678",
                "exists": True,
                "display_name": "John Doe",
                "about": "Software Engineer",
                "business": False,
                "profile_photo": "https://cdn.waverify.dev/p/9f2c.jpg",
                "response_time_ms": 214,
                "cached": False,
                "checked_at": "2026-07-23T10:04:11Z",
            }
        }
    }


class SearchLogRead(ORMModel):
    id: uuid.UUID
    phone_number: str
    country_code: str | None
    status: LookupStatus
    source: LookupSource
    exists_on_whatsapp: bool | None
    display_name: str | None
    response_time_ms: int
    cached: bool
    created_at: datetime
