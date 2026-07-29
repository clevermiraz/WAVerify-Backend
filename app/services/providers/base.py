"""Verification provider interface.

WhatsApp exposes no official public "does this number have an account"
endpoint, so the concrete lookup is treated as a swappable dependency. Every
adapter implements `WhatsAppProvider`; the rest of the application only ever
sees `ProviderResult` and never learns which backend answered.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.utils.phone import ParsedPhone


@dataclass(frozen=True, slots=True)
class ProviderResult:
    exists: bool
    display_name: str | None = None
    # Where display_name came from, so callers can tell "hidden by privacy"
    # apart from "this backend cannot see personal names at all".
    name_source: str | None = None
    about: str | None = None
    is_business: bool = False
    profile_photo_url: str | None = None
    profile_photo_id: str | None = None
    device_count: int | None = None


class WhatsAppProvider(ABC):
    """Contract every verification backend must satisfy."""

    name: str

    @abstractmethod
    def check(self, phone: ParsedPhone) -> ProviderResult:
        """Look up a number.

        Raises `ProviderError` when the upstream is unreachable or returns an
        unusable response. Returning `exists=False` means the lookup
        succeeded and the number has no account — the two cases are billed
        and logged differently, so adapters must not conflate them.
        """

    def close(self) -> None:  # noqa: B027 — optional hook, not every adapter holds resources
        """Release adapter-held resources. Overridden where relevant."""
