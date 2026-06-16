"""Authentication utilities for FastAPI.

This module provides:
- Auth0 cookie and Bearer JWT schemes for OpenAPI documentation
- Authentication dependencies (require_authenticated, require_admin, etc.)
- get_user: Get authenticated user from session cookie or Bearer JWT
- get_auth_client: Get Auth0 client from app state
- AuthSettings: Full auth configuration (cookie_enabled, jwt_enabled, session, domain,
  credentials, org, role claim, JWT audience)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

import httpx
import jwt
from fastapi import Request, Response, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm
from loguru import logger
from pydantic import Field, PlainSerializer, SecretStr, StringConstraints, model_validator
from pydantic_settings import SettingsConfigDict

from aignostics_foundry_core.foundry import get_context
from aignostics_foundry_core.sentry import set_sentry_user
from aignostics_foundry_core.settings import OpaqueSettings, load_settings

from .exceptions import ApiException

if TYPE_CHECKING:
    from auth0_fastapi.auth.auth_client import AuthClient
    from jwt.algorithms import AllowedRSAKeys

AUTH0_SESSION_COOKIE_NAME = "_a0_session"
AUTH0_TRANSACTION_COOKIE_NAME = "_a0_tx"
AUTH0_COOKIE_SCHEME_NAME = "Auth0Cookie"
AUTH0_COOKIE_SCHEME_DESCRIPTION = "Auth0 session cookie authentication scheme."
AUTH0_BEARER_SCHEME_NAME = "Auth0Bearer"
AUTH0_ROLE_ADMIN = "admin"
USER_NOT_AUTHENTICATED = "User is not authenticated"
AUTH_SESSION_EXPIRATION_DEFAULT = 60 * 60 * 24  # 1 day in seconds
AUTH0_JWKS_ALGORITHMS = ["RS256"]
AUTH0_JWKS_CACHE_TTL = 3600  # seconds


@dataclass(frozen=True)
class _JwksCacheEntry:
    jwks: dict[str, Any]
    fetched_at: float


_jwks_cache: dict[str, _JwksCacheEntry] = {}


class AuthSettings(OpaqueSettings):
    """Auth settings whose env prefix and env files are derived from the active FoundryContext.

    The effective prefix is ``{FoundryContext.env_prefix}AUTH_`` and the env files are
    ``FoundryContext.env_file``, both resolved at instantiation time via
    :func:`aignostics_foundry_core.foundry.get_context`.

    Fields:
        cookie_enabled: Enable Auth0 cookie-based authentication (AUTH_COOKIE_ENABLED).
        enabled: Deprecated alias for cookie_enabled. Use AUTH_COOKIE_ENABLED instead
            (AUTH_ENABLED still accepted for backwards compatibility).
        jwt_enabled: Enable JWT Bearer token authentication (AUTH_JWT_ENABLED).
        jwt_audience: Auth0 API audience identifier for JWT validation (AUTH_JWT_AUDIENCE).
        session_secret: Secret used to sign session cookies (AUTH_SESSION_SECRET).
        session_expiration: Session cookie expiration in seconds (AUTH_SESSION_EXPIRATION).
        domain: Auth0 domain (AUTH_DOMAIN).
        client_id: Auth0 client ID (AUTH_CLIENT_ID).
        client_secret: Auth0 client secret (AUTH_CLIENT_SECRET).
        internal_org_id: Auth0 org ID for the internal organisation (AUTH_INTERNAL_ORG_ID).
        role_claim: JWT claim name containing the user's role (AUTH_ROLE_CLAIM).

    Cross-field rules (validated after field assignment):
        - cookie_enabled=True (or enabled=True) requires session_secret, client_secret,
          non-empty domain, client_id, internal_org_id, and role_claim
        - jwt_enabled=True requires non-empty domain and jwt_audience
    """

    model_config = SettingsConfigDict(extra="ignore")

    cookie_enabled: bool = Field(default=False)
    enabled: bool = Field(default=False)  # deprecated; kept for AUTH_ENABLED backwards compat
    jwt_enabled: bool = Field(default=False)
    jwt_audience: str = Field(default="")
    session_secret: Annotated[
        SecretStr | None,
        PlainSerializer(func=OpaqueSettings.serialize_sensitive_info, return_type=str, when_used="always"),
    ] = Field(default=None)
    session_expiration: int = Field(default=AUTH_SESSION_EXPIRATION_DEFAULT, gt=60, le=31536000)
    domain: Annotated[str, StringConstraints(max_length=255, strip_whitespace=True)] = Field(default="")
    client_id: Annotated[str, StringConstraints(max_length=32, strip_whitespace=True)] = Field(default="")
    client_secret: Annotated[
        SecretStr | None,
        PlainSerializer(func=OpaqueSettings.serialize_sensitive_info, return_type=str, when_used="always"),
    ] = Field(default=None, min_length=64, max_length=64)
    internal_org_id: Annotated[str, StringConstraints(max_length=255, strip_whitespace=True)] = Field(default="")
    role_claim: Annotated[str, StringConstraints(max_length=255, strip_whitespace=True)] = Field(default="")

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialise settings, deriving env_prefix and env files from the active FoundryContext."""
        ctx = get_context()
        super().__init__(_env_prefix=f"{ctx.env_prefix}AUTH_", _env_file=ctx.env_file, **kwargs)  # pyright: ignore[reportCallIssue]

    def _validate_cookie_auth(self) -> None:
        """Validate cookie auth required fields when cookie auth is active.

        Raises:
            ValueError: If any required cookie auth field is missing or invalid.
        """
        cookie_active = self.cookie_enabled or self.enabled
        if not cookie_active:
            return
        if self.session_secret is None:
            msg = "AUTH_SESSION_SECRET must not be None when cookie auth is enabled"
            raise ValueError(msg)
        if self.client_secret is None:
            msg = "AUTH_CLIENT_SECRET must not be None when cookie auth is enabled"
            raise ValueError(msg)
        if not self.domain:
            msg = "AUTH_DOMAIN must not be empty when cookie auth is enabled"
            raise ValueError(msg)
        if not self.client_id:
            msg = "AUTH_CLIENT_ID must not be empty when cookie auth is enabled"
            raise ValueError(msg)
        if not self.internal_org_id:
            msg = "AUTH_INTERNAL_ORG_ID must not be empty when cookie auth is enabled"
            raise ValueError(msg)
        if not self.role_claim:
            msg = "AUTH_ROLE_CLAIM must not be empty when cookie auth is enabled"
            raise ValueError(msg)

    @model_validator(mode="after")
    def validate_auth_dependencies(self) -> AuthSettings:
        """Validate cross-field auth dependencies.

        Returns:
            AuthSettings: The validated settings instance.

        Raises:
            ValueError: If any cross-field dependency is violated.
        """
        self._validate_cookie_auth()
        if self.jwt_enabled and not self.domain:
            msg = "AUTH_DOMAIN must not be empty when AUTH_JWT_ENABLED is True"
            raise ValueError(msg)
        if self.jwt_enabled and not self.jwt_audience:
            msg = "AUTH_JWT_AUDIENCE must not be empty when AUTH_JWT_ENABLED is True"
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
    scheme_name=AUTH0_COOKIE_SCHEME_NAME,
    description="Auth0 session cookie authentication with admin role requirement. "
    f"User must have '{AUTH0_ROLE_ADMIN}' role in their configured role_claim.",
    auto_error=False,
)  # Security scheme specifically for admin endpoints

auth0_internal_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name=AUTH0_COOKIE_SCHEME_NAME,
    description="Auth0 session cookie authentication with internal organization membership requirement. "
    "User must be a member of the configured internal organization.",
    auto_error=False,
)  # Security scheme for internal endpoints

auth0_internal_admin_scheme = APIKeyCookie(
    name=AUTH0_SESSION_COOKIE_NAME,
    scheme_name=AUTH0_COOKIE_SCHEME_NAME,
    description=(
        "Auth0 session cookie authentication with internal organization membership AND admin role requirements. "
        f"User must be a member of the internal organization AND have '{AUTH0_ROLE_ADMIN}' role."
    ),
    auto_error=False,
)  # Security scheme for internal admin endpoints

auth0_bearer_scheme = HTTPBearer(
    scheme_name=AUTH0_BEARER_SCHEME_NAME,
    description="Auth0 JWT Bearer token authentication.",
    auto_error=False,
)

auth0_admin_bearer_scheme = HTTPBearer(
    scheme_name=AUTH0_BEARER_SCHEME_NAME,
    description="Auth0 JWT Bearer token authentication with admin role requirement. "
    f"User must have '{AUTH0_ROLE_ADMIN}' role in their configured role_claim.",
    auto_error=False,
)

auth0_internal_bearer_scheme = HTTPBearer(
    scheme_name=AUTH0_BEARER_SCHEME_NAME,
    description="Auth0 JWT Bearer token authentication with internal organization membership requirement. "
    "User must be a member of the configured internal organization.",
    auto_error=False,
)

auth0_internal_admin_bearer_scheme = HTTPBearer(
    scheme_name=AUTH0_BEARER_SCHEME_NAME,
    description=(
        "Auth0 JWT Bearer token authentication with internal organization membership AND admin role requirements. "
        f"User must be a member of the internal organization AND have '{AUTH0_ROLE_ADMIN}' role."
    ),
    auto_error=False,
)


async def _fetch_jwks(domain: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch JWKS from Auth0, caching the result per domain for AUTH0_JWKS_CACHE_TTL seconds.

    On fetch failure falls back to the last known good cache entry when one exists.

    Args:
        domain: Auth0 domain to fetch JWKS from.
        force_refresh: Bypass the TTL check and always fetch from the network.

    Returns:
        Parsed JWKS JSON as a dict.
    """
    entry = _jwks_cache.get(domain)
    if not force_refresh and entry is not None and (time.time() - entry.fetched_at) < AUTH0_JWKS_CACHE_TTL:
        return entry.jwks

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://{domain}/.well-known/jwks.json", timeout=10)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            _jwks_cache[domain] = _JwksCacheEntry(jwks=result, fetched_at=time.time())
            return result
    except Exception:
        if entry is not None:
            logger.warning("JWKS refresh failed for domain {}; using stale cache", domain)
            return entry.jwks
        raise


async def _extract_public_key(token: str, domain: str) -> AllowedRSAKeys | None:
    """Resolve the RSA public key for a JWT's kid from Auth0 JWKS.

    Fetches JWKS from cache; on a kid-miss, force-refreshes once before giving up.

    Args:
        token: The raw JWT string (used only to read the unverified header).
        domain: Auth0 domain to fetch JWKS from.

    Returns:
        RSA public key object on success, or None if the kid cannot be resolved.
    """
    jwks = await _fetch_jwks(domain)
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key_data is None:
        logger.debug("JWT kid not found in cache; force-refreshing JWKS", domain=domain, kid=kid)
        jwks = await _fetch_jwks(domain, force_refresh=True)

        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            logger.warning("JWT kid not found in JWKS after refresh", domain=domain, kid=kid)
            return None

    return RSAAlgorithm.from_jwk(key_data)


async def _validate_jwt(token: str, auth_settings: AuthSettings) -> dict[str, Any] | None:
    """Validate a Bearer JWT against the Auth0 JWKS.

    Returns:
        Decoded JWT claims dict on success, or None if validation fails.
    """
    try:
        public_key = await _extract_public_key(token, auth_settings.domain)
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key,  # pyright: ignore[reportArgumentType]  # from_jwk returns public key from JWKS
            algorithms=AUTH0_JWKS_ALGORITHMS,
            audience=auth_settings.jwt_audience,
            issuer=f"https://{auth_settings.domain}/",
        )
        return payload
    except Exception:  # noqa: BLE001
        logger.debug("JWT validation failed")
        return None


async def _require_authenticated_impl(
    request: Request,
    _cookie: str | None,
    _bearer: HTTPAuthorizationCredentials | None = None,
    role: str | None = None,
) -> None:
    """Internal implementation for authenticated session check with optional role.

    Args:
        request: The incoming request.
        _cookie: The session cookie.
        _bearer: Optional Bearer JWT credentials.
        role: Optional role required (e.g., "admin"). If specified, user must have
            this role in their configured role_claim.

    Raises:
        UnauthenticatedError: If the session is not valid or missing.
        ForbiddenError: If role is specified and user doesn't have the required role.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie, _bearer)
    if not user:
        logger.critical(USER_NOT_AUTHENTICATED)
        raise ForbiddenError(USER_NOT_AUTHENTICATED)

    log = logger.bind(user_id=user.get("sub"))

    # Check role if specified
    if role is not None:
        user_role = user.get(auth_settings.role_claim)
        if user_role != role:
            log.warning("Role check failed", required_role=role, actual_role=user_role)
            msg = f"User role '{user_role}' does not match required role '{role}'"
            raise ForbiddenError(msg)
        log.debug("Role check passed", role=role)


async def require_authenticated(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_session_scheme)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(auth0_bearer_scheme)],
) -> None:
    """Require an authenticated session (FastAPI dependency).

    Accepts either an Auth0 session cookie or a valid JWT Bearer token.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).
        _bearer: JWT Bearer credentials (auto-injected by FastAPI).

    Raises:
        ForbiddenError: If the session is not valid or missing.
    """
    await _require_authenticated_impl(request, _cookie, _bearer)


async def require_admin(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_admin_scheme)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(auth0_admin_bearer_scheme)],
) -> None:
    """Require admin role (FastAPI dependency).

    Accepts either an Auth0 session cookie or a valid JWT Bearer token.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).
        _bearer: JWT Bearer credentials (auto-injected by FastAPI).

    Raises:
        ForbiddenError: If the session is not valid or user doesn't have admin role.
    """
    await _require_authenticated_impl(request, _cookie, _bearer, role=AUTH0_ROLE_ADMIN)


async def require_internal(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_internal_scheme)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(auth0_internal_bearer_scheme)],
) -> None:
    """Require internal organization membership (FastAPI dependency).

    Checks if the authenticated user is a member of the configured internal organization.
    The internal organization is identified by the FOUNDRY_AUTH_INTERNAL_ORG_ID setting.
    Accepts either an Auth0 session cookie or a valid JWT Bearer token.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).
        _bearer: JWT Bearer credentials (auto-injected by FastAPI).

    Raises:
        ForbiddenError: If the session is not valid or user is not in the internal org.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie, _bearer)
    if not user:
        logger.critical(USER_NOT_AUTHENTICATED)
        raise ForbiddenError(USER_NOT_AUTHENTICATED)

    user_org_id = user.get("org_id")
    log = logger.bind(user_id=user.get("sub"), user_org=user_org_id)

    if user_org_id != auth_settings.internal_org_id:
        log.warning("Org membership check failed")
        msg = f"User is not a member of the internal organization (org_id: {user_org_id})"
        raise ForbiddenError(msg)

    log.debug("Org membership check passed")


async def require_internal_admin(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_internal_admin_scheme)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(auth0_internal_admin_bearer_scheme)],
) -> None:
    """Require internal organization membership AND admin role (FastAPI dependency).

    Checks if the authenticated user is both:
    1. A member of the configured internal organization (FOUNDRY_AUTH_INTERNAL_ORG_ID)
    2. Has the admin role in their configured role_claim
    Accepts either an Auth0 session cookie or a valid JWT Bearer token.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).
        _bearer: JWT Bearer credentials (auto-injected by FastAPI).

    Raises:
        ForbiddenError: If user is not internal or doesn't have admin role.
    """
    auth_settings = load_settings(AuthSettings)

    user = await get_user(request, _cookie, _bearer)
    if not user:
        logger.critical(USER_NOT_AUTHENTICATED)
        raise ForbiddenError(USER_NOT_AUTHENTICATED)

    user_org_id = user.get("org_id")
    user_role = user.get(auth_settings.role_claim)
    log = logger.bind(user_id=user.get("sub"), user_org=user_org_id, user_role=user_role)

    if user_org_id != auth_settings.internal_org_id:
        log.warning("Org membership check failed")
        msg = f"User is not a member of the internal organization (org_id: {user_org_id})"
        raise ForbiddenError(msg)

    if user_role != AUTH0_ROLE_ADMIN:
        log.warning("Role check failed", required_role=AUTH0_ROLE_ADMIN)
        msg = f"User role '{user_role}' does not match required role '{AUTH0_ROLE_ADMIN}'"
        raise ForbiddenError(msg)

    log.debug("Internal admin check passed")


async def get_user(
    request: Request,
    _cookie: Annotated[str | None, Security(auth0_session_scheme)],
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(auth0_bearer_scheme)],
) -> dict[str, Any] | None:
    """Get authenticated user information (FastAPI dependency).

    Tries Bearer JWT first (when jwt_enabled=True and a token is present), then falls
    back to the Auth0 encrypted session cookie. Returns None if neither authenticates.

    Args:
        request: The incoming request.
        _cookie: The session cookie (auto-injected by FastAPI).
        _bearer: JWT Bearer credentials (auto-injected by FastAPI).

    Returns:
        User dictionary containing claims like 'sub', 'email', 'name', etc.,
            or None if not authenticated.

    Example:
        @router.get("/me")
        async def me(user: Annotated[dict[str, Any], Depends(get_user)]):
            return {"email": user.get("email")}
    """
    auth_settings = load_settings(AuthSettings)

    # Try Bearer JWT first
    if _bearer and auth_settings.jwt_enabled:
        jwt_user = await _validate_jwt(_bearer.credentials, auth_settings)
        if jwt_user:
            set_sentry_user(jwt_user, role_claim=auth_settings.role_claim)
            return jwt_user
        logger.debug("Bearer token present but JWT validation failed; falling back to cookie")

    # Cookie path
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
