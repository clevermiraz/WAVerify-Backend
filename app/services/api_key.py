"""API key lifecycle: create, rename, revoke, authenticate."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import ApiKey
from app.repositories.api_key import ApiKeyRepository

logger = get_logger(__name__)

MAX_KEYS_PER_USER = 10


class ApiKeyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ApiKeyRepository(session)

    def list_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        return self.repo.list_for_user(user_id)

    def create(self, user_id: uuid.UUID, name: str) -> tuple[ApiKey, str]:
        """Return the persisted key and its plaintext, shown only once."""
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Give the key a name.")
        if self.repo.count_active_for_user(user_id) >= MAX_KEYS_PER_USER:
            raise ValidationError(
                f"You can have at most {MAX_KEYS_PER_USER} active API keys. "
                "Delete one to create another."
            )
        if self.repo.name_taken(user_id, clean_name):
            raise ConflictError("You already have a key with this name.")

        plaintext, hashed, prefix = generate_api_key()
        api_key = self.repo.create(
            user_id=user_id,
            name=clean_name,
            hashed_key=hashed,
            prefix=prefix,
        )
        logger.info("api_key.created", user_id=str(user_id), key_id=str(api_key.id))
        return api_key, plaintext

    def rename(self, user_id: uuid.UUID, key_id: uuid.UUID, name: str) -> ApiKey:
        api_key = self._get_owned(user_id, key_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Give the key a name.")
        if self.repo.name_taken(user_id, clean_name, exclude_id=key_id):
            raise ConflictError("You already have a key with this name.")
        return self.repo.update(api_key, name=clean_name)

    def delete(self, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
        api_key = self._get_owned(user_id, key_id)
        self.repo.delete(api_key)
        logger.info("api_key.deleted", user_id=str(user_id), key_id=str(key_id))

    def authenticate(self, plaintext: str) -> ApiKey | None:
        api_key = self.repo.get_by_hash(hash_api_key(plaintext))
        if api_key is None:
            return None
        self.touch(api_key)
        return api_key

    def touch(self, api_key: ApiKey) -> None:
        now = datetime.now(UTC)
        # Coarse write: skip if it was already touched within the minute, so a
        # busy key does not generate an UPDATE on every single request.
        if api_key.last_used_at and (now - api_key.last_used_at).total_seconds() < 60:
            return
        self.repo.update(api_key, last_used_at=now)

    def _get_owned(self, user_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey:
        api_key = self.repo.get_for_user(key_id, user_id)
        if api_key is None:
            raise NotFoundError("API key not found.")
        return api_key
