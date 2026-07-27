"""Per-principal rate limiting backed by Redis.

Fixed-window counter: cheap, one round trip, and accurate enough for an
abuse guard. The window resets on the minute boundary.
"""

import time
from typing import Annotated

import redis
from fastapi import Depends

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.dependencies.auth import Principal, VerifiedPrincipalDep
from app.dependencies.common import RedisDep, SessionDep
from app.services.billing import BillingService

logger = get_logger(__name__)

_PREFIX = "ratelimit:"


def enforce_rate_limit(
    principal: VerifiedPrincipalDep,
    redis_client: RedisDep,
    session: SessionDep,
) -> Principal:
    if not settings.RATE_LIMIT_ENABLED:
        return principal

    wallet = BillingService(session).get_wallet(principal.user.id)
    limit = wallet.plan.rate_limit_per_minute or settings.RATE_LIMIT_PER_MINUTE

    window = int(time.time() // 60)
    key = f"{_PREFIX}{principal.rate_limit_key}:{window}"

    try:
        pipeline = redis_client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, 90)
        count, _ = pipeline.execute()
    except redis.RedisError as exc:
        # Fail open: a Redis outage should degrade abuse protection, not
        # take the API offline.
        logger.warning("rate_limit.unavailable", error=str(exc))
        return principal

    if int(count) > limit:
        raise RateLimitError(
            f"Rate limit of {limit} requests per minute exceeded on the "
            f"{wallet.plan.name} plan."
        )
    return principal


RateLimitedPrincipalDep = Annotated[Principal, Depends(enforce_rate_limit)]
