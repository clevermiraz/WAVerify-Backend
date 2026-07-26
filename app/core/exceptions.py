"""Domain exceptions.

Services raise these; a single handler in `main.py` turns them into the
uniform error envelope the API contract promises.
"""

from typing import Any


class AppError(Exception):
    """Base class for all expected, user-facing failures."""

    status_code: int = 400
    code: str = "bad_request"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"
    message = "Invalid credentials."


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"
    message = "This link is invalid or has expired."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have access to this resource."


class EmailNotVerifiedError(AppError):
    status_code = 403
    code = "email_not_verified"
    message = "Please verify your email address to continue."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists."


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
    message = "Too many requests. Please slow down."


class QuotaExceededError(AppError):
    status_code = 402
    code = "quota_exceeded"
    message = "Monthly request quota exhausted. Upgrade your plan to continue."


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"
    message = "The verification provider is temporarily unavailable."
