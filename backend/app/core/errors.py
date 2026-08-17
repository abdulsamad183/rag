"""Application error hierarchy and FastAPI exception handlers.

Errors carry a machine-readable ``code`` and a safe user-facing message.
Raw stack traces and secrets are never sent to clients.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("errors")


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "Internal error", *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderError(AppError):
    """Upstream LLM/embedding provider failure."""

    status_code = 502
    code = "provider_error"


class ProviderNotConfiguredError(AppError):
    status_code = 400
    code = "provider_not_configured"


class ProviderAuthError(AppError):
    status_code = 401
    code = "provider_auth_failed"


class ModelNotAvailableError(AppError):
    status_code = 400
    code = "model_not_available"


class CapabilityError(AppError):
    status_code = 400
    code = "capability_not_supported"


class IngestionError(AppError):
    status_code = 422
    code = "ingestion_failed"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class EmbeddingMismatchError(AppError):
    status_code = 409
    code = "embedding_mismatch"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            code=exc.code,
            path=request.url.path,
            message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
        )
