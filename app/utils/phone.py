"""E.164 phone number parsing and normalisation."""

from dataclasses import dataclass

import phonenumbers
from phonenumbers import carrier, geocoder, timezone

from app.core.exceptions import ValidationError

# phonenumbers ships its own offline metadata, so every field below is derived
# without a network call and works for any country.
_LINE_TYPES = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
    phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
    phonenumbers.PhoneNumberType.VOIP: "voip",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.UAN: "uan",
    phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
}


@dataclass(frozen=True, slots=True)
class ParsedPhone:
    e164: str
    country_code: str
    national_number: str
    region: str | None = None
    location: str | None = None
    carrier: str | None = None
    line_type: str = "unknown"
    timezones: tuple[str, ...] = ()
    international_format: str | None = None
    national_format: str | None = None


def parse_phone(raw: str) -> ParsedPhone:
    """Normalise user input to E.164.

    Requires an explicit country prefix: without a default region there is no
    safe way to guess one, and guessing wrong would silently verify a
    different subscriber.
    """
    candidate = raw.strip().replace(" ", "").replace("-", "")
    if not candidate.startswith("+"):
        candidate = f"+{candidate.lstrip('+')}"

    try:
        parsed = phonenumbers.parse(candidate, None)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError(
            "Enter a phone number in international format, e.g. +8801712345678.",
            details={"phone": raw},
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(
            "That phone number is not valid.",
            details={"phone": raw},
        )

    return ParsedPhone(
        e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        country_code=f"+{parsed.country_code}",
        national_number=str(parsed.national_number),
        region=phonenumbers.region_code_for_number(parsed),
        location=geocoder.description_for_number(parsed, "en") or None,
        carrier=carrier.name_for_number(parsed, "en") or None,
        line_type=_LINE_TYPES.get(phonenumbers.number_type(parsed), "unknown"),
        # phonenumbers returns the sentinel "Etc/Unknown" rather than nothing.
        timezones=tuple(
            tz for tz in timezone.time_zones_for_number(parsed) if tz != "Etc/Unknown"
        ),
        international_format=phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        ),
        national_format=phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        ),
    )


def mask_phone(e164: str) -> str:
    """Redact the subscriber digits for logging."""
    if len(e164) <= 6:
        return "***"
    return f"{e164[:5]}{'*' * (len(e164) - 7)}{e164[-2:]}"
