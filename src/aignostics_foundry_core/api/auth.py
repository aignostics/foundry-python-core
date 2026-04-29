"""Authentication utilities for FastAPI.

This module provides:
- Auth0 cookie schemes for OpenAPI documentation
- Authentication dependencies (require_authenticated, require_admin, etc.)
- get_user: Get authenticated user from session
- get_auth_client: Get Auth0 client from app state
- AuthSettings: Full auth configuration (enabled, session, domain, credentials, org, role claim)
"""

import time
from typing import Annotated, Any

from auth0_fastapi.auth.auth_client import AuthClient
from fastapi import Request, Security
from fastapi.security import APIKeyCookie
from loguru import logger
from pydantic import Field, PlainSerializer, SecretStr, StringConstraints, model_validator
from pydantic_settings import SettingsConfigDict

from aignostics_foundry_core.foundry import get_context
from aignostics_foundry_core.settings import OpaqueSettings, load_settings

from .exceptions import ApiException

AUTH0_SESSION_COOKIE_NAME = "_a0_session"
AUTH0_TRANSACTION_COOKIE_NAME = "_a0_tx"
AUTH0_COOKIE_SCHEME_NAME = "Auth0Cookie"
AUTH0_COOKIE_SCHEME_DESCRIPTION = "Auth0 session cookie authentication scheme."
AUTH0_ROLE_ADMIN = "admin"
USER_NOT_AUTHENTICATED = "User is not authenticated"
AUTH_SESSION_EXPIRATION_DEFAULT = 60 * 60 * 24  # 1 day in seconds


class AuthSettings(OpaqueSettings):
    """Auth settings whose env prefix and env files are derived from the active FoundryContext.

    The effective prefix is ``{FoundryContext.env_prefix}AUTH_`` and the env files are
    ``FoundryContext.env_file``, both resolved at instantiation time via
    :func:`aignostics_foundry_core.foundry.get_context`.

    Fields:
        enabled: Enable Auth0 authentication (AUTH_ENABLED).
        session_enabled: Enable session cookies (AUTH_SESSION_ENABLED).
        session_secret: Secret used to sign session cookies (AUTH_SESSION_SECRET).
        session_expiration: Session cookie expiration in seconds (AUTH_SESSION_EXPIRATION).
        domain: Auth0 domain (AUTH_DOMAIN).
        client_id: Auth0 client ID (AUTH_CLIENT_ID).
        client_secret: Auth0 client secret (AUTH_CLIENT_SECRET).
        internal_org_id: Auth0 org ID for the internal organisation (AUTH_INTERNAL_ORG_ID).
        role_claim: JWT claim name containing the user's role (AUTH_ROLE_CLAIM).

    Cross-field rules (validated after field assignment):
        - enabled=True requires session_enabled=True
        - session_enabled=True requires session_secret not None
        - enabled=True requires client_secret not None, non-empty domain, client_id,
          internal_org_id, and role_claim
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = Field(default=False)
    session_enabled: bool = Field(default=False)
    session_secret: Annotated[
        SecretStr | None,
        PlainSerializer(func=OpaqueSettings.serialize_sensitive_info, return_type=str, when_used="always"),
    ] = Field(default=None)
    session_expiration: int = Field(default=AUTH_SESSION_EXPIRATION_DEFAULT, gt=60, le=31536000)
    domain: Annotated[str, StringConstraints(max_length=255)] = Field(default="")
    client_id: Annotated[str, StringConstraints(max_length=32)] = Field(default="")
    client_secret: Annotated[
        SecretStr | None,
        PlainSerializer(func=OpaqueSettings.serialize_sensitive_info, return_type=str, when_used="always"),
    ] = Field(default=None, min_length=64, max_length=64)
    internal_org_id: str = ""
    role_claim: str = ""

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialise settings, deriving env_prefix and env files from the active FoundryContext."""
        ctx = get_context()
        super().__init__(_env_prefix=f"{ctx.env_prefix}AUTH_", _env_file=ctx.env_file, **kwargs)  # pyright: ignore[reportCallIssue]

    @model_validator(mode="after")
    def validate_auth_dependencies(self) -> "AuthSettings":
        """Validate cross-field auth dependencies.

        Returns:
            AuthSettings: The validated settings instance.

        Raises:
            ValueError: If any cross-field dependency is violated.
        """
        if self.enabled and not self.session_enabled:
            msg = "AUTH_SESSION_ENABLED must be True when AUTH_ENABLED is True"
            raise ValueError(msg)
        if self.session_enabled and self.session_secret is None:
            msg = "AUTH_SESSION_SECRET must not be None when AUTH_SESSION_ENABLED is True"
            raise ValueError(msg)
        if self.enabled and self.client_secret is None:
            msg = "AUTH_CLIENT_SECRET must not be None when AUTH_ENABLED is True"
            raise ValueError(msg)
        if self.enabled and not self.domain:
            msg = "AUTH_DOMAIN must not be empty when AUTH_ENABLED is True"
            raise ValueError(msg)
        if self.enabled and not self.client_id:
            msg = "AUTH_CLIENT_ID must not be empty when AUTH_ENABLED is True"
            raise ValueError(msg)
        if self.enabled and not self.internal_org_id:
            msg = "AUTH_INTERNAL_ORG_ID must not be empty when AUTH_ENABLED is True"
            raise ValueError(msg)
        if self.enabled and not self.role_claim:
            msg = "AUTH_ROLE_CLAIM must not be empty when AUTH_ENABLED is True"
            raise ValueError(msg)
        return self


class UnauthenticatedError(Exception):
    """Raised when user is not authenticated."""


class ForbiddenError(ApiException):
    """Exception for 403 Forbidden errors.

    Used when user is authenticated but lacks required permissions/role.
    """

    status_code = 403
    message = "Forbidden"

    def __init__(self, message: str | None = None) -> None:
        """Initialize Forbidden error.

        Args:
            message: Optional error message override.
        """
        super().__init__(message=message, status_code=403)


def get_auth_client(request: Request) -> AuthClient:
    """Get auth_client from app state.

    Args:
        request: The incoming request.

    Returns:
        AuthClient: The Auth0 authentication client.

    Raises:
        RuntimeError: If Auth0 is not enabled or auth_client is not configured.
    """
    if not hasattr(request.app.state, "auth_client"):
        msg = "auth0 is not enabled."
        logger.error(msg)
        raise RuntimeError(msg)
    return request.app.state.auth_client


auth0_session_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name=AUTH0_COOKIE_SCHEME_NAME,
    description=AUTH0_COOKIE_SCHEME_DESCRIPTION,
    auto_error=False,
)  # Security scheme for OpenAPI documentation (shows lock icon in Swagger)

auth0_admin_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name="Auth0AdminCookie",
    description="Auth0 session cookie authentication with admin role requirement. "
    f"User must have '{AUTH0_ROLE_ADMIN}' role in their configured role_claim.",
    auto_error=False,
)  # Security scheme specifically for admin endpoints

auth0_internal_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name="Auth0InternalCookie",
    description="Auth0 session cookie authentication with internal organization membership requirement. "
    "User must be a member of the configured internal organization.",
    auto_error=False,
)  # Security scheme for internal endpoints

auth0_internal_admin_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name="Auth0InternalAdminCookie",
    description=(
        "Auth0 session cookie authentication with internal organization membership AND admin role requirements. "
        f"User must be a member of the internal organization AND have '{AUTH0_ROLE_ADMIN}' role."
    ),
    auto_error=False,
)  # Security scheme for internal admin endpoints


async def _require_authenticated_impl(
    request: Request,
    _cookie: str | None,
    role: str | None = None,
) -> None:
    """Internal implementation for authenticated session check with optional role.

    Args:
        request: The incoming request.
        _cookie: The session cookie.
        role: Optional role required (e.g., "admin"). If specified, user must have
            this role in their configured role_claim.

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
        ForbiddenError: If role is specified and user doesn't have the required role.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie)
    if not user:
        msg = USER_NOT_AUTHENTICATED
        logger.critical(msg)
        raise ForbiddenError(msg)

    # Check role if specified
    if role is not None:
        user_role = user.get(auth_settings.role_claim)
        if user_role != role:
            msg = f"User role '{user_role}' does not match required role '{role}'"
            logger.warning(msg)
            raise ForbiddenError(msg)
        logger.debug(f"User has required role: {role}")


async def require_authenticated(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_session_scheme)],
) -> None:
    """Require an authenticated session (FastAPI dependency).

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
    """
    await _require_authenticated_impl(request, _cookie)


async def require_admin(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_admin_scheme)],
) -> None:
    """Require admin role (FastAPI dependency).

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
        ForbiddenError: If user doesn't have admin role.
    """
    await _require_authenticated_impl(request, _cookie, role=AUTH0_ROLE_ADMIN)


async def require_internal(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_internal_scheme)],
) -> None:
    """Require internal organization membership (FastAPI dependency).

    Checks if the authenticated user is a member of the configured internal organization.
    The internal organization is identified by the FOUNDRY_AUTH_INTERNAL_ORG_ID setting.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
        ForbiddenError: If user is not a member of the internal organization.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie)
    if not user:
        msg = USER_NOT_AUTHENTICATED
        logger.critical(msg)
        raise ForbiddenError(msg)
    # Check organization membership
    user_org_id = user.get("org_id")
    if user_org_id != auth_settings.internal_org_id:
        msg = f"User is not a member of the internal organization (org_id: {user_org_id})"
        logger.warning(msg)
        raise ForbiddenError(msg)

    logger.debug(f"User is member of internal organization: {auth_settings.internal_org_id}")


async def require_internal_admin(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_internal_admin_scheme)],
) -> None:
    """Require internal organization membership AND admin role (FastAPI dependency).

    Checks if the authenticated user is both:
    1. A member of the configured internal organization (FOUNDRY_AUTH_INTERNAL_ORG_ID)
    2. Has the admin role in their configured role_claim

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
        ForbiddenError: If user is not internal or doesn't have admin role.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie)
    if not user:
        msg = USER_NOT_AUTHENTICATED
        logger.critical(msg)
        raise ForbiddenError(msg)

    # Check organization membership
    user_org_id = user.get("org_id")
    if user_org_id != auth_settings.internal_org_id:
        msg = f"User is not a member of the internal organization (org_id: {user_org_id})"
        logger.warning(msg)
        raise ForbiddenError(msg)

    # Check admin role
    user_role = user.get(auth_settings.role_claim)
    if user_role != AUTH0_ROLE_ADMIN:
        msg = f"User role '{user_role}' does not match required role '{AUTH0_ROLE_ADMIN}'"
        logger.warning(msg)
        raise ForbiddenError(msg)

    logger.debug(f"User is internal admin: org={auth_settings.internal_org_id}, role={AUTH0_ROLE_ADMIN}")


async def get_user(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_session_scheme)],
) -> dict[str, Any] | None:
    """Get authenticated user information (FastAPI dependency).

    This dependency ensures the user is authenticated and returns their user data
    from the Auth0 session. Internally reads from the encrypted session cookie.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).

    Returns:
        User dictionary from Auth0 session containing claims like 'sub', 'email', 'name', etc.
            or None if not authenticated.

    Example:
        @router.get("/me")
        async def me(user: Annotated[dict[str, Any], Depends(get_user)]):
            return {"email": user.get("email")}
    """
    from fastapi import Response  # noqa: PLC0415

    from aignostics_foundry_core.sentry import set_sentry_user  # noqa: PLC0415

    auth_settings = load_settings(AuthSettings)

    try:
        auth_client = get_auth_client(request)
        session: dict = await auth_client.require_session(request, Response())  # type: ignore[reportUnknownVariableType]
    except Exception:  # noqa: BLE001
        msg = "No session found"
        logger.debug(msg)
        return None

    raw_user: dict | None = session.get("user") if isinstance(session, dict) else None  # type: ignore[reportUnknownVariableType]
    if not raw_user or not isinstance(raw_user, dict):
        msg = "Failed to retrieve user information from session"
        logger.critical(msg)
        return None
    user: dict[str, Any] = raw_user  # pyright: ignore[reportUnknownVariableType]

    set_sentry_user(user, role_claim=auth_settings.role_claim)

    # Check if expired
    exp = user.get("exp")
    if not exp:
        msg = "User session is missing expiration claim"
        logger.critical(msg)
        return None

    if exp < int(time.time()):
        msg = "User session has expired"
        logger.debug(msg)
        return None

    return user
