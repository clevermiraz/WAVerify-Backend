"""Transactional email delivery using Resend."""

import resend

from app.core.config import settings
from app.core.logging import get_logger
from app.services.email_templates import SUPPORT_ADDRESS, render_email

logger = get_logger(__name__)

# Initialize resend with the API key
resend.api_key = settings.RESEND_API_KEY


class EmailService:
    def send_verification_email(self, *, to: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        expiry = (
            f"This link expires in {settings.EMAIL_TOKEN_EXPIRE_HOURS} "
            f"hour{'s' if settings.EMAIL_TOKEN_EXPIRE_HOURS != 1 else ''}."
        )
        closing = "If you did not create a WAVerify account, you can ignore this email."
        self._send(
            to=to,
            subject="Verify your WAVerify email address",
            body=(
                "Welcome to WAVerify.\n\n"
                f"Confirm your email address to activate your account:\n{link}\n\n"
                f"{expiry}\n\n{closing}"
            ),
            html=render_email(
                preheader="Confirm your email address to activate your account.",
                heading="Confirm your email address",
                intro=(
                    "Welcome to WAVerify. Verify this address to activate your account "
                    "and start checking numbers."
                ),
                cta_label="Verify email address",
                cta_url=link,
                expiry_note=expiry,
                closing=closing,
            ),
        )

    def send_password_reset_email(self, *, to: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        expiry = (
            f"This link expires in {settings.PASSWORD_RESET_EXPIRE_HOURS} "
            f"hour{'s' if settings.PASSWORD_RESET_EXPIRE_HOURS != 1 else ''}."
        )
        closing = (
            "If you did not request this, you can safely ignore this email — "
            "your password stays unchanged."
        )
        self._send(
            to=to,
            subject="Reset your WAVerify password",
            body=(
                "We received a request to reset your WAVerify password.\n\n"
                f"Choose a new password here:\n{link}\n\n"
                f"{expiry}\n\n{closing}"
            ),
            html=render_email(
                preheader="Choose a new password for your WAVerify account.",
                heading="Reset your password",
                intro=(
                    "We received a request to reset the password for your WAVerify "
                    "account. Choose a new one below."
                ),
                cta_label="Choose a new password",
                cta_url=link,
                expiry_note=expiry,
                closing=closing,
            ),
        )

    def _send(self, *, to: str, subject: str, body: str, html: str | None = None) -> None:
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
                # `EMAIL_FROM` is a no-reply identity, so point replies at the
                # inbox a human actually reads.
                "reply_to": SUPPORT_ADDRESS,
            }
            if html:
                # Sent alongside the text part, not instead of it: clients that
                # refuse HTML still get a usable link.
                params["html"] = html
            resend.Emails.send(params)
            logger.info("email.sent", backend="resend", to=to, subject=subject)
        except Exception as exc:
            # Never fail the caller's request because delivery failed —
            # registration and password reset both stay usable via resend.
            logger.error("email.delivery_failed", to=to, subject=subject, error=str(exc))
