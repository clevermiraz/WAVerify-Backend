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
Verify whether a phone number has a WhatsApp account.

## Authentication

Send your API key in the `X-API-Key` header:

```
X-API-Key: wav_live_xxxxxxxxxxxxxxxxxxxx
```

Dashboard sessions authenticate with a Bearer access token instead.

## Errors

Every non-2xx response uses the same envelope:

```json
{ "success": false, "error": { "code": "quota_exceeded", "message": "…", "details": {} } }
```
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
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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
