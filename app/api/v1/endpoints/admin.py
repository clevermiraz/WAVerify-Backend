import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.dependencies.auth import AdminUserDep
from app.dependencies.common import PaginationDep
from app.dependencies.services import AdminServiceDep
from app.models.plan import Plan
from app.models.whatsapp_account import WhatsAppAccount
from app.repositories.plan import PlanRepository
from app.schemas.admin import (
    AdminApiKeyRead,
    AdminPlanCreate,
    AdminPlanUpdate,
    AdminSearchLogRead,
    AdminStats,
    AdminWalletRead,
    AdminUserRead,
    AdminUserUpdate,
    SystemSettings,
)
from app.schemas.billing import PlanRead
from app.schemas.common import Page

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStats)
def stats(_: AdminUserDep, service: AdminServiceDep) -> AdminStats:
    return service.stats()


@router.get("/users", response_model=Page[AdminUserRead])
def list_users(
    _: AdminUserDep,
    service: AdminServiceDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Page[AdminUserRead]:
    return service.list_users(
        page=pagination.page, page_size=pagination.page_size, query=q
    )


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    actor: AdminUserDep,
    service: AdminServiceDep,
) -> AdminUserRead:
    """Activate, deactivate or change the role of an account."""
    return service.update_user(
        actor, user_id, is_active=payload.is_active, role=payload.role
    )


@router.get("/wallets", response_model=Page[AdminWalletRead])
def list_wallets(
    _: AdminUserDep, service: AdminServiceDep, pagination: PaginationDep
) -> Page[AdminWalletRead]:
    return service.list_wallets(
        page=pagination.page, page_size=pagination.page_size
    )


@router.get("/api-keys", response_model=Page[AdminApiKeyRead])
def list_api_keys(
    _: AdminUserDep, service: AdminServiceDep, pagination: PaginationDep
) -> Page[AdminApiKeyRead]:
    return service.list_api_keys(page=pagination.page, page_size=pagination.page_size)


@router.get("/search-logs", response_model=Page[AdminSearchLogRead])
def list_search_logs(
    _: AdminUserDep,
    service: AdminServiceDep,
    pagination: PaginationDep,
    q: Annotated[str | None, Query(max_length=20)] = None,
) -> Page[AdminSearchLogRead]:
    return service.list_search_logs(
        page=pagination.page, page_size=pagination.page_size, query=q
    )


@router.get("/settings", response_model=SystemSettings)
def system_settings(_: AdminUserDep, service: AdminServiceDep) -> SystemSettings:
    """Runtime configuration, read-only.

    Settings are environment-driven so they stay reproducible across
    deploys; changing one means changing the environment, not the database.
    """
    return service.system_settings()


@router.get("/whatsapp/accounts")
def list_whatsapp_accounts(_: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """List all WhatsApp accounts, reporting the status lookups actually use.

    The stored status is only ever as fresh as the last event this process
    saw, so after a restart it still claims "connected" for a session that has
    not reconnected. Since `/check` picks accounts by their live in-memory
    status, believing the stored one makes the panel show a healthy pool while
    every lookup fails with `no_accounts` — so the live status wins here, and
    `stored_status` is kept alongside for when the two disagree.
    """
    from app.services.providers.direct import DirectWhatsAppProvider
    from app.services.providers.registry import get_provider

    accounts = db.query(WhatsAppAccount).order_by(
        WhatsAppAccount.created_at.desc()).all()

    provider = get_provider()
    live: dict[str, str] = {}
    if isinstance(provider, DirectWhatsAppProvider):
        live = {
            status["id"]: status["status"]
            for status in provider.get_all_statuses()
        }

    result = []
    for acc in accounts:
        # No client at all means the pool never loaded this account — a real
        # state, and not the same as one that loaded and failed to connect.
        live_status = live.get(str(acc.id), "not_loaded")
        result.append({
            "id": str(acc.id),
            "phone_number": acc.phone_number,
            "status": live_status,
            "stored_status": acc.status,
            "is_default": acc.is_default,
            "total_lookups_performed": acc.total_lookups_performed,
            "lookups_this_month": acc.lookups_this_month,
            "created_at": acc.created_at.isoformat()
        })
    return {
        "accounts": result,
        # What /check will do right now, so the panel can say so plainly.
        "usable_accounts": sum(1 for s in live.values() if s == "connected"),
    }


@router.post("/whatsapp/accounts", status_code=201)
def create_whatsapp_account(_: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """Create a new WhatsApp account session."""
    from app.services.providers.direct import DirectWhatsAppProvider
    from app.services.providers.registry import get_provider

    account = WhatsAppAccount(status="initializing")
    db.add(account)
    db.commit()

    provider = get_provider()
    if isinstance(provider, DirectWhatsAppProvider):
        provider.add_account(account.id)

    return {
        "id": str(account.id),
        "status": account.status,
        "message": "Session initialized. Start polling for QR code."
    }


@router.get("/whatsapp/accounts/{account_id}/status")
def whatsapp_account_status(account_id: uuid.UUID, _: AdminUserDep) -> dict:
    """Get the current connection status and QR code of a specific WhatsApp account."""
    from app.services.providers.direct import DirectWhatsAppProvider
    from app.services.providers.registry import get_provider

    provider = get_provider()
    if isinstance(provider, DirectWhatsAppProvider):
        status = provider.get_account_status(account_id)
        if status:
            return status
    return {"id": str(account_id), "status": "not_found", "qr_data": None, "paired_number": None}


@router.post("/whatsapp/accounts/{account_id}/reverify")
def reverify_whatsapp_account(account_id: uuid.UUID, _: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """Force a reconnection/new QR code for an account."""
    from app.services.providers.direct import DirectWhatsAppProvider
    from app.services.providers.registry import get_provider

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.id == account_id).first()
    if not account:
        return {"error": "Account not found"}

    account.status = "initializing"
    account.phone_number = None
    db.commit()

    provider = get_provider()
    if isinstance(provider, DirectWhatsAppProvider):
        provider.reverify_account(account_id)

    return {
        "id": str(account_id),
        "status": "pairing",
        "message": "Session reset. Please poll status for new QR code."
    }


@router.delete("/whatsapp/accounts/{account_id}")
def delete_whatsapp_account(account_id: uuid.UUID, _: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """Remove a WhatsApp account."""
    from app.services.providers.direct import DirectWhatsAppProvider
    from app.services.providers.registry import get_provider

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.id == account_id).first()
    if account:
        db.delete(account)
        db.commit()

    provider = get_provider()
    if isinstance(provider, DirectWhatsAppProvider):
        provider.remove_account(account_id)

    return {"success": True, "message": "WhatsApp account successfully removed."}


@router.patch("/whatsapp/accounts/{account_id}/default")
def set_default_whatsapp_account(account_id: uuid.UUID, _: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """Set an account as the default fallback account."""
    db.query(WhatsAppAccount).update({"is_default": False})

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.id == account_id).first()
    if not account:
        return {"error": "Account not found"}

    account.is_default = True
    db.commit()

    return {"success": True, "message": "Default account updated."}


@router.get("/plans", response_model=list[PlanRead])
def list_all_plans(_: AdminUserDep, db: Session = Depends(get_session)) -> list[PlanRead]:
    """List all plans, including hidden ones, for admin management."""
    # repo = PlanRepository(db)
    # Get all ordered by sort_order
    plans = db.query(Plan).order_by(Plan.sort_order.asc()).all()
    return [PlanRead.model_validate(p) for p in plans]


@router.post("/plans", response_model=PlanRead, status_code=201)
def create_plan(payload: AdminPlanCreate, _: AdminUserDep, db: Session = Depends(get_session)) -> PlanRead:
    """Create a new pricing plan."""
    repo = PlanRepository(db)
    if repo.get_by_slug(payload.slug):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400, detail="Plan with this slug already exists.")
    plan = repo.create(**payload.model_dump())
    return PlanRead.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanRead)
def update_plan(plan_id: uuid.UUID, payload: AdminPlanUpdate, _: AdminUserDep, db: Session = Depends(get_session)) -> PlanRead:
    """Update an existing pricing plan."""
    repo = PlanRepository(db)
    plan = repo.get(plan_id)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Plan not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        repo.update(plan, **update_data)
    return PlanRead.model_validate(plan)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: uuid.UUID, _: AdminUserDep, db: Session = Depends(get_session)) -> dict:
    """Delete a plan. Note: May fail if users are subscribed to it."""
    repo = PlanRepository(db)
    plan = repo.get(plan_id)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        repo.delete(plan)
        return {"success": True}
    except Exception as err:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Cannot delete plan. There may be active wallets tied to it."
        ) from err
