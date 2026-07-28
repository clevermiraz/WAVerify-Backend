"""Test fixtures.

The suite runs against a real PostgreSQL database because the schema relies
on Postgres-specific features (JSONB, UUID, `ON CONFLICT` upserts) that a
SQLite stand-in would not exercise faithfully.

Point `TEST_DATABASE_URL` at a scratch database; the whole schema is created
and dropped around the session.
"""

import contextlib
import os
import uuid
from collections.abc import Iterator

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-000000")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://waverify:waverify@localhost:5432/waverify_test",
    ),
)
os.environ.setdefault("REDIS_URL", os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"))
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("VERIFICATION_CACHE_TTL_SECONDS", "0")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.init_db import seed_plans  # noqa: E402
from app.db.redis import get_redis  # noqa: E402
from app.db.session import SessionLocal, engine, get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.providers.base import ProviderResult  # noqa: E402
from app.services.providers.direct import DirectWhatsAppProvider  # noqa: E402


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_init(self, *args, **kwargs):
        pass

    def fake_check(self, phone):
        return ProviderResult(exists=True, display_name="Test User", is_business=False, about=None, profile_photo_url=None)

    monkeypatch.setattr(DirectWhatsAppProvider, "__init__", fake_init)
    monkeypatch.setattr(DirectWhatsAppProvider, "check", fake_check)
    monkeypatch.setattr(DirectWhatsAppProvider, "close", lambda self: None)



@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    try:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def session() -> Iterator[Session]:
    db = SessionLocal()
    seed_plans(db)
    db.commit()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(autouse=True)
def _clean_tables(_schema: None) -> Iterator[None]:
    """Truncate mutable tables between tests so cases stay independent."""
    yield
    with SessionLocal() as db:
        from sqlalchemy import text

        db.execute(
            text(
                "TRUNCATE users, api_keys, search_logs, usage_statistics, "
                "wallets, payments RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
    # Redis is optional for most tests.
    with contextlib.suppress(Exception):  # pragma: no cover
        get_redis().flushdb()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app = create_app()

    def _override() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def registered(client: TestClient) -> dict:
    """A registered user plus their access token."""
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "email": email,
        "password": "secret123",
        "user": body["user"],
        "token": body["tokens"]["access_token"],
        "refresh": body["tokens"]["refresh_token"],
        "headers": {"Authorization": f"Bearer {body['tokens']['access_token']}"},
    }
