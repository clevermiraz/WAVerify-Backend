"""Application configuration loaded from the environment."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------
    PROJECT_NAME: str = "WAVerify"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # --- Security --------------------------------------------------------
    SECRET_KEY: str = Field(min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    # When false, unverified users may still perform lookups. Left off in
    # development so the console-email flow is not a hard blocker; turn on
    # in production.
    REQUIRE_EMAIL_VERIFICATION: bool = False
    PASSWORD_RESET_EXPIRE_HOURS: int = 2
    ALGORITHM: str = "HS256"

    # --- Datastores ------------------------------------------------------
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    REDIS_URL: str = "redis://redis:6379/0"

    # --- CORS ------------------------------------------------------------
    # `NoDecode` stops pydantic-settings from JSON-parsing the raw env value,
    # which would reject the comma-separated form used in .env and compose.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- Frontend links used inside transactional emails ------------------
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Verification provider -------------------------------------------
    VERIFICATION_CACHE_TTL_SECONDS: int = 300

    # --- Rate limiting ---------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_ENABLED: bool = True

    # --- Email -----------------------------------------------------------
    # `console` writes the message to the structured log, which is all the
    # MVP needs. A real SMTP/provider backend can be added alongside it.
    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    EMAIL_FROM: str = "no-reply@waverify.dev"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    # --- Bootstrap admin --------------------------------------------------
    FIRST_ADMIN_EMAIL: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept both a comma-separated string and a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so the environment is parsed exactly once."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
