"""API sub-package for aignostics_foundry_core.

Sub-modules:
- exceptions: ApiException hierarchy and FastAPI exception handlers
- auth: Auth0 authentication and authorisation FastAPI dependencies
- core: VersionedAPIRouter, router factories, and init_api
"""

from .auth import (
    AUTH0_COOKIE_SCHEME_DESCRIPTION,
    AUTH0_COOKIE_SCHEME_NAME,
    AUTH0_ROLE_ADMIN,
    AUTH0_SESSION_COOKIE_NAME,
    AUTH0_TRANSACTION_COOKIE_NAME,
    DEFAULT_AUTH0_ROLE_CLAIM,
    AuthSettings,
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
from .core import (
    API_TAG_ADMIN,
    API_TAG_AUTHENTICATED,
    API_TAG_INTERNAL,
    API_TAG_INTERNAL_ADMIN,
    API_TAG_PUBLIC,
    VersionedAPIRouter,
    build_api_metadata,
    build_root_api_tags,
    build_versioned_api_tags,
    create_admin_router,
    create_authenticated_router,
    create_internal_admin_router,
    create_internal_router,
    create_public_router,
    get_versioned_api_instances,
    init_api,
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
    # core
    "API_TAG_ADMIN",
    "API_TAG_AUTHENTICATED",
    "API_TAG_INTERNAL",
    "API_TAG_INTERNAL_ADMIN",
    "API_TAG_PUBLIC",
    # auth
    "AUTH0_COOKIE_SCHEME_DESCRIPTION",
    "AUTH0_COOKIE_SCHEME_NAME",
    "AUTH0_ROLE_ADMIN",
    "AUTH0_SESSION_COOKIE_NAME",
    "AUTH0_TRANSACTION_COOKIE_NAME",
    "DEFAULT_AUTH0_ROLE_CLAIM",
    # exceptions
    "AccessDeniedException",
    "ApiException",
    "AuthSettings",
    "ForbiddenError",
    "NotFoundException",
    "UnauthenticatedError",
    "VersionedAPIRouter",
    "api_exception_handler",
    "auth0_admin_scheme",
    "auth0_internal_admin_scheme",
    "auth0_internal_scheme",
    "auth0_session_scheme",
    "build_api_metadata",
    "build_root_api_tags",
    "build_versioned_api_tags",
    "create_admin_router",
    "create_authenticated_router",
    "create_internal_admin_router",
    "create_internal_router",
    "create_public_router",
    "get_auth_client",
    "get_user",
    "get_versioned_api_instances",
    "init_api",
    "require_admin",
    "require_authenticated",
    "require_internal",
    "require_internal_admin",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
