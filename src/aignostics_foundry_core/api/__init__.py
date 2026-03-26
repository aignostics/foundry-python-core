"""API sub-package for aignostics_foundry_core.

Sub-modules:
- exceptions: ApiException hierarchy and FastAPI exception handlers
"""

from .auth import (
    AUTH0_COOKIE_SCHEME_DESCRIPTION,
    AUTH0_COOKIE_SCHEME_NAME,
    AUTH0_ROLE_ADMIN,
    AUTH0_SESSION_COOKIE_NAME,
    AUTH0_TRANSACTION_COOKIE_NAME,
    ForbiddenError,
    UnauthenticatedError,
    auth0_admin_scheme,
    auth0_internal_admin_scheme,
    auth0_internal_scheme,
    auth0_session_scheme,
    get_auth_client,
    get_user,
    require_admin,
    require_authenticated,
    require_internal,
    require_internal_admin,
)
from .exceptions import (
    AccessDeniedException,
    ApiException,
    NotFoundException,
    api_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

__all__ = [
    "AUTH0_COOKIE_SCHEME_DESCRIPTION",
    "AUTH0_COOKIE_SCHEME_NAME",
    "AUTH0_ROLE_ADMIN",
    "AUTH0_SESSION_COOKIE_NAME",
    "AUTH0_TRANSACTION_COOKIE_NAME",
    "AccessDeniedException",
    "ApiException",
    "ForbiddenError",
    "NotFoundException",
    "UnauthenticatedError",
    "api_exception_handler",
    "auth0_admin_scheme",
    "auth0_internal_admin_scheme",
    "auth0_internal_scheme",
    "auth0_session_scheme",
    "get_auth_client",
    "get_user",
    "require_admin",
    "require_authenticated",
    "require_internal",
    "require_internal_admin",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
