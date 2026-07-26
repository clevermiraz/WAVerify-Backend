"""E.164 phone number parsing and normalisation."""

from dataclasses import dataclass

import phonenumbers

from app.core.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ParsedPhone:
    e164: str
    country_code: str
    national_number: str


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
    )


def mask_phone(e164: str) -> str:
    """Redact the subscriber digits for logging."""
    if len(e164) <= 6:
        return "***"
    return f"{e164[:5]}{'*' * (len(e164) - 7)}{e164[-2:]}"
