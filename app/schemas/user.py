import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole
from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    company: str | None
    role: UserRole
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    # Which sign-in methods this account actually has, so the dashboard can
    # hide password controls from Google-only users instead of showing forms
    # that are guaranteed to fail.
    has_password: bool
    has_google: bool


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=150)
    company: str | None = Field(default=None, max_length=150)


class DeleteAccountRequest(BaseModel):
    # Optional: a Google-only account has no password to confirm with. The
    # request is still authenticated by the access token.
    password: str | None = Field(default=None, max_length=72)
