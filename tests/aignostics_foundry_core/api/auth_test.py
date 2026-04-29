"""Tests for aignostics_foundry_core.api.auth."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pydantic
import pytest

from aignostics_foundry_core.api.auth import (
    AUTH0_ROLE_ADMIN,
    AUTH_SESSION_EXPIRATION_DEFAULT,
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
from aignostics_foundry_core.foundry import set_context
from tests.aignostics_foundry_core.api import INTERNAL_ORG_ID_VAR_NAME, ROLE_CLAIM_VAR_NAME
from tests.conftest import make_context

_INTERNAL_ORG_ID = "org_internal_123"
_OTHER_ORG_ID = "org_other_456"
_TEST_ROLE_CLAIM = "https://aignostics-platform-bridge/role"
_USER_NOT_AUTHENTICATED = "User is not authenticated"
_USER_SUB = "auth0|x"
_USER_EMAIL = "x@x.com"
_TEST_SESSION_SECRET = "test-session-secret"  # noqa: S105
_TEST_CLIENT_SECRET = "x" * 64
_TEST_CLIENT_ID = "x" * 32
_TEST_DOMAIN = "example.auth0.com"


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
    """Tests for AuthSettings."""

    def test_auth_settings_defaults(self) -> None:
        """AuthSettings has correct defaults when no env vars are set."""
        settings = AuthSettings()
        assert settings.enabled is False
        assert not settings.internal_org_id
        assert not settings.role_claim
        assert not settings.domain
        assert not settings.client_id
        assert settings.session_expiration == AUTH_SESSION_EXPIRATION_DEFAULT

    def test_auth_settings_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AuthSettings reads field values from env vars using the context's env prefix."""
        monkeypatch.setenv(INTERNAL_ORG_ID_VAR_NAME, "myorg")
        settings = AuthSettings()
        assert settings.internal_org_id == "myorg"

    def test_auth_settings_uses_context_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AuthSettings reads fields from env vars using the context's prefix."""
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, "https://custom/role")
        settings = AuthSettings()
        assert settings.role_claim == "https://custom/role"

    def test_enabled_requires_session_secret(self) -> None:
        """enabled=True with session_secret=None raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(enabled=True, session_secret=None)

    def test_enabled_requires_client_secret(self) -> None:
        """enabled=True with client_secret=None raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(
                enabled=True,
                session_secret=_TEST_SESSION_SECRET,
                client_secret=None,
            )

    def test_enabled_requires_non_empty_domain(self) -> None:
        """enabled=True with empty domain raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(
                enabled=True,
                session_secret=_TEST_SESSION_SECRET,
                client_secret=_TEST_CLIENT_SECRET,
                domain="",
            )

    def test_enabled_requires_non_empty_client_id(self) -> None:
        """enabled=True with empty client_id raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(
                enabled=True,
                session_secret=_TEST_SESSION_SECRET,
                client_secret=_TEST_CLIENT_SECRET,
                domain=_TEST_DOMAIN,
                client_id="",
            )

    def test_enabled_requires_non_empty_internal_org_id(self) -> None:
        """enabled=True with empty internal_org_id raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(
                enabled=True,
                session_secret=_TEST_SESSION_SECRET,
                client_secret=_TEST_CLIENT_SECRET,
                domain=_TEST_DOMAIN,
                client_id=_TEST_CLIENT_ID,
                internal_org_id="",
            )

    def test_enabled_requires_non_empty_role_claim(self) -> None:
        """enabled=True with empty role_claim raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(
                enabled=True,
                session_secret=_TEST_SESSION_SECRET,
                client_secret=_TEST_CLIENT_SECRET,
                domain=_TEST_DOMAIN,
                client_id=_TEST_CLIENT_ID,
                internal_org_id=_INTERNAL_ORG_ID,
                role_claim="",
            )


@pytest.mark.integration
class TestAuthSettingsEnvFile:
    """Tests for AuthSettings env file loading."""

    def test_auth_settings_reads_fields_from_env_file_via_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AuthSettings reads fields from a .env file listed in the active FoundryContext."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            f"{INTERNAL_ORG_ID_VAR_NAME}=org_from_env_file\n{ROLE_CLAIM_VAR_NAME}=claim_from_env_file\n"
        )

        set_context(make_context(env_file=[env_file]))

        monkeypatch.delenv(INTERNAL_ORG_ID_VAR_NAME, raising=False)
        monkeypatch.delenv(ROLE_CLAIM_VAR_NAME, raising=False)

        settings = AuthSettings()

        assert settings.internal_org_id == "org_from_env_file"
        assert settings.role_claim == "claim_from_env_file"


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

    async def test_get_user_returns_none_when_session_is_not_a_dict(self) -> None:
        """get_user returns None when require_session returns a non-dict value."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value="not-a-dict")
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
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, _TEST_ROLE_CLAIM)
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError):
            await require_admin(request, None)

    async def test_wrong_role_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_admin raises ForbiddenError when user has a non-admin role."""
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, _TEST_ROLE_CLAIM)
        request = MagicMock()
        user = {"sub": _USER_SUB, _TEST_ROLE_CLAIM: "viewer", "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_admin(request, None)

    async def test_admin_role_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_admin returns None without raising when user has the admin role."""
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, _TEST_ROLE_CLAIM)
        request = MagicMock()
        user = {"sub": _USER_SUB, _TEST_ROLE_CLAIM: AUTH0_ROLE_ADMIN, "exp": int(time.time()) + 3600}
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
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal(request, None)

    async def test_wrong_org_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal raises ForbiddenError when user belongs to a different org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal(request, None)

    async def test_internal_org_member_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal returns None without raising when user is in the internal org."""
        monkeypatch.setenv(INTERNAL_ORG_ID_VAR_NAME, _INTERNAL_ORG_ID)
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
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal_admin(request, None)

    async def test_wrong_org_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin raises ForbiddenError when user belongs to a different org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal_admin(request, None)

    async def test_correct_org_wrong_role_raises_forbidden_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin raises ForbiddenError when user is in internal org but lacks admin role."""
        monkeypatch.setenv(INTERNAL_ORG_ID_VAR_NAME, _INTERNAL_ORG_ID)
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, _TEST_ROLE_CLAIM)
        request = MagicMock()
        user = {
            "sub": _USER_SUB,
            "org_id": _INTERNAL_ORG_ID,
            _TEST_ROLE_CLAIM: "viewer",
            "exp": int(time.time()) + 3600,
        }
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_internal_admin(request, None)

    async def test_internal_admin_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """require_internal_admin returns None without raising when user is internal org admin."""
        monkeypatch.setenv(INTERNAL_ORG_ID_VAR_NAME, _INTERNAL_ORG_ID)
        monkeypatch.setenv(ROLE_CLAIM_VAR_NAME, _TEST_ROLE_CLAIM)
        request = MagicMock()
        user = {
            "sub": _USER_SUB,
            "org_id": _INTERNAL_ORG_ID,
            _TEST_ROLE_CLAIM: AUTH0_ROLE_ADMIN,
            "exp": int(time.time()) + 3600,
        }
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_internal_admin(request, None)
        assert result is None
