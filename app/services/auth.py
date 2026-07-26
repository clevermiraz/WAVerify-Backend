"""Registration, login, token refresh, email verification, password reset."""

import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidTokenError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    TokenType,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_reset_fingerprint,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenPair
from app.services.billing import BillingService
from app.services.email import EmailService

logger = get_logger(__name__)

_REVOKED_PREFIX = "auth:revoked_refresh:"


class AuthService:
    def __init__(
        self,
        session: Session,
        redis_client: redis.Redis,
        email_service: EmailService | None = None,
    ) -> None:
        self.session = session
        self.redis = redis_client
        self.users = UserRepository(session)
        self.billing = BillingService(session)
        self.email = email_service or EmailService()

    # --- Registration ----------------------------------------------------

    def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None,
        company: str | None,
    ) -> User:
        normalized = email.strip().lower()
        if self.users.email_exists(normalized):
            raise ConflictError("An account with this email already exists.")

        user = self.users.create(
            email=normalized,
            hashed_password=hash_password(password),
            full_name=full_name.strip() if full_name else None,
            company=company.strip() if company else None,
        )
        self.billing.create_default_subscription(user.id)

        self.email.send_verification_email(
            to=user.email, token=create_email_verification_token(str(user.id))
        )
        logger.info("auth.registered", user_id=str(user.id))
        return user

    # --- Login -----------------------------------------------------------

    def authenticate(self, *, email: str, password: str) -> User:
        user = self.users.get_by_email(email)
        # Hash even when the user is missing so response time does not reveal
        # which addresses are registered.
        stored_hash = user.hashed_password if user else _DUMMY_HASH
        password_ok = verify_password(password, stored_hash)

        if user is None or not password_ok:
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise AuthenticationError("This account has been deactivated.")

        self.users.update(user, last_login_at=datetime.now(UTC))
        return user

    def issue_tokens(self, user: User) -> TokenPair:
        access = create_access_token(str(user.id), role=user.role.value)
        refresh, _ = create_refresh_token(str(user.id))
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, TokenType.REFRESH)
        jti = payload.get("jti", "")
        if self.redis.exists(f"{_REVOKED_PREFIX}{jti}"):
            raise InvalidTokenError("This session has been signed out.")

        user = self.users.get(_as_uuid(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("This account is no longer active.")

        # Rotate: the presented token is burned so a stolen copy cannot be
        # replayed after the legitimate client refreshes.
        self._revoke(jti, payload.get("exp"))
        return self.issue_tokens(user)

    def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError:
            # Already unusable; logging out is idempotent from the client's
            # point of view.
            return
        self._revoke(payload.get("jti", ""), payload.get("exp"))

    def _revoke(self, jti: str, exp: int | None) -> None:
        if not jti:
            return
        ttl = max(1, int(exp - datetime.now(UTC).timestamp())) if exp else 60
        self.redis.setex(f"{_REVOKED_PREFIX}{jti}", ttl, "1")

    # --- Email verification ----------------------------------------------

    def verify_email(self, token: str) -> User:
        payload = decode_token(token, TokenType.EMAIL_VERIFY)
        user = self.users.get(_as_uuid(payload["sub"]))
        if user is None:
            raise InvalidTokenError()

        if not user.is_email_verified:
            self.users.update(
                user, is_email_verified=True, email_verified_at=datetime.now(UTC)
            )
        return user

    def resend_verification(self, email: str) -> None:
        user = self.users.get_by_email(email)
        # Always succeed from the caller's perspective so this cannot be used
        # to enumerate registered addresses.
        if user is None or user.is_email_verified:
            return
        self.email.send_verification_email(
            to=user.email, token=create_email_verification_token(str(user.id))
        )

    # --- Password reset --------------------------------------------------

    def request_password_reset(self, email: str) -> None:
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            return
        self.email.send_password_reset_email(
            to=user.email,
            token=create_password_reset_token(str(user.id), user.hashed_password),
        )
        logger.info("auth.password_reset_requested", user_id=str(user.id))

    def reset_password(self, *, token: str, new_password: str) -> User:
        payload = decode_token(token, TokenType.PASSWORD_RESET)
        user = self.users.get(_as_uuid(payload["sub"]))
        if user is None or not user.is_active:
            raise InvalidTokenError()

        # The fingerprint stops a reset link from working twice.
        if payload.get("fp") != password_reset_fingerprint(user.hashed_password):
            raise InvalidTokenError("This link has already been used.")

        self.users.update(user, hashed_password=hash_password(new_password))
        logger.info("auth.password_reset", user_id=str(user.id))
        return user

    def change_password(self, user: User, *, current: str, new: str) -> None:
        if not verify_password(current, user.hashed_password):
            raise AuthenticationError("Your current password is incorrect.")
        if current == new:
            raise ValidationError("The new password must differ from the current one.")
        self.users.update(user, hashed_password=hash_password(new))
        logger.info("auth.password_changed", user_id=str(user.id))


def _as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise InvalidTokenError() from exc


# Pre-computed so the "unknown email" branch of `authenticate` performs the
# same bcrypt work as the "known email" branch.
_DUMMY_HASH = hash_password("waverify-timing-equalizer")
