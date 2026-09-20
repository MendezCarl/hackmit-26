"""Typed application errors and the repository-standard error envelope."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.contracts.models import ErrorBody, ErrorResponse


class ErrorCode(str, Enum):
    """Stable machine-readable error codes used by every endpoint."""

    VALIDATION_FAILED = "validation_failed"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    DUPLICATE = "duplicate"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_REFUSED = "provider_refused"
    PROVIDER_MALFORMED_OUTPUT = "provider_malformed_output"
    DEMO_UNAVAILABLE = "demo_unavailable"
    INTERNAL_ERROR = "internal_error"


STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.DUPLICATE: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.PROVIDER_FAILURE: 502,
    ErrorCode.PROVIDER_TIMEOUT: 502,
    ErrorCode.PROVIDER_REFUSED: 502,
    ErrorCode.PROVIDER_MALFORMED_OUTPUT: 502,
    ErrorCode.DEMO_UNAVAILABLE: 404,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    """Typed error carrying a stable code, HTTP status, and message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        """Create a typed application error.

        Args:
            code: Stable machine-readable error code.
            message: Human-readable explanation safe to return to clients.
            details: Optional structured details (never include secrets).
            status_code: Optional HTTP override; defaults to the code mapping.
        """

        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code or STATUS_BY_CODE[code]
        super().__init__(message)


def build_error_payload(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize an error into the repository-standard envelope.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable explanation.
        details: Optional structured details.

    Returns:
        A JSON-serializable ``{"error": {...}}`` envelope.
    """

    body = ErrorBody(code=code.value, message=message, details=details)
    return ErrorResponse(error=body).model_dump()


def install_error_handlers(app: FastAPI) -> None:
    """Register exception handlers that emit the standard error envelope.

    Args:
        app: FastAPI application receiving the handlers.
    """

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """Convert typed application errors into the standard envelope."""

        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert request-validation failures into the standard envelope."""

        sanitized_errors = [
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": error.get("msg"),
                "type": error.get("type"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=build_error_payload(
                ErrorCode.VALIDATION_FAILED,
                "Request payload failed validation.",
                {"errors": sanitized_errors},
            ),
        )
