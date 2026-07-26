from fastapi import APIRouter, status

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import UserServiceDep
from app.schemas.user import DeleteAccountRequest, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
def get_profile(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
def update_profile(
    payload: UserUpdate, user: CurrentUserDep, service: UserServiceDep
) -> UserRead:
    return UserRead.model_validate(
        service.update_profile(user, full_name=payload.full_name, company=payload.company)
    )


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest, user: CurrentUserDep, service: UserServiceDep
) -> None:
    """Permanently delete the account and everything attached to it.

    A POST with the current password rather than a bare DELETE, so the
    destructive action cannot be triggered by a stray link.
    """
    service.delete_account(user, password=payload.password)
