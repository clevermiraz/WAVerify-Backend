"""Authentication and authorisation dependencies.

Two credential types reach the API:

* a Bearer JWT from the dashboard, and
* an `X-API-Key` header from server-to-server integrations.

`CurrentUserDep` accepts only the former. `PrincipalDep` accepts either and
reports which one was used, so lookups can be attributed to a key.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    EmailNotVerifiedError,
    InvalidTokenError,
    PermissionDeniedError,
)
from app.core.security import TokenType, decode_token
from app.dependencies.common import SessionDep
from app.dependencies.services import ApiKeyServiceDep
from app.models.search_log import LookupSource
from app.models.user import User
from app.repositories.user import UserRepository

# `auto_error=False` so a missing header raises our own error envelope
# instead of FastAPI's default 403 body.
_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_current_user(
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required.")

    payload = decode_token(credentials.credentials, TokenType.ACCESS)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise InvalidTokenError() from exc

    user = UserRepository(session).get(user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_verified_user(user: CurrentUserDep) -> User:
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.is_email_verified:
        raise EmailNotVerifiedError()
    return user


VerifiedUserDep = Annotated[User, Depends(get_verified_user)]


def get_admin_user(user: CurrentUserDep) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Administrator access required.")
    return user


AdminUserDep = Annotated[User, Depends(get_admin_user)]


@dataclass(slots=True)
class Principal:
    """Whoever is making the request, and how they authenticated."""

    user: User
    source: LookupSource
    api_key_id: uuid.UUID | None = None

    @property
    def rate_limit_key(self) -> str:
        if self.api_key_id:
            return f"key:{self.api_key_id}"
        return f"user:{self.user.id}"


def get_principal(
    request: Request,
    session: SessionDep,
    api_keys: ApiKeyServiceDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    if x_api_key:
        api_key = api_keys.authenticate(x_api_key.strip())
        if api_key is None:
            raise AuthenticationError("Invalid API key.", code="invalid_api_key")
        if not api_key.user.is_active:
            raise AuthenticationError("This account has been deactivated.")
        return Principal(
            user=api_key.user, source=LookupSource.API, api_key_id=api_key.id
        )

    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError(
            "Provide an API key in the X-API-Key header, or a Bearer access token."
        )

    payload = decode_token(token, TokenType.ACCESS)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise InvalidTokenError() from exc

    user = UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("This account is no longer active.")
    return Principal(user=user, source=LookupSource.DASHBOARD)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_verified_principal(principal: PrincipalDep) -> Principal:
    if settings.REQUIRE_EMAIL_VERIFICATION and not principal.user.is_email_verified:
        raise EmailNotVerifiedError()
    return principal


VerifiedPrincipalDep = Annotated[Principal, Depends(get_verified_principal)]
