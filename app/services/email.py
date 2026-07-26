"""Transactional email delivery.

The MVP ships a console backend that writes the rendered message to the
structured log — enough to complete every auth flow locally — plus an SMTP
backend for real deployments.
"""

import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
        if settings.EMAIL_BACKEND == "smtp":
            self._send_smtp(to=to, subject=subject, body=body)
        else:
            logger.info("email.sent", backend="console", to=to, subject=subject, body=body)

    def _send_smtp(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            host = settings.SMTP_HOST or ""
            with smtplib.SMTP(host, settings.SMTP_PORT, timeout=10) as smtp:
                smtp.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # Never fail the caller's request because delivery failed —
            # registration and password reset both stay usable via resend.
            logger.error("email.delivery_failed", to=to, subject=subject, error=str(exc))
            return

        logger.info("email.sent", backend="smtp", to=to, subject=subject)
