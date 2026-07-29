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
    email: str | None = Field(
        default=None,
        max_length=254,
        description=(
            "Optional. If you also send an email we verify it and return the "
            "verdict under `email_info` — whether the address is well-formed, "
            "whether its domain can actually receive mail, and whether it is a "
            "throwaway or a shared team address. When the address is well-formed "
            "we also look it up on Gravatar and add any public profile under "
            "`gravatar`. Leave it out and both fields are simply null. "
            "A malformed address is a result, not an error: you get `200` with "
            "`email_info.syntax_valid: false`, never a `422`."
        ),
        examples=["someone@example.com"],
    )


class EmailCheckRequest(BaseModel):
    email: str = Field(
        min_length=1,
        max_length=254,
        description=(
            "The email address to check. A malformed address is a result, not "
            "an error: you get `200` with `email_info.syntax_valid: false`."
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


class EmailInfo(BaseModel):
    """The verdict on the email you sent.

    Two things are checked without ever contacting the mailbox: the address is
    written correctly, and its domain publishes somewhere to deliver mail. That
    is as far as any honest check can go — the only way to prove one specific
    mailbox exists is to try to send to it, which gets the sender blocklisted,
    so we do not do it. Read `deliverable` as "this domain accepts mail", not
    "this person exists".
    """

    email: str = Field(
        description="The address you sent, lowercased and cleaned up.",
        examples=["someone@example.com"],
    )
    syntax_valid: bool = Field(
        description="true if the address is written correctly and could exist."
    )
    domain: str | None = Field(
        default=None,
        description="The part after the @. null when the address is too broken to split.",
    )
    deliverable: bool | None = Field(
        default=None,
        description=(
            "true if the domain publishes a mail server, false if it does not "
            "or does not exist at all. null means we could not find out — the "
            "DNS lookup timed out or was turned off, so treat it as unknown "
            "rather than as a failure."
        ),
    )
    mx_hosts: list[str] = Field(
        default_factory=list,
        description="Mail servers for the domain, best first. Empty when there are none.",
    )
    disposable: bool = Field(
        default=False,
        description=(
            "true if the domain is a known throwaway-inbox service. These "
            "addresses receive mail perfectly well but are abandoned in minutes."
        ),
    )
    role_account: bool = Field(
        default=False,
        description=(
            "true for shared or automated mailboxes like `info@`, `support@` or "
            "`no-reply@` — real, but no single person behind them."
        ),
    )
    free_provider: bool = Field(
        default=False,
        description=(
            "true if the domain is a consumer mailbox provider such as Gmail. "
            "Normal for a personal address; notable for one claiming to be a company."
        ),
    )
    status: str = Field(
        description=(
            "One-word summary: `valid`, `invalid_syntax`, `domain_not_found`, "
            "`no_mail_server`, `disposable`, or `unknown` when the DNS check "
            "could not be completed."
        )
    )
    reason: str | None = Field(
        default=None,
        description="Plain-English explanation of `status`. null when the address is fine.",
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
    email_info: EmailInfo | None = Field(
        default=None,
        description=(
            "The verdict on the `email` you sent. null when you did not send one."
        ),
    )
    gravatar: GravatarProfile | None = Field(
        default=None,
        description=(
            "Public Gravatar profile, only when you passed a well-formed `email` "
            "and that email has a Gravatar account. null otherwise."
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
                "email_info": {
                    "email": "jane@acme.com",
                    "syntax_valid": True,
                    "domain": "acme.com",
                    "deliverable": True,
                    "mx_hosts": ["aspmx.l.google.com"],
                    "disposable": False,
                    "role_account": False,
                    "free_provider": False,
                    "status": "valid",
                    "reason": None,
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


class EmailCheckResponse(BaseModel):
    """What `POST /api/v1/check/email` sends back.

    Nothing here touches WhatsApp, so this route keeps working when the
    account pool is empty or down — which is the whole point of having it
    separate from `/check`.
    """

    success: bool = Field(default=True, description="Always true when the request worked.")
    email: str = Field(description="The address you sent, normalised.")
    email_info: EmailInfo = Field(description="The verdict on the address.")
    gravatar: GravatarProfile | None = Field(
        default=None,
        description=(
            "Public Gravatar profile for the address, when it has one. null "
            "when it does not, or when the address was too malformed to look up."
        ),
    )
    response_time_ms: int = Field(
        description="How long the check took on our server, in milliseconds."
    )
    cached: bool = Field(
        default=False,
        description="true if we answered from a saved recent result.",
    )
    checked_at: datetime = Field(description="Date and time of the check, in UTC.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "email": "jane@acme.com",
                "email_info": {
                    "email": "jane@acme.com",
                    "syntax_valid": True,
                    "domain": "acme.com",
                    "deliverable": True,
                    "mx_hosts": ["mx.acme.com"],
                    "disposable": False,
                    "role_account": False,
                    "free_provider": False,
                    "status": "valid",
                    "reason": None,
                },
                "gravatar": None,
                "response_time_ms": 96,
                "cached": False,
                "checked_at": "2026-07-29T10:04:11Z",
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
    email_info: EmailInfo | None = None
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
