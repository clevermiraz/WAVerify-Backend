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


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=150)
    company: str | None = Field(default=None, max_length=150)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=72)
