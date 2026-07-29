"""Orchestrates a single number lookup.

Sequence: validate → enforce quota → serve from cache or call the provider →
persist a search log → roll up usage. The search log is written for failures
too, so the usage page can show an honest success rate.
"""

import json
import time
import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProviderError, QuotaExceededError
from app.core.logging import get_logger
from app.models.search_log import LookupSource, LookupStatus, SearchLog
from app.models.user import User
from app.repositories.search_log import SearchLogRepository
from app.repositories.usage import UsageRepository
from app.schemas.check import CheckResponse, GravatarProfile, NumberInfo
from app.services.billing import BillingService
from app.services.gravatar import GravatarService
from app.services.providers.base import ProviderResult
from app.services.providers.registry import get_provider
from app.utils.phone import ParsedPhone, mask_phone, parse_phone

logger = get_logger(__name__)

_CACHE_PREFIX = "lookup:"


class VerificationService:
    def __init__(self, session: Session, redis_client: redis.Redis) -> None:
        self.session = session
        self.redis = redis_client
        self.logs = SearchLogRepository(session)
        self.usage = UsageRepository(session)
        self.billing = BillingService(session)
        self.gravatar = GravatarService(redis_client)
        self.provider = get_provider()

    def check(
        self,
        *,
        user: User,
        raw_phone: str,
        source: LookupSource = LookupSource.DASHBOARD,
        api_key_id: uuid.UUID | None = None,
        email: str | None = None,
    ) -> CheckResponse:
        phone = parse_phone(raw_phone)
        self._assert_within_quota(user)

        # Derived from the phone alone, so it is valid on every path including
        # failures. Built once and reused by both persistence and the response.
        number_info = self._number_info(phone)
        # Email enrichment is independent of the WhatsApp lookup and its cache,
        # so resolve it once up front and attach to whichever path answers.
        gravatar = self.gravatar.lookup(email) if email else None

        started = time.perf_counter()
        cached_payload = self._read_cache(phone)

        if cached_payload is not None:
            result = ProviderResult(**cached_payload)
            elapsed_ms = self._elapsed_ms(started)
            self._persist(
                user=user,
                phone=phone,
                result=result,
                elapsed_ms=elapsed_ms,
                source=source,
                api_key_id=api_key_id,
                cached=True,
                number_info=number_info,
                gravatar=gravatar,
            )
            return self._to_response(
                phone, result, elapsed_ms, cached=True,
                number_info=number_info, gravatar=gravatar,
            )

        try:
            result = self.provider.check(phone)
        except ProviderError as exc:
            elapsed_ms = self._elapsed_ms(started)
            self._persist_failure(
                user=user,
                phone=phone,
                elapsed_ms=elapsed_ms,
                source=source,
                api_key_id=api_key_id,
                error_code=exc.code,
                number_info=number_info,
                gravatar=gravatar,
            )
            logger.warning(
                "verification.failed",
                user_id=str(user.id),
                phone=mask_phone(phone.e164),
                error=exc.code,
            )
            raise

        elapsed_ms = self._elapsed_ms(started)
        self._write_cache(phone, result)
        self._persist(
            user=user,
            phone=phone,
            result=result,
            elapsed_ms=elapsed_ms,
            source=source,
            api_key_id=api_key_id,
            cached=False,
            number_info=number_info,
            gravatar=gravatar,
        )
        logger.info(
            "verification.completed",
            user_id=str(user.id),
            phone=mask_phone(phone.e164),
            exists=result.exists,
            response_time_ms=elapsed_ms,
        )
        return self._to_response(
            phone, result, elapsed_ms, cached=False,
            number_info=number_info, gravatar=gravatar,
        )

    # --- Quota -----------------------------------------------------------

    def _assert_within_quota(self, user: User) -> None:
        wallet = self.billing.get_wallet(user.id)
        remaining = self.billing.remaining_quota(user.id, wallet)
        if remaining is not None and remaining <= 0:
            raise QuotaExceededError(
                f"You have run out of credits. Please top-up your wallet to continue."
            )

    # --- Cache -----------------------------------------------------------

    def _cache_key(self, phone: ParsedPhone) -> str:
        return f"{_CACHE_PREFIX}{phone.e164}"

    def _read_cache(self, phone: ParsedPhone) -> dict | None:
        if settings.VERIFICATION_CACHE_TTL_SECONDS <= 0:
            return None
        try:
            raw = self.redis.get(self._cache_key(phone))
        except redis.RedisError as exc:
            # A cache outage must not take the product down.
            logger.warning("verification.cache_unavailable", error=str(exc))
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _write_cache(self, phone: ParsedPhone, result: ProviderResult) -> None:
        if settings.VERIFICATION_CACHE_TTL_SECONDS <= 0:
            return
        payload = {
            "exists": result.exists,
            "display_name": result.display_name,
            "name_source": result.name_source,
            "about": result.about,
            "is_business": result.is_business,
            "profile_photo_url": result.profile_photo_url,
            "profile_photo_id": result.profile_photo_id,
            "device_count": result.device_count,
        }
        try:
            self.redis.setex(
                self._cache_key(phone),
                settings.VERIFICATION_CACHE_TTL_SECONDS,
                json.dumps(payload),
            )
        except redis.RedisError as exc:
            logger.warning("verification.cache_write_failed", error=str(exc))

    # --- Persistence -----------------------------------------------------

    def _persist(
        self,
        *,
        user: User,
        phone: ParsedPhone,
        result: ProviderResult,
        elapsed_ms: int,
        source: LookupSource,
        api_key_id: uuid.UUID | None,
        cached: bool,
        number_info: NumberInfo | None = None,
        gravatar: GravatarProfile | None = None,
    ) -> SearchLog:
        log = self.logs.create(
            user_id=user.id,
            api_key_id=api_key_id,
            phone_number=phone.e164,
            country_code=phone.country_code,
            status=LookupStatus.EXISTS if result.exists else LookupStatus.NOT_FOUND,
            source=source,
            exists_on_whatsapp=result.exists,
            display_name=result.display_name,
            about=result.about,
            is_business=result.is_business,
            profile_photo_url=result.profile_photo_url,
            number_info=number_info.model_dump(mode="json") if number_info else None,
            gravatar=gravatar.model_dump(mode="json") if gravatar else None,
            response_time_ms=elapsed_ms,
            cached=cached,
        )
        self.usage.record(
            user_id=user.id,
            day=datetime.now(UTC).date(),
            succeeded=True,
            response_time_ms=elapsed_ms,
        )
        self.billing.deduct_quota(user.id)
        return log

    def _persist_failure(
        self,
        *,
        user: User,
        phone: ParsedPhone,
        elapsed_ms: int,
        source: LookupSource,
        api_key_id: uuid.UUID | None,
        error_code: str,
        number_info: NumberInfo | None = None,
        gravatar: GravatarProfile | None = None,
    ) -> None:
        self.logs.create(
            user_id=user.id,
            api_key_id=api_key_id,
            phone_number=phone.e164,
            country_code=phone.country_code,
            status=LookupStatus.FAILED,
            source=source,
            number_info=number_info.model_dump(mode="json") if number_info else None,
            gravatar=gravatar.model_dump(mode="json") if gravatar else None,
            response_time_ms=elapsed_ms,
            error_code=error_code,
        )
        self.usage.record(
            user_id=user.id,
            day=datetime.now(UTC).date(),
            succeeded=False,
            response_time_ms=elapsed_ms,
        )
        self.billing.deduct_quota(user.id)
        # The provider failed, not the caller — commit the audit trail before
        # the exception handler unwinds the request.
        self.session.commit()

    # --- Helpers ---------------------------------------------------------

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(1, round((time.perf_counter() - started) * 1000))

    @staticmethod
    def _number_info(phone: ParsedPhone) -> NumberInfo:
        return NumberInfo(
            country_code=phone.country_code,
            region=phone.region,
            location=phone.location,
            carrier=phone.carrier,
            line_type=phone.line_type,
            timezones=list(phone.timezones),
            international_format=phone.international_format,
            national_format=phone.national_format,
        )

    @staticmethod
    def _to_response(
        phone: ParsedPhone,
        result: ProviderResult,
        elapsed_ms: int,
        *,
        cached: bool,
        number_info: NumberInfo | None = None,
        gravatar: GravatarProfile | None = None,
    ) -> CheckResponse:
        return CheckResponse(
            phone=phone.e164,
            exists=result.exists,
            display_name=result.display_name,
            name_source=result.name_source,
            about=result.about,
            business=result.is_business,
            profile_photo=result.profile_photo_url,
            profile_photo_id=result.profile_photo_id,
            device_count=result.device_count,
            number_info=number_info or VerificationService._number_info(phone),
            gravatar=gravatar,
            response_time_ms=elapsed_ms,
            cached=cached,
            checked_at=datetime.now(UTC),
        )
