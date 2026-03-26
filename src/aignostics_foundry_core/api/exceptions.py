"""API exception classes and handlers.

This module provides:
- ApiException: Base exception for API errors
- NotFoundException: 404 Not Found exception
- AccessDeniedException: 401 Unauthorized exception
- Exception handlers for FastAPI
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import JSONResponse


@runtime_checkable
class _HasErrors(Protocol):
    """Protocol for exceptions that expose a structured errors() method."""

    def errors(self) -> list[dict[str, Any]]: ...


class ApiException(Exception):  # noqa: N818
    """Base exception for API errors."""

    status_code = 500
    message = "Unhandled API exception"

    def __init__(self, message: str | None = None, status_code: int | None = None) -> None:
        """Initialize API exception.

        Args:
            message: Optional error message override.
            status_code: Optional status code override.
        """
        if message is not None:
            self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(ApiException):
    """Exception for 404 Not Found errors."""

    status_code = 404
    message = "Not found"


class AccessDeniedException(ApiException):
    """Exception for 401 Unauthorized errors.

    Note: HTTP 401 indicates that a request lacks valid authentication credentials.
    In the HTTP specification, it should have been called "Unauthenticated" to avoid confusion.
    For "Access denied" where the user is authenticated but lacks permission, use HTTP 403 Forbidden.
    See: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
    """

    status_code = 401
    message = "Access denied"


def api_exception_handler(_: "Request", exc: ApiException) -> "JSONResponse":
    """Handle ApiException by returning a standardized JSON error response.

    Args:
        _: The FastAPI request object (unused).
        exc: The ApiException to handle.

    Returns:
        JSONResponse with error details.
    """
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.message,
            },
        },
    )


def unhandled_exception_handler(_: "Request", exc: Exception) -> "JSONResponse":
    """Handle unhandled exceptions by logging and returning a generic error.

    Args:
        _: The FastAPI request object (unused).
        exc: The unhandled exception.

    Returns:
        JSONResponse with generic server error.
    """
    from fastapi.responses import JSONResponse  # noqa: PLC0415
    from loguru import logger  # noqa: PLC0415

    logger.critical(f"Unhandled api exception {exc!r}", extra={"exception": f"{exc!r}"})
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": 500, "message": "Server Error"},
        },
    )


def validation_exception_handler(_: "Request", exc: Exception) -> "JSONResponse":
    """Handle validation exceptions by returning detailed error information.

    Args:
        _: The FastAPI request object (unused).
        exc: The validation exception (Pydantic ValidationError or FastAPI RequestValidationError).

    Returns:
        JSONResponse with validation error details.
    """
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    # Both ValidationError and RequestValidationError have errors() method
    if isinstance(exc, _HasErrors):
        errors: object = exc.errors()
    else:
        errors = str(exc)
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": 422,
                "message": f"Validation error: {errors}",
            },
        },
    )
