"""Tests for aignostics_foundry_core.api.auth."""

import time
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from aignostics_foundry_core.api.auth import (
    AUTH0_ROLE_ADMIN,
    DEFAULT_AUTH0_ROLE_CLAIM,
    AuthSettings,
    ForbiddenError,
    UnauthenticatedError,
    get_auth_client,
    get_user,
    require_admin,
    require_authenticated,
    require_internal,
    require_internal_admin,
)
from aignostics_foundry_core.foundry import reset_context, set_context
from tests.conftest import TEST_PROJECT_PREFIX, make_context

_INTERNAL_ORG_ID = "org_internal_123"
_OTHER_ORG_ID = "org_other_456"
_USER_NOT_AUTHENTICATED = "User is not authenticated"
_USER_SUB = "auth0|x"
_USER_EMAIL = "x@x.com"


@pytest.fixture(autouse=True)
def _auth_context() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Set a real FoundryContext for all auth tests to preserve FOUNDRY_AUTH_* env var names.

    Yields:
        None
    """
    set_context(make_context())
    yield
    reset_context()


@pytest.mark.unit
class TestUnauthenticatedError:
    """Tests for UnauthenticatedError."""

    def test_unauthenticated_error_is_exception(self) -> None:
        """UnauthenticatedError must inherit from Exception for standard exception handling."""
        assert issubclass(UnauthenticatedError, Exception)


@pytest.mark.unit
class TestForbiddenError:
    """Tests for ForbiddenError."""

    def test_forbidden_error_status_code(self) -> None:
        """ForbiddenError carries HTTP 403 status code."""
        err = ForbiddenError()
        assert err.status_code == 403

    def test_forbidden_error_message_override(self) -> None:
        """Custom message is reflected in str representation."""
        err = ForbiddenError(message="nope")
        assert err.message == "nope"


@pytest.mark.unit
class TestGetAuthClient:
    """Tests for get_auth_client."""

    def test_get_auth_client_raises_without_state(self) -> None:
        """get_auth_client raises RuntimeError when app state has no auth_client attribute."""
        request = MagicMock()
        del request.app.state.auth_client  # ensure attribute is absent
        # hasattr check on a MagicMock always returns True unless we spec it
        request.app.state = MagicMock(spec=[])  # spec=[] → no attributes

        with pytest.raises(RuntimeError, match="auth0 is not enabled"):
            get_auth_client(request)

    def test_get_auth_client_returns_client_when_present(self) -> None:
        """get_auth_client returns the auth_client stored on app state."""
        fake_client = MagicMock()
        request = MagicMock()
        request.app.state.auth_client = fake_client

        result = get_auth_client(request)
        assert result is fake_client


@pytest.mark.unit
class TestAuthSettings:
    """Tests for AuthSettings defaults."""

    def test_auth_settings_defaults(self) -> None:
        """AuthSettings.auth0_role_claim has the expected default role claim URL."""
        settings = AuthSettings()
        assert settings.auth0_role_claim == DEFAULT_AUTH0_ROLE_CLAIM
        assert settings.internal_org_id is None

    def test_auth_settings_role_claim_value(self) -> None:
        """The default role claim is the Aignostics platform bridge claim URL."""
        assert DEFAULT_AUTH0_ROLE_CLAIM == "https://aignostics-platform-bridge/role"

    def test_auth_settings_uses_context_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AuthSettings reads env vars from the prefix supplied by FoundryContext."""
        set_context(make_context())
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}AUTH_AUTH0_ROLE_CLAIM", "https://custom/role")
        settings = AuthSettings()
        assert settings.auth0_role_claim == "https://custom/role"


@pytest.mark.integration
class TestGetUser:
    """Tests for get_user FastAPI dependency."""

    async def test_get_user_returns_none_without_session(self) -> None:
        """get_user returns None when get_auth_client raises (no session available)."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_auth_client raises naturally
        cookie = None

        result = await get_user(request, cookie)

        assert result is None

    async def test_get_user_returns_none_for_expired_session(self) -> None:
        """get_user returns None when the session user token is expired."""
        request = MagicMock()
        cookie = "fake-cookie"

        fake_client = MagicMock()
        expired_user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) - 3600}
        fake_client.require_session = AsyncMock(return_value={"user": expired_user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie)

        assert result is None

    async def test_get_user_returns_none_when_session_has_no_user_key(self) -> None:
        """get_user returns None when session exists but contains no 'user' key."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie)

        assert result is None

    async def test_get_user_returns_none_when_exp_claim_missing(self) -> None:
        """get_user returns None when the user dict has no 'exp' claim."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": {"sub": "x"}})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie)

        assert result is None

    async def test_get_user_returns_user_for_valid_session(self) -> None:
        """get_user returns the user dict when the session is valid and not expired."""
        request = MagicMock()
        cookie = "fake-cookie"
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie)

        assert result == user


@pytest.mark.integration
class TestRequireAuthenticated:
    """Tests for require_authenticated FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self) -> None:
        """require_authenticated raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_authenticated(request, None)

    async def test_authenticated_user_passes(self) -> None:
        """require_authenticated returns None without raising when user is authenticated."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_authenticated(request, None)
        assert result is None


@pytest.mark.integration
class TestRequireAdmin:
    """Tests for require_admin FastAPI dependency."""

    async def test_no_user_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_admin raises ForbiddenError when no session is available."""
        monkeypatch.delenv("FOUNDRY_AUTH_AUTH0_ROLE_CLAIM", raising=False)
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError):
            await require_admin(request, None)

    async def test_wrong_role_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_admin raises ForbiddenError when user has a non-admin role."""
        monkeypatch.delenv("FOUNDRY_AUTH_AUTH0_ROLE_CLAIM", raising=False)
        request = MagicMock()
        user = {"sub": _USER_SUB, DEFAULT_AUTH0_ROLE_CLAIM: "viewer", "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_admin(request, None)

    async def test_admin_role_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_admin returns None without raising when user has the admin role."""
        monkeypatch.delenv("FOUNDRY_AUTH_AUTH0_ROLE_CLAIM", raising=False)
        request = MagicMock()
        user = {"sub": _USER_SUB, DEFAULT_AUTH0_ROLE_CLAIM: AUTH0_ROLE_ADMIN, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_admin(request, None)
        assert result is None


@pytest.mark.integration
class TestRequireInternal:
    """Tests for require_internal FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal raises ForbiddenError when no session is available."""
        monkeypatch.setenv("FOUNDRY_AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal(request, None)

    async def test_wrong_org_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal raises ForbiddenError when user belongs to a different org."""
        monkeypatch.setenv("FOUNDRY_AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal(request, None)

    async def test_internal_org_member_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal returns None without raising when user is in the internal org."""
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _INTERNAL_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_internal(request, None)
        assert result is None


@pytest.mark.integration
class TestRequireInternalAdmin:
    """Tests for require_internal_admin FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin raises ForbiddenError when no session is available."""
        monkeypatch.setenv("FOUNDRY_AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal_admin(request, None)

    async def test_wrong_org_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin raises ForbiddenError when user belongs to a different org."""
        monkeypatch.setenv("FOUNDRY_AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal_admin(request, None)

    async def test_correct_org_wrong_role_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin raises ForbiddenError when user is in internal org but lacks admin role."""
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        monkeypatch.delenv(f"{TEST_PROJECT_PREFIX}AUTH_AUTH0_ROLE_CLAIM", raising=False)
        request = MagicMock()
        user = {
            "sub": _USER_SUB,
            "org_id": _INTERNAL_ORG_ID,
            DEFAULT_AUTH0_ROLE_CLAIM: "viewer",
            "exp": int(time.time()) + 3600,
        }
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_internal_admin(request, None)

    async def test_internal_admin_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin returns None without raising when user is internal org admin."""
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}AUTH_INTERNAL_ORG_ID", _INTERNAL_ORG_ID)
        monkeypatch.delenv(f"{TEST_PROJECT_PREFIX}AUTH_AUTH0_ROLE_CLAIM", raising=False)
        request = MagicMock()
        user = {
            "sub": _USER_SUB,
            "org_id": _INTERNAL_ORG_ID,
            DEFAULT_AUTH0_ROLE_CLAIM: AUTH0_ROLE_ADMIN,
            "exp": int(time.time()) + 3600,
        }
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_internal_admin(request, None)
        assert result is None
