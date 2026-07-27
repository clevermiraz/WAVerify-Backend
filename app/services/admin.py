"""Read-mostly admin operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.user import User, UserRole
from app.repositories.api_key import ApiKeyRepository
from app.repositories.search_log import SearchLogRepository
from app.repositories.wallet import WalletRepository
from app.repositories.user import UserRepository
from app.schemas.admin import (
    AdminApiKeyRead,
    AdminSearchLogRead,
    AdminStats,
    AdminWalletRead,
    AdminUserRead,
    SystemSettings,
)
from app.schemas.common import Page

logger = get_logger(__name__)


class AdminService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.api_keys = ApiKeyRepository(session)
        self.logs = SearchLogRepository(session)
        self.wallets = WalletRepository(session)

    def stats(self) -> AdminStats:
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return AdminStats(
            total_users=self.users.count(),
            active_users=self.users.count_where_active(),
            verified_users=self.users.count_where_verified(),
            total_searches=self.logs.count(),
            searches_today=self.logs.count_since(midnight),
            active_api_keys=self.api_keys.count_active(),
            success_rate=self.logs.global_success_rate(),
        )

    def list_users(
        self, *, page: int, page_size: int, query: str | None = None
    ) -> Page[AdminUserRead]:
        rows, total = self.users.search(
            query=query, limit=page_size, offset=(page - 1) * page_size
        )

        user_ids = [row.id for row in rows]
        lookup_counts = self.logs.get_counts_for_users(
            user_ids) if user_ids else {}

        items = []
        for row in rows:
            data = AdminUserRead.model_validate(row).model_dump()
            data["total_lookups"] = lookup_counts.get(row.id, 0)
            items.append(AdminUserRead(**data))

        return Page.create(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def update_user(
        self,
        actor: User,
        user_id: uuid.UUID,
        *,
        is_active: bool | None,
        role: UserRole | None,
    ) -> AdminUserRead:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        if user.id == actor.id:
            # Prevents an admin from locking themselves out mid-session.
            raise PermissionDeniedError("You cannot modify your own admin account.")

        changes: dict[str, object] = {}
        if is_active is not None:
            changes["is_active"] = is_active
        if role is not None:
            changes["role"] = role
        if changes:
            self.users.update(user, **changes)
            logger.info("admin.user_updated", actor_id=str(actor.id), user_id=str(user_id))
        return AdminUserRead.model_validate(user)

    def list_wallets(
        self, *, page: int, page_size: int
    ) -> Page[AdminWalletRead]:
        rows, total = self.wallets.paginate(
            limit=page_size, offset=(page - 1) * page_size
        )
        return Page.create(
            items=[
                AdminWalletRead(
                    id=row.id,
                    user_id=row.user_id,
                    user_email=row.user.email,
                    plan_name=row.plan.name,
                    credits_balance=row.credits_balance,
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_api_keys(self, *, page: int, page_size: int) -> Page[AdminApiKeyRead]:
        rows, total = self.api_keys.paginate(
            limit=page_size, offset=(page - 1) * page_size
        )
        return Page.create(
            items=[AdminApiKeyRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_search_logs(
        self, *, page: int, page_size: int, query: str | None = None
    ) -> Page[AdminSearchLogRead]:
        rows, total = self.logs.paginate(
            query=query, limit=page_size, offset=(page - 1) * page_size
        )
        return Page.create(
            items=[
                AdminSearchLogRead(
                    id=row.id,
                    user_id=row.user_id,
                    user_email=row.user.email if row.user else None,
                    phone_number=row.phone_number,
                    status=row.status.value,
                    source=row.source.value,
                    response_time_ms=row.response_time_ms,
                    created_at=row.created_at,
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def system_settings() -> SystemSettings:
        return SystemSettings(
            environment=settings.ENVIRONMENT,
            verification_cache_ttl_seconds=settings.VERIFICATION_CACHE_TTL_SECONDS,
            rate_limit_enabled=settings.RATE_LIMIT_ENABLED,
            rate_limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
            email_backend="resend" if settings.RESEND_API_KEY else "console",
        )
