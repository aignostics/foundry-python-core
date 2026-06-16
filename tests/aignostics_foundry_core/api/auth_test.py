"""Tests for aignostics_foundry_core.api.auth."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

from aignostics_foundry_core.api.auth import (
    AUTH0_ROLE_ADMIN,
    AUTH0_ROLE_SUPERADMIN,
    AUTH_SESSION_EXPIRATION_DEFAULT,
    AuthSettings,
    ForbiddenError,
    UnauthenticatedError,
    _fetch_jwks,
    _jwks_cache,
    _JwksCacheEntry,
    _validate_jwt,
    get_auth_client,
    get_user,
    require_admin,
    require_authenticated,
    require_internal,
    require_internal_admin,
    require_internal_superadmin,
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
_TEST_JWT_AUDIENCE = "https://api.example.com"
_TEST_BEARER_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QifQ.test.test"  # noqa: S105
_TEST_KID = "test-kid"
_FETCH_JWKS_PATH = "aignostics_foundry_core.api.auth._fetch_jwks"


@pytest.fixture
def jwt_settings() -> AuthSettings:
    """AuthSettings with JWT auth enabled (domain + audience pre-set)."""
    return AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)


@pytest.fixture
def auth_disabled() -> AuthSettings:
    """AuthSettings with all auth mechanisms disabled (the default)."""
    return AuthSettings()


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
        assert settings.cookie_enabled is False
        assert settings.enabled is False
        assert settings.jwt_enabled is False
        assert not settings.jwt_audience
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

    def test_cookie_enabled_requires_session_secret(self) -> None:
        """cookie_enabled=True with session_secret=None raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(cookie_enabled=True, session_secret=None)

    def test_deprecated_enabled_still_triggers_validation(self) -> None:
        """enabled=True (deprecated flag) still enforces all cookie auth validations."""
        with pytest.raises(pydantic.ValidationError):
            AuthSettings(enabled=True, session_secret=None)

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

    def test_cookie_enabled_with_all_required_fields_passes(self) -> None:
        """cookie_enabled=True with all required fields set validates successfully."""
        settings = AuthSettings(
            cookie_enabled=True,
            session_secret=_TEST_SESSION_SECRET,
            client_secret=_TEST_CLIENT_SECRET,
            domain=_TEST_DOMAIN,
            client_id=_TEST_CLIENT_ID,
            internal_org_id=_INTERNAL_ORG_ID,
            role_claim=_TEST_ROLE_CLAIM,
        )
        assert settings.cookie_enabled is True

    def test_jwt_enabled_requires_domain(self) -> None:
        """jwt_enabled=True with empty domain raises ValidationError."""
        with pytest.raises(pydantic.ValidationError, match="AUTH_DOMAIN"):
            AuthSettings(jwt_enabled=True, domain="", jwt_audience=_TEST_JWT_AUDIENCE)

    def test_jwt_enabled_requires_audience(self) -> None:
        """jwt_enabled=True with empty jwt_audience raises ValidationError."""
        with pytest.raises(pydantic.ValidationError, match="AUTH_JWT_AUDIENCE"):
            AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience="")

    def test_jwt_enabled_with_all_fields_passes(self) -> None:
        """jwt_enabled=True with domain and jwt_audience set does not raise."""
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)
        assert settings.jwt_enabled is True

    def test_jwt_enabled_independent_of_cookie_enabled(self) -> None:
        """jwt_enabled=True can be set without cookie_enabled=True."""
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)
        assert settings.cookie_enabled is False
        assert settings.enabled is False


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


def _make_bearer(token: str = _TEST_BEARER_TOKEN) -> MagicMock:
    """Create a mock HTTPAuthorizationCredentials with the given token."""
    bearer = MagicMock()
    bearer.credentials = token
    return bearer


@pytest.mark.integration
class TestGetUser:
    """Tests for get_user FastAPI dependency."""

    async def test_get_user_returns_none_without_session(self, auth_disabled: AuthSettings) -> None:
        """get_user returns None when get_auth_client raises (no session available)."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_auth_client raises naturally
        cookie = None

        result = await get_user(request, cookie, None, auth_disabled)

        assert result is None

    async def test_get_user_returns_none_for_expired_session(self, auth_disabled: AuthSettings) -> None:
        """get_user returns None when the session user token is expired."""
        request = MagicMock()
        cookie = "fake-cookie"

        fake_client = MagicMock()
        expired_user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) - 3600}
        fake_client.require_session = AsyncMock(return_value={"user": expired_user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie, None, auth_disabled)

        assert result is None

    async def test_get_user_returns_none_when_session_has_no_user_key(self, auth_disabled: AuthSettings) -> None:
        """get_user returns None when session exists but contains no 'user' key."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie, None, auth_disabled)

        assert result is None

    async def test_get_user_returns_none_when_exp_claim_missing(self, auth_disabled: AuthSettings) -> None:
        """get_user returns None when the user dict has no 'exp' claim."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": {"sub": "x"}})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie, None, auth_disabled)

        assert result is None

    async def test_get_user_returns_none_when_session_is_not_a_dict(self, auth_disabled: AuthSettings) -> None:
        """get_user returns None when require_session returns a non-dict value."""
        request = MagicMock()
        cookie = "fake-cookie"
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value="not-a-dict")
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie, None, auth_disabled)

        assert result is None

    async def test_get_user_returns_user_for_valid_session(self, auth_disabled: AuthSettings) -> None:
        """get_user returns the user dict when the session is valid and not expired."""
        request = MagicMock()
        cookie = "fake-cookie"
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, cookie, None, auth_disabled)

        assert result == user

    async def test_get_user_bearer_takes_priority_over_cookie(self, jwt_settings: AuthSettings) -> None:
        """get_user returns JWT user when both bearer and cookie are valid."""
        jwt_user = {"sub": "jwt|user", "email": "jwt@example.com", "exp": int(time.time()) + 3600}
        cookie_user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}

        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": cookie_user})
        request.app.state.auth_client = fake_client

        with patch("aignostics_foundry_core.api.auth._validate_jwt", AsyncMock(return_value=jwt_user)):
            result = await get_user(request, "cookie-value", _make_bearer(), jwt_settings)

        assert result == jwt_user

    async def test_get_user_falls_back_to_cookie_when_bearer_absent(self, auth_disabled: AuthSettings) -> None:
        """get_user uses cookie when _bearer is None."""
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, "cookie-value", None, auth_disabled)

        assert result == user

    async def test_get_user_falls_back_to_cookie_when_jwt_disabled(self, auth_disabled: AuthSettings) -> None:
        """get_user uses cookie when jwt_enabled=False even if bearer token is present."""
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await get_user(request, "cookie-value", _make_bearer(), auth_disabled)

        assert result == user

    async def test_get_user_falls_back_to_cookie_when_bearer_invalid(self, jwt_settings: AuthSettings) -> None:
        """get_user falls back to cookie when JWT validation fails."""
        cookie_user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        request = MagicMock()
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": cookie_user})
        request.app.state.auth_client = fake_client

        with patch("aignostics_foundry_core.api.auth._validate_jwt", AsyncMock(return_value=None)):
            result = await get_user(request, "cookie-value", _make_bearer(), jwt_settings)

        assert result == cookie_user


@pytest.mark.unit
class TestValidateJwt:
    """Unit tests for _validate_jwt (JWT validation helper)."""

    @pytest.fixture
    def mock_jwks(self) -> dict:
        """A minimal JWKS response with one RSA key entry."""
        return {"keys": [{"kid": _TEST_KID, "kty": "RSA", "use": "sig"}]}

    async def test_validate_jwt_returns_none_when_kid_absent_after_refresh(self) -> None:
        """_validate_jwt returns None when kid is absent from JWKS even after a force-refresh."""
        jwks_without_kid: dict = {"keys": []}
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)

        with patch(_FETCH_JWKS_PATH, AsyncMock(return_value=jwks_without_kid)):
            import jwt

            with patch.object(jwt, "get_unverified_header", return_value={"kid": _TEST_KID, "alg": "RS256"}):
                result = await _validate_jwt(_TEST_BEARER_TOKEN, settings)

        assert result is None

    async def test_validate_jwt_force_refreshes_on_kid_miss_and_succeeds(self) -> None:
        """_validate_jwt retries with a force-refreshed JWKS when the kid is missing from cache."""
        import jwt
        from jwt.algorithms import RSAAlgorithm

        stale_jwks: dict = {"keys": []}
        fresh_jwks: dict = {"keys": [{"kid": _TEST_KID, "kty": "RSA", "use": "sig"}]}
        expected_payload = {"sub": _USER_SUB, "exp": int(time.time()) + 3600}
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)

        fetch_mock = AsyncMock(side_effect=[stale_jwks, fresh_jwks])
        with (
            patch(_FETCH_JWKS_PATH, fetch_mock),
            patch.object(jwt, "get_unverified_header", return_value={"kid": _TEST_KID, "alg": "RS256"}),
            patch.object(RSAAlgorithm, "from_jwk", return_value=MagicMock()),
            patch.object(jwt, "decode", return_value=expected_payload),
        ):
            result = await _validate_jwt(_TEST_BEARER_TOKEN, settings)

        assert result == expected_payload
        assert fetch_mock.call_count == 2
        _, kwargs = fetch_mock.call_args
        assert kwargs.get("force_refresh") is True

    async def test_validate_jwt_returns_none_on_fetch_failure(self) -> None:
        """_validate_jwt returns None when JWKS fetch raises an exception."""
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)

        with patch(_FETCH_JWKS_PATH, AsyncMock(side_effect=RuntimeError("network error"))):
            result = await _validate_jwt(_TEST_BEARER_TOKEN, settings)

        assert result is None

    async def test_validate_jwt_returns_none_for_invalid_token(self, mock_jwks: dict) -> None:
        """_validate_jwt returns None when jwt.decode raises (e.g., expired or bad signature)."""
        import jwt
        from jwt.algorithms import RSAAlgorithm

        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)

        with (
            patch(_FETCH_JWKS_PATH, AsyncMock(return_value=mock_jwks)),
            patch.object(jwt, "get_unverified_header", return_value={"kid": _TEST_KID, "alg": "RS256"}),
            patch.object(RSAAlgorithm, "from_jwk", return_value=MagicMock()),
            patch.object(jwt, "decode", side_effect=jwt.ExpiredSignatureError("expired")),
        ):
            result = await _validate_jwt(_TEST_BEARER_TOKEN, settings)

        assert result is None

    async def test_validate_jwt_returns_payload_for_valid_token(self, mock_jwks: dict) -> None:
        """_validate_jwt returns decoded payload when token is valid."""
        import jwt
        from jwt.algorithms import RSAAlgorithm

        expected_payload = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        settings = AuthSettings(jwt_enabled=True, domain=_TEST_DOMAIN, jwt_audience=_TEST_JWT_AUDIENCE)

        with (
            patch(_FETCH_JWKS_PATH, AsyncMock(return_value=mock_jwks)),
            patch.object(jwt, "get_unverified_header", return_value={"kid": _TEST_KID, "alg": "RS256"}),
            patch.object(RSAAlgorithm, "from_jwk", return_value=MagicMock()),
            patch.object(jwt, "decode", return_value=expected_payload),
        ):
            result = await _validate_jwt(_TEST_BEARER_TOKEN, settings)

        assert result == expected_payload


@pytest.mark.integration
class TestRequireAuthenticated:
    """Tests for require_authenticated FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_authenticated raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_authenticated(request, None, None, jwt_settings)

    async def test_authenticated_user_passes(self, auth_disabled: AuthSettings) -> None:
        """require_authenticated returns None without raising when user is authenticated."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "email": _USER_EMAIL, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_authenticated(request, None, None, auth_disabled)
        assert result is None


@pytest.mark.integration
class TestRequireAdmin:
    """Tests for require_admin FastAPI dependency."""

    async def test_no_user_raises_forbidden_error(self) -> None:
        """require_admin raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError):
            await require_admin(
                request,
                None,
                None,
                AuthSettings(
                    jwt_enabled=True,
                    domain=_TEST_DOMAIN,
                    jwt_audience=_TEST_JWT_AUDIENCE,
                    role_claim=_TEST_ROLE_CLAIM,
                ),
            )

    async def test_wrong_role_raises_forbidden_error(self) -> None:
        """require_admin raises ForbiddenError when user has a non-admin role."""
        request = MagicMock()
        user = {"sub": _USER_SUB, _TEST_ROLE_CLAIM: "viewer", "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_admin(
                request,
                None,
                None,
                AuthSettings(
                    jwt_enabled=True,
                    domain=_TEST_DOMAIN,
                    jwt_audience=_TEST_JWT_AUDIENCE,
                    role_claim=_TEST_ROLE_CLAIM,
                ),
            )

    async def test_admin_role_passes(self) -> None:
        """require_admin returns None without raising when user has the admin role."""
        request = MagicMock()
        user = {"sub": _USER_SUB, _TEST_ROLE_CLAIM: AUTH0_ROLE_ADMIN, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_admin(request, None, None, AuthSettings(role_claim=_TEST_ROLE_CLAIM))
        assert result is None


@pytest.mark.integration
class TestRequireInternal:
    """Tests for require_internal FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal(request, None, None, jwt_settings)

    async def test_wrong_org_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal raises ForbiddenError when user belongs to a different org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal(request, None, None, jwt_settings)

    async def test_internal_org_member_passes(self) -> None:
        """require_internal returns None without raising when user is in the internal org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _INTERNAL_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_internal(request, None, None, AuthSettings(internal_org_id=_INTERNAL_ORG_ID))
        assert result is None


@pytest.mark.integration
class TestRequireInternalAdmin:
    """Tests for require_internal_admin FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal_admin raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal_admin(request, None, None, jwt_settings)

    async def test_wrong_org_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal_admin raises ForbiddenError when user belongs to a different org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal_admin(request, None, None, jwt_settings)

    async def test_correct_org_wrong_role_raises_forbidden_error(self) -> None:
        """require_internal_admin raises ForbiddenError when user is in internal org but lacks admin role."""
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
            await require_internal_admin(
                request,
                None,
                None,
                AuthSettings(
                    jwt_enabled=True,
                    domain=_TEST_DOMAIN,
                    jwt_audience=_TEST_JWT_AUDIENCE,
                    internal_org_id=_INTERNAL_ORG_ID,
                    role_claim=_TEST_ROLE_CLAIM,
                ),
            )

    async def test_internal_admin_passes(self) -> None:
        """require_internal_admin returns None without raising when user is internal org admin."""
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

        result = await require_internal_admin(
            request,
            None,
            None,
            AuthSettings(internal_org_id=_INTERNAL_ORG_ID, role_claim=_TEST_ROLE_CLAIM),
        )
        assert result is None


@pytest.mark.unit
class TestFetchJwks:
    """Unit tests for _fetch_jwks (JWKS fetching and caching helper)."""

    def setup_method(self) -> None:
        """Clear the JWKS cache before each test for isolation."""
        _jwks_cache.clear()

    async def test_returns_cached_jwks_when_fresh(self) -> None:
        """_fetch_jwks returns the in-memory cached JWKS without an HTTP call when fresh."""
        cached_jwks: dict = {"keys": [{"kid": _TEST_KID}]}
        _jwks_cache[_TEST_DOMAIN] = _JwksCacheEntry(jwks=cached_jwks, fetched_at=time.time())

        result = await _fetch_jwks(_TEST_DOMAIN)

        assert result is cached_jwks

    async def test_fetches_and_caches_on_cache_miss(self) -> None:
        """_fetch_jwks makes an HTTP request, stores the result in cache, and returns it."""
        fetched_jwks: dict = {"keys": [{"kid": _TEST_KID, "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = fetched_jwks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_jwks(_TEST_DOMAIN)

        assert result == fetched_jwks
        assert _TEST_DOMAIN in _jwks_cache
        assert _jwks_cache[_TEST_DOMAIN].jwks == fetched_jwks

    async def test_force_refresh_bypasses_fresh_cache(self) -> None:
        """_fetch_jwks hits the network even when a fresh cache entry exists if force_refresh=True."""
        stale_jwks: dict = {"keys": [{"kid": "old-kid"}]}
        fresh_jwks: dict = {"keys": [{"kid": _TEST_KID, "kty": "RSA"}]}
        _jwks_cache[_TEST_DOMAIN] = _JwksCacheEntry(jwks=stale_jwks, fetched_at=time.time())

        mock_response = MagicMock()
        mock_response.json.return_value = fresh_jwks
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_jwks(_TEST_DOMAIN, force_refresh=True)

        assert result == fresh_jwks
        mock_client.get.assert_called_once()

    async def test_stale_cache_returned_on_fetch_failure(self) -> None:
        """_fetch_jwks returns the stale cached JWKS when the network request fails."""
        stale_jwks: dict = {"keys": [{"kid": _TEST_KID}]}
        _jwks_cache[_TEST_DOMAIN] = _JwksCacheEntry(jwks=stale_jwks, fetched_at=0.0)  # expired

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_jwks(_TEST_DOMAIN)

        assert result is stale_jwks

    async def test_raises_when_fetch_fails_and_no_cache(self) -> None:
        """_fetch_jwks re-raises the exception when the network request fails and no cache exists."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client), pytest.raises(RuntimeError, match="network error"):
            await _fetch_jwks(_TEST_DOMAIN)


@pytest.mark.integration
class TestRequireInternalSuperadmin:
    """Tests for require_internal_superadmin FastAPI dependency."""

    async def test_unauthenticated_user_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal_superadmin raises ForbiddenError when no session is available."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError, match=_USER_NOT_AUTHENTICATED):
            await require_internal_superadmin(request, None, None, jwt_settings)

    async def test_wrong_org_raises_forbidden_error(self, jwt_settings: AuthSettings) -> None:
        """require_internal_superadmin raises ForbiddenError when user belongs to a different org."""
        request = MagicMock()
        user = {"sub": _USER_SUB, "org_id": _OTHER_ORG_ID, "exp": int(time.time()) + 3600}
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        with pytest.raises(ForbiddenError, match="not a member of the internal organization"):
            await require_internal_superadmin(request, None, None, jwt_settings)

    async def test_correct_org_wrong_role_raises_forbidden_error(self) -> None:
        """require_internal_superadmin raises ForbiddenError when user is in internal org but lacks superadmin role."""
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

        with pytest.raises(ForbiddenError, match="does not match required role"):
            await require_internal_superadmin(
                request,
                None,
                None,
                AuthSettings(
                    jwt_enabled=True,
                    domain=_TEST_DOMAIN,
                    jwt_audience=_TEST_JWT_AUDIENCE,
                    internal_org_id=_INTERNAL_ORG_ID,
                    role_claim=_TEST_ROLE_CLAIM,
                ),
            )

    async def test_internal_superadmin_passes(self) -> None:
        """require_internal_superadmin returns None without raising when user is internal org superadmin."""
        request = MagicMock()
        user = {
            "sub": _USER_SUB,
            "org_id": _INTERNAL_ORG_ID,
            _TEST_ROLE_CLAIM: AUTH0_ROLE_SUPERADMIN,
            "exp": int(time.time()) + 3600,
        }
        fake_client = MagicMock()
        fake_client.require_session = AsyncMock(return_value={"user": user})
        request.app.state.auth_client = fake_client

        result = await require_internal_superadmin(
            request,
            None,
            None,
            AuthSettings(internal_org_id=_INTERNAL_ORG_ID, role_claim=_TEST_ROLE_CLAIM),
        )
        assert result is None


@pytest.mark.integration
class TestAuthDisabledBypass:
    """Tests that all require_* dependencies bypass checks when auth is fully disabled."""

    async def test_require_authenticated_bypasses_when_auth_disabled(self, auth_disabled: AuthSettings) -> None:
        """require_authenticated passes without checking session when all auth is disabled."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])

        result = await require_authenticated(request, None, None, auth_disabled)
        assert result is None

    async def test_require_admin_bypasses_when_auth_disabled(self, auth_disabled: AuthSettings) -> None:
        """require_admin passes without checking session or role when all auth is disabled."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])

        result = await require_admin(request, None, None, auth_disabled)
        assert result is None

    async def test_require_internal_bypasses_when_auth_disabled(self, auth_disabled: AuthSettings) -> None:
        """require_internal passes without checking org membership when all auth is disabled."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])

        result = await require_internal(request, None, None, auth_disabled)
        assert result is None

    async def test_require_internal_admin_bypasses_when_auth_disabled(self, auth_disabled: AuthSettings) -> None:
        """require_internal_admin passes without checking org or role when all auth is disabled."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])

        result = await require_internal_admin(request, None, None, auth_disabled)
        assert result is None

    async def test_require_internal_superadmin_bypasses_when_auth_disabled(self, auth_disabled: AuthSettings) -> None:
        """require_internal_superadmin passes without checking org or role when all auth is disabled."""
        request = MagicMock()
        request.app.state = MagicMock(spec=[])

        result = await require_internal_superadmin(request, None, None, auth_disabled)
        assert result is None

    async def test_require_authenticated_enforces_when_cookie_enabled(self) -> None:
        """require_authenticated still enforces auth when cookie_enabled=True."""
        settings = AuthSettings(
            cookie_enabled=True,
            session_secret=_TEST_SESSION_SECRET,
            client_secret=_TEST_CLIENT_SECRET,
            domain=_TEST_DOMAIN,
            client_id=_TEST_CLIENT_ID,
            internal_org_id=_INTERNAL_ORG_ID,
            role_claim=_TEST_ROLE_CLAIM,
        )
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no auth_client → get_user returns None

        with pytest.raises(ForbiddenError):
            await require_authenticated(request, None, None, settings)
