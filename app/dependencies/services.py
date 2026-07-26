"""Service providers.

Constructing services through dependencies keeps endpoints free of wiring
and makes each service trivially replaceable in tests.
"""

from typing import Annotated

from fastapi import Depends

from app.dependencies.common import RedisDep, SessionDep
from app.services.admin import AdminService
from app.services.api_key import ApiKeyService
from app.services.auth import AuthService
from app.services.billing import BillingService
from app.services.history import SearchHistoryService
from app.services.usage import UsageService
from app.services.user import UserService
from app.services.verification import VerificationService


def get_auth_service(session: SessionDep, redis_client: RedisDep) -> AuthService:
    return AuthService(session, redis_client)


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_api_key_service(session: SessionDep) -> ApiKeyService:
    return ApiKeyService(session)


def get_verification_service(
    session: SessionDep, redis_client: RedisDep
) -> VerificationService:
    return VerificationService(session, redis_client)


def get_usage_service(session: SessionDep) -> UsageService:
    return UsageService(session)


def get_billing_service(session: SessionDep) -> BillingService:
    return BillingService(session)


def get_history_service(session: SessionDep) -> SearchHistoryService:
    return SearchHistoryService(session)


def get_admin_service(session: SessionDep) -> AdminService:
    return AdminService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]
VerificationServiceDep = Annotated[VerificationService, Depends(get_verification_service)]
UsageServiceDep = Annotated[UsageService, Depends(get_usage_service)]
BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
HistoryServiceDep = Annotated[SearchHistoryService, Depends(get_history_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
