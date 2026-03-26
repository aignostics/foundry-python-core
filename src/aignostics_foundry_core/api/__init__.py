"""API sub-package for aignostics_foundry_core.

Sub-modules:
- exceptions: ApiException hierarchy and FastAPI exception handlers
"""

from .exceptions import (
    AccessDeniedException,
    ApiException,
    NotFoundException,
    api_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

__all__ = [
    "AccessDeniedException",
    "ApiException",
    "NotFoundException",
    "api_exception_handler",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
