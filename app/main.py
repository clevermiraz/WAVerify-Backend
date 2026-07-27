"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.common import ErrorDetail, ErrorResponse
from app.services.providers.registry import get_provider, shutdown_provider

logger = get_logger(__name__)

DESCRIPTION = """
Send a phone number. Find out if it has a WhatsApp account.

## Base URL

```
https://api.waverify.app
```

Always use `https`. Plain `http` does not work.

## Your API key

Send your key in a header called `X-API-Key`:

```
X-API-Key: wav_live_xxxxxxxxxxxxxxxxxxxx
```

You see the full key only once, when you create it in the dashboard. We do not
keep a copy, so we cannot show it to you again. Save it somewhere safe.

Keep the key in an environment variable. Do not write it in your code, and do
not upload it to GitHub. If someone else gets your key, delete it in the
dashboard and make a new one.

If you are signed in to the dashboard, your session uses a short-lived Bearer
token instead. Both work on the same endpoints.

## Errors

Every error looks the same:

```json
{ "success": false, "error": { "code": "quota_exceeded", "message": "…", "details": {} } }
```

In your code, check `error.code`. Do not check the message text — the wording
can change, but the code will not.

## Limits

There are two separate limits.

1. **Requests per minute.** If you go over, you get `429` with the code
   `rate_limit_exceeded`. Wait a short time, then try again.
2. **Requests per month.** When you use them all, you get `402` with the code
   `quota_exceeded`. You can upgrade your plan at any time.

Checking the same number twice in a short time returns a saved result, marked
`cached: true`. It is faster, but it still counts towards your monthly total.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    provider = get_provider()
    logger.info(
        "app.startup",
        environment=settings.ENVIRONMENT,
        provider=provider.name,
    )
    yield
    shutdown_provider()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    # The schema documents every route, including the whole admin API, so the
    # interactive docs are switched off in production rather than advertising
    # that surface. `openapi_url` goes too — leaving it on would keep the
    # machine-readable version of exactly the same information public.
    docs_enabled = not settings.is_production

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=DESCRIPTION,
        version="1.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    _register_error_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    # Unprefixed alias so container orchestrators can probe a stable path.
    app.add_api_route("/health", _liveness, methods=["GET"], include_in_schema=False)
    return app


async def _liveness() -> dict[str, str]:
    return {"status": "ok"}


def _error_response(
    status_code: int, code: str, message: str, details: dict | None = None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or {})
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Collapse Pydantic's list into `{field: message}`, which is what the
        # frontend forms consume.
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part not in ("body", "query")]
            fields[".".join(location) or "body"] = error["msg"]
        return _error_response(
            422,
            "validation_error",
            "Please correct the highlighted fields.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(
            exc.status_code,
            _HTTP_CODES.get(exc.status_code, "http_error"),
            str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("app.unhandled_exception", error=str(exc))
        # Never leak internals to the client.
        return _error_response(
            500, "internal_error", "Something went wrong on our end."
        )


_HTTP_CODES = {
    401: "authentication_failed",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    429: "rate_limit_exceeded",
}

app = create_app()
