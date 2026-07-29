"""Application configuration loaded from the environment."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import make_url


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

    # --- Google sign-in ---------------------------------------------------
    # The OAuth *client ID* only. The client secret is deliberately absent:
    # the frontend obtains an ID token via Google Identity Services and we
    # verify its signature and `aud` claim, which needs no secret.
    # Unset disables the /auth/google endpoint.
    GOOGLE_CLIENT_ID: str | None = None

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

    # --- Provider pacing (anti-ban jitter) -------------------------------
    # Random delays inserted before each WhatsApp call so pooled-account
    # traffic does not look robotic. Lower = faster responses but higher ban
    # risk. All values are seconds; set a pair equal for a fixed delay, or the
    # max to 0 to disable that delay entirely.
    PROVIDER_LOOKUP_DELAY_MIN: float = 0.2
    PROVIDER_LOOKUP_DELAY_MAX: float = 0.7
    PROVIDER_ENRICH_DELAY_MIN: float = 0.05
    PROVIDER_ENRICH_DELAY_MAX: float = 0.25
    # Fetch about/photo/devices for accounts that exist. Off makes lookups much
    # faster but returns only existence plus any business name.
    PROVIDER_ENRICH_PROFILE: bool = True

    # --- Gravatar enrichment ---------------------------------------------
    # When a caller passes an email alongside the number, we look it up on
    # Gravatar's public profile API to add a name, avatar, bio and any social
    # accounts the person has verified. The API works unauthenticated (100
    # req/hour); a key raises that to 1000/hour but is never required.
    GRAVATAR_ENABLED: bool = True
    GRAVATAR_API_KEY: str = ""
    GRAVATAR_TIMEOUT_SECONDS: float = 4.0
    # Profiles change rarely, so results are cached longer than a WhatsApp
    # lookup. 0 disables the cache.
    GRAVATAR_CACHE_TTL_SECONDS: int = 3600

    # --- Rate limiting ---------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_ENABLED: bool = True

    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@waverify.app"

    # --- Billing (Polar) --------------------------------------------------
    # Organization Access Token. Sandbox and production tokens are not
    # interchangeable, so POLAR_SERVER has to agree with whichever one is set.
    POLAR_ACCESS_TOKEN: str = ""
    # Signing secret of the webhook endpoint, copied from the Polar dashboard.
    # Distinct from the access token, and also per-environment.
    POLAR_WEBHOOK_SECRET: str = ""
    POLAR_SERVER: Literal["sandbox", "production"] = "sandbox"
    # Where Polar sends the buyer after paying. `{CHECKOUT_ID}` is substituted
    # by Polar itself, so it must survive into the URL literally.
    POLAR_SUCCESS_URL: str = "http://localhost:3000/dashboard/billing?checkout_id={CHECKOUT_ID}"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept both a comma-separated string and a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Accept plain-Postgres and pooler URLs, target the psycopg 3 driver.

        Supabase and similar hosts hand out `postgresql://…?pgbouncer=true`. A
        bare `postgresql://` leaves SQLAlchemy to guess a DBAPI, and `pgbouncer`
        is not a libpq option so psycopg rejects it up front. This rewrites both
        to the driver we install, while leaving any explicit `+driver`
        (`+psycopg`, `+asyncpg`, …) untouched.
        """
        try:
            url = make_url(value)
        except Exception:
            # Not a shape we recognise — let the engine raise the real error.
            return value
        if url.drivername in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
        if "pgbouncer" in url.query:
            url = url.set(
                query={k: v for k, v in url.query.items() if k != "pgbouncer"}
            )
        return url.render_as_string(hide_password=False)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def google_login_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID)

    @property
    def polar_enabled(self) -> bool:
        """Both halves are required: the token creates checkouts, the secret
        authenticates the callback that actually grants the credits."""
        return bool(self.POLAR_ACCESS_TOKEN and self.POLAR_WEBHOOK_SECRET)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so the environment is parsed exactly once."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
