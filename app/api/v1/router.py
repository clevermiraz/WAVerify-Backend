"""Aggregates every v1 endpoint module."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    api_keys,
    auth,
    billing,
    check,
    health,
    usage,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(check.router)
api_router.include_router(api_keys.router)
api_router.include_router(usage.router)
api_router.include_router(billing.router)
api_router.include_router(admin.router)
