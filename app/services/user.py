"""Profile management and account deletion."""

from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.logging import get_logger
from app.core.security import verify_password
from app.models.user import User
from app.repositories.user import UserRepository

logger = get_logger(__name__)


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def update_profile(
        self, user: User, *, full_name: str | None, company: str | None
    ) -> User:
        return self.users.update(
            user,
            full_name=full_name.strip() if full_name else None,
            company=company.strip() if company else None,
        )

    def delete_account(self, user: User, *, password: str | None) -> None:
        # Google-only accounts have no password to confirm with; the access
        # token on the request is the only credential they ever have.
        if user.has_password and not verify_password(
            password or "", user.hashed_password
        ):
            raise AuthenticationError("Password is incorrect.")
        if user.is_admin:
            # Removing the last admin would lock everyone out of the panel.
            raise PermissionDeniedError(
                "Admin accounts cannot be deleted from the dashboard."
            )

        # Subscriptions, API keys and search logs cascade with the user.
        logger.info("user.deleted", user_id=str(user.id))
        self.users.delete(user)
