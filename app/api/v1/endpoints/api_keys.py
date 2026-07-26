import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import CurrentUserDep
from app.dependencies.services import ApiKeyServiceDep
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, ApiKeyUpdate

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get("", response_model=list[ApiKeyRead])
def list_keys(user: CurrentUserDep, service: ApiKeyServiceDep) -> list[ApiKeyRead]:
    return [ApiKeyRead.model_validate(key) for key in service.list_for_user(user.id)]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: ApiKeyCreate, user: CurrentUserDep, service: ApiKeyServiceDep
) -> ApiKeyCreated:
    """Create a key. The plaintext is returned here and never again."""
    api_key, plaintext = service.create(user.id, payload.name)
    return ApiKeyCreated(
        **ApiKeyRead.model_validate(api_key).model_dump(), key=plaintext
    )


@router.patch("/{key_id}", response_model=ApiKeyRead)
def rename_key(
    key_id: uuid.UUID,
    payload: ApiKeyUpdate,
    user: CurrentUserDep,
    service: ApiKeyServiceDep,
) -> ApiKeyRead:
    return ApiKeyRead.model_validate(service.rename(user.id, key_id, payload.name))


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(
    key_id: uuid.UUID, user: CurrentUserDep, service: ApiKeyServiceDep
) -> None:
    service.delete(user.id, key_id)
