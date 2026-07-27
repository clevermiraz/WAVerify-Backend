import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.search_log import LookupSource, LookupStatus
from app.schemas.common import ORMModel


class CheckRequest(BaseModel):
    phone: str = Field(
        min_length=6,
        max_length=20,
        description=(
            "The phone number to check, in international format: a + sign, "
            "then the country code, then the number. Spaces, dashes and "
            "brackets are removed for you."
        ),
        examples=["+8801712345678"],
    )


class CheckResponse(BaseModel):
    """What `POST /api/v1/check` sends back."""

    success: bool = Field(default=True, description="Always true when the request worked.")
    phone: str = Field(
        description="The number you sent, rewritten in the standard international format."
    )
    exists: bool = Field(description="true if this number has a WhatsApp account.")
    display_name: str | None = Field(
        default=None, description="The name on the account. null if the account hides it."
    )
    about: str | None = Field(
        default=None,
        description="The short 'about' text on the account. null if the account hides it.",
    )
    business: bool = Field(
        default=False, description="true if this is a WhatsApp Business account."
    )
    profile_photo: str | None = Field(
        default=None,
        description="Link to the profile picture. null if the account hides it.",
    )
    response_time_ms: int = Field(
        description="How long the check took on our server, in milliseconds."
    )
    cached: bool = Field(
        default=False,
        description=(
            "true if we answered from a saved recent result instead of checking "
            "again. It still counts towards your monthly total."
        ),
    )
    checked_at: datetime = Field(description="Date and time of the check, in UTC.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "phone": "+8801712345678",
                "exists": True,
                "display_name": "John Doe",
                "about": "Software Engineer",
                "business": False,
                "profile_photo": "https://cdn.waverify.app/p/9f2c.jpg",
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
