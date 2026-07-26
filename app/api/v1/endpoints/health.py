import redis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.dependencies.common import RedisDep, SessionDep

router = APIRouter(tags=["System"])


@router.get("/health", summary="Liveness and dependency check")
def health(session: SessionDep, redis_client: RedisDep) -> dict[str, object]:
    checks = {"database": "ok", "redis": "ok"}

    try:
        session.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"

    try:
        redis_client.ping()
    except redis.RedisError:
        checks["redis"] = "unavailable"

    healthy = all(value == "ok" for value in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }
