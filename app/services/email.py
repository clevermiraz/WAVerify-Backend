"""Transactional email delivery using Resend."""

import resend

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Initialize resend with the API key
resend.api_key = settings.RESEND_API_KEY


class EmailService:
    def send_verification_email(self, *, to: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        self._send(
            to=to,
            subject="Verify your WAVerify email address",
            body=(
                "Welcome to WAVerify.\n\n"
                f"Confirm your email address to activate your account:\n{link}\n\n"
                f"This link expires in {settings.EMAIL_TOKEN_EXPIRE_HOURS} hours."
            ),
        )

    def send_password_reset_email(self, *, to: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        self._send(
            to=to,
            subject="Reset your WAVerify password",
            body=(
                "We received a request to reset your WAVerify password.\n\n"
                f"Choose a new password here:\n{link}\n\n"
                f"This link expires in {settings.PASSWORD_RESET_EXPIRE_HOURS} hours. "
                "If you did not request this, you can safely ignore this email."
            ),
        )

    def _send(self, *, to: str, subject: str, body: str) -> None:
        if not settings.RESEND_API_KEY:
            # Fallback for local development if no key is set
            logger.info("email.sent", backend="console", to=to, subject=subject, body=body)
            return

        try:
            params: resend.Emails.SendParams = {
                "from": settings.EMAIL_FROM,
                "to": [to],
                "subject": subject,
                "text": body,
            }
            resend.Emails.send(params)
            logger.info("email.sent", backend="resend", to=to, subject=subject)
        except Exception as exc:
            # Never fail the caller's request because delivery failed —
            # registration and password reset both stay usable via resend.
            logger.error("email.delivery_failed", to=to, subject=subject, error=str(exc))
