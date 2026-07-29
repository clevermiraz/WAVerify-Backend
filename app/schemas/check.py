import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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
    email: EmailStr | None = Field(
        default=None,
        description=(
            "Optional. If you also know an email for this person, we look it up "
            "on Gravatar and add their public profile — name, avatar, bio and any "
            "social accounts they have verified — under `gravatar` in the reply. "
            "Leave it out and that field is simply null."
        ),
        examples=["someone@example.com"],
    )


class NumberInfo(BaseModel):
    """Facts derived from the number itself, without contacting WhatsApp.

    Always present, even when the number has no WhatsApp account.
    """

    country_code: str = Field(description="The dialling prefix, e.g. `+880`.")
    region: str | None = Field(
        default=None, description="Two-letter country code, e.g. `BD`."
    )
    location: str | None = Field(
        default=None, description="Where the number is registered, in English."
    )
    carrier: str | None = Field(
        default=None,
        description="The network the number was issued on. Not updated for ported numbers.",
    )
    line_type: str = Field(
        description=(
            "One of `mobile`, `fixed_line`, `fixed_line_or_mobile`, `voip`, "
            "`toll_free`, `premium_rate`, `shared_cost`, `personal_number`, "
            "`pager`, `uan`, `voicemail`, `unknown`."
        )
    )
    timezones: list[str] = Field(
        default_factory=list, description="IANA time zones the number belongs to."
    )
    international_format: str | None = Field(
        default=None, description="Human-readable international form."
    )
    national_format: str | None = Field(
        default=None, description="Human-readable local form."
    )


class GravatarAccount(BaseModel):
    """A social account the person has verified on their Gravatar profile."""

    service: str = Field(description="The platform, e.g. `Twitter`, `Instagram`, `GitHub`.")
    url: str = Field(description="Link to their profile on that platform.")


class GravatarProfile(BaseModel):
    """Public Gravatar profile for the email, when one exists.

    Everything here is what the person chose to publish on gravatar.com. Only
    fields they filled in are set; the rest are null.
    """

    display_name: str | None = Field(default=None, description="Their public name.")
    about: str | None = Field(default=None, description="Their public bio.")
    location: str | None = Field(default=None, description="Their stated location.")
    job_title: str | None = Field(default=None, description="Their stated job title.")
    company: str | None = Field(default=None, description="Their stated company.")
    pronouns: str | None = Field(default=None, description="Their stated pronouns.")
    avatar_url: str | None = Field(default=None, description="Link to their avatar image.")
    profile_url: str | None = Field(
        default=None, description="Link to their full Gravatar profile."
    )
    verified_accounts: list[GravatarAccount] = Field(
        default_factory=list,
        description="Social accounts they have verified — the ones they chose to show.",
    )


class CheckResponse(BaseModel):
    """What `POST /api/v1/check` sends back."""

    success: bool = Field(default=True, description="Always true when the request worked.")
    phone: str = Field(
        description="The number you sent, rewritten in the standard international format."
    )
    exists: bool = Field(description="true if this number has a WhatsApp account.")
    display_name: str | None = Field(
        default=None,
        description=(
            "The name on the account. Business accounts publish a verified name; "
            "personal accounts do not expose their name to a stranger, so this is "
            "usually null for them. Check `name_source` to see where it came from."
        ),
    )
    name_source: str | None = Field(
        default=None,
        description=(
            "How we obtained `display_name`: `business_verified` (from the "
            "account's verified business certificate), `business_name`, "
            "`contact_name` or `push_name` (already known to the checking "
            "account). null when we could not get a name at all."
        ),
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
        description=(
            "Link to the profile picture. null if the account hides it. The link "
            "is issued by WhatsApp and expires — download it if you need to keep it."
        ),
    )
    profile_photo_id: str | None = Field(
        default=None,
        description=(
            "Stable id for the current picture. It changes when the account "
            "changes its photo, so you can detect a change without re-downloading."
        ),
    )
    device_count: int | None = Field(
        default=None,
        description=(
            "How many devices are linked to the account. 1 means phone only; "
            "higher means WhatsApp Web or Desktop is in use."
        ),
    )
    number_info: NumberInfo | None = Field(
        default=None, description="Facts about the number itself. Never requires WhatsApp."
    )
    gravatar: GravatarProfile | None = Field(
        default=None,
        description=(
            "Public Gravatar profile, only when you passed an `email` and that "
            "email has a Gravatar account. null otherwise."
        ),
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
                "display_name": "Acme Store",
                "name_source": "business_verified",
                "about": "Open 9-6, Sat closed",
                "business": True,
                "profile_photo": "https://pps.whatsapp.net/v/t61.24694-24/9f2c.jpg",
                "profile_photo_id": "1721728451",
                "device_count": 2,
                "number_info": {
                    "country_code": "+880",
                    "region": "BD",
                    "location": "Bangladesh",
                    "carrier": "Grameenphone",
                    "line_type": "mobile",
                    "timezones": ["Asia/Dhaka"],
                    "international_format": "+880 1712-345678",
                    "national_format": "01712-345678",
                },
                "gravatar": {
                    "display_name": "Jane Roe",
                    "about": "Product designer.",
                    "location": "Dhaka, Bangladesh",
                    "job_title": "Designer",
                    "company": "Acme",
                    "pronouns": None,
                    "avatar_url": "https://gravatar.com/avatar/abc123",
                    "profile_url": "https://gravatar.com/janeroe",
                    "verified_accounts": [
                        {"service": "Twitter", "url": "https://twitter.com/janeroe"}
                    ],
                },
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
    number_info: NumberInfo | None = None
    gravatar: GravatarProfile | None = None
    response_time_ms: int
    cached: bool
    created_at: datetime


class SearchLogDetail(SearchLogRead):
    """A single past check with everything we stored about it.

    Backs the history detail view — clicking a number shows exactly what that
    lookup returned. Fields not captured at lookup time (`name_source`,
    `profile_photo_id`, `device_count`) are live-response only and absent here.
    """

    about: str | None = None
    is_business: bool | None = None
    profile_photo_url: str | None = None
    error_code: str | None = None
