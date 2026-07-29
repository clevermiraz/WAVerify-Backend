"""Email -> public profile enrichment via Gravatar.

Gravatar keys every profile on the SHA256 of the lowercased, trimmed email
(https://docs.gravatar.com/rest-api/). The public endpoint answers without a
key at 100 requests/hour; a key raises that to 1000 but is never required, so
this stays a best-effort side-channel: any failure returns ``None`` and never
takes a lookup down with it.
"""

import hashlib
import json

import httpx
import redis

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.check import GravatarAccount, GravatarProfile

logger = get_logger(__name__)

_API_BASE = "https://api.gravatar.com/v3/profiles/"
_CACHE_PREFIX = "gravatar:"
# Distinguishes "we asked Gravatar and there is no profile" from "never asked",
# so a miss is cached too and we do not re-hit the API for every repeat.
_MISS_SENTINEL = "__miss__"


def email_hash(email: str) -> str:
    """Gravatar identifier for an email: SHA256 of its normalised form."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class GravatarService:
    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client

    def lookup(self, email: str) -> GravatarProfile | None:
        """Return the public Gravatar profile for an email, or ``None``.

        ``None`` means "no usable profile" for every reason — disabled,
        no account, network error, malformed response — on purpose: the caller
        treats enrichment as optional and must not branch on why it was absent.
        """
        if not settings.GRAVATAR_ENABLED or not email:
            return None

        digest = email_hash(email)

        cached = self._read_cache(digest)
        if cached is _MISS_SENTINEL:
            return None
        if cached is not None:
            return GravatarProfile(**cached)

        data = self._fetch(digest)
        if data is None:
            self._write_cache(digest, _MISS_SENTINEL)
            return None

        profile = self._to_profile(data)
        self._write_cache(digest, profile.model_dump(mode="json"))
        return profile

    # --- HTTP ------------------------------------------------------------

    def _fetch(self, digest: str) -> dict | None:
        headers = {"Accept": "application/json"}
        if settings.GRAVATAR_API_KEY:
            headers["Authorization"] = f"Bearer {settings.GRAVATAR_API_KEY}"
        try:
            response = httpx.get(
                f"{_API_BASE}{digest}",
                headers=headers,
                timeout=settings.GRAVATAR_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            logger.warning("gravatar.request_failed", error=str(exc))
            return None

        if response.status_code == 404:
            # No Gravatar account for this email — a normal, expected outcome.
            return None
        if response.status_code == 429:
            logger.warning("gravatar.rate_limited")
            return None
        if response.status_code >= 400:
            logger.warning("gravatar.error_response", status=response.status_code)
            return None

        try:
            return response.json()
        except json.JSONDecodeError:
            logger.warning("gravatar.bad_json")
            return None

    # --- Cache -----------------------------------------------------------

    def _cache_key(self, digest: str) -> str:
        return f"{_CACHE_PREFIX}{digest}"

    def _read_cache(self, digest: str) -> dict | str | None:
        if self.redis is None or settings.GRAVATAR_CACHE_TTL_SECONDS <= 0:
            return None
        try:
            raw = self.redis.get(self._cache_key(digest))
        except redis.RedisError as exc:
            logger.warning("gravatar.cache_unavailable", error=str(exc))
            return None
        if not raw:
            return None
        if raw == _MISS_SENTINEL:
            return _MISS_SENTINEL
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _write_cache(self, digest: str, value: dict | str) -> None:
        if self.redis is None or settings.GRAVATAR_CACHE_TTL_SECONDS <= 0:
            return
        payload = value if isinstance(value, str) else json.dumps(value)
        try:
            self.redis.setex(
                self._cache_key(digest),
                settings.GRAVATAR_CACHE_TTL_SECONDS,
                payload,
            )
        except redis.RedisError as exc:
            logger.warning("gravatar.cache_write_failed", error=str(exc))

    # --- Mapping ---------------------------------------------------------

    @staticmethod
    def _to_profile(data: dict) -> GravatarProfile:
        accounts = [
            GravatarAccount(
                service=acc.get("service_label") or acc.get("service_type") or "unknown",
                url=acc["url"],
            )
            for acc in data.get("verified_accounts", [])
            if acc.get("url") and not acc.get("is_hidden")
        ]
        return GravatarProfile(
            display_name=data.get("display_name") or None,
            about=data.get("description") or None,
            location=data.get("location") or None,
            job_title=data.get("job_title") or None,
            company=data.get("company") or None,
            pronouns=data.get("pronouns") or None,
            avatar_url=data.get("avatar_url") or None,
            profile_url=data.get("profile_url") or None,
            verified_accounts=accounts,
        )
