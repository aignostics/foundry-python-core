"""Tests for aignostics_foundry_core.sentry."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from aignostics_foundry_core.foundry import FoundryContext
from aignostics_foundry_core.sentry import SentrySettings, sentry_initialize, set_sentry_user

_VALID_DSN = "https://abc123def456@o99999.ingest.de.sentry.io/1234567"
_PROJECT = "testproject"
_VERSION = "1.0.0"
_ENVIRONMENT = "test"
_SENTRY_SET_USER = "sentry_sdk.set_user"
_AUTH0_USER = "auth0|x"
_SENTRY_PREFIX = "TESTPROJECT_SENTRY_"


def _mk_ctx(
    name: str = _PROJECT,
    version: str = _VERSION,
    environment: str = _ENVIRONMENT,
    env_prefix: str = "TESTPROJECT_",
    **kwargs: bool,
) -> FoundryContext:
    return FoundryContext(
        name=name,
        version=version,
        version_full=version,
        environment=environment,
        env_prefix=env_prefix,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.unit
class TestSentryInitialize:
    """Behavioural tests for sentry_initialize()."""

    def test_sentry_initialize_returns_false_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when TESTPROJECT_SENTRY_ENABLED is not set (default False)."""
        monkeypatch.delenv(f"{_SENTRY_PREFIX}ENABLED", raising=False)
        result = sentry_initialize(integrations=None, context=_mk_ctx())
        assert result is False

    def test_sentry_initialize_returns_false_when_sdk_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when sentry_sdk is not importable (find_spec returns None)."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        with patch("aignostics_foundry_core.sentry.find_spec", return_value=None):
            result = sentry_initialize(integrations=None, context=_mk_ctx())
        assert result is False

    def test_sentry_initialize_returns_true_and_calls_init_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns True and calls sentry_sdk.init with correct release when enabled with valid DSN."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        with (
            patch("sentry_sdk.init") as mock_init,
            patch("sentry_sdk.set_context"),
            patch("sentry_sdk.integrations.logging.ignore_logger"),
        ):
            result = sentry_initialize(integrations=None, context=_mk_ctx())
        assert result is True
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["release"] == f"{_PROJECT}@{_VERSION}"

    def test_sentry_initialize_returns_false_when_enabled_but_dsn_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when enabled but no DSN is configured."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.delenv(f"{_SENTRY_PREFIX}DSN", raising=False)
        result = sentry_initialize(integrations=None, context=_mk_ctx())
        assert result is False

    def test_sentry_initialize_uses_context_project_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sentry_sdk.init release tag uses the context project name."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        ctx = _mk_ctx(name="ctxproject")
        with (
            patch("sentry_sdk.init") as mock_init,
            patch("sentry_sdk.set_context"),
            patch("sentry_sdk.integrations.logging.ignore_logger"),
        ):
            result = sentry_initialize(integrations=None, context=ctx)
        assert result is True
        assert mock_init.call_args.kwargs["release"].startswith("ctxproject@")

    def test_sentry_initialize_uses_context_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sentry_sdk.init environment arg matches context.environment."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        ctx = _mk_ctx(environment="staging")
        with (
            patch("sentry_sdk.init") as mock_init,
            patch("sentry_sdk.set_context"),
            patch("sentry_sdk.integrations.logging.ignore_logger"),
        ):
            sentry_initialize(integrations=None, context=ctx)
        assert mock_init.call_args.kwargs["environment"] == "staging"

    def test_sentry_initialize_uses_sentry_context_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sentry_sdk.set_context receives runtime mode flags from the context."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        ctx = _mk_ctx(is_test=True)
        with (
            patch("sentry_sdk.init"),
            patch("sentry_sdk.set_context") as mock_set_ctx,
            patch("sentry_sdk.integrations.logging.ignore_logger"),
        ):
            sentry_initialize(integrations=None, context=ctx)
        ctx_data: dict[str, object] = mock_set_ctx.call_args.args[1]  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        assert ctx_data["test_mode"] is True


@pytest.mark.unit
class TestSentrySettingsDsnValidation:
    """Tests for SentrySettings DSN edge-case validation paths."""

    def test_dsn_missing_scheme_raises(self) -> None:
        """DSN without a URL scheme raises ValidationError."""
        with pytest.raises(ValidationError):
            SentrySettings(dsn="//abc@o1.ingest.de.sentry.io/1")  # pyright: ignore[reportCallIssue]

    def test_dsn_missing_netloc_raises(self) -> None:
        """DSN with only a scheme and no netloc raises ValidationError."""
        with pytest.raises(ValidationError):
            SentrySettings(dsn="https:")  # pyright: ignore[reportCallIssue]

    def test_dsn_missing_at_sign_raises(self) -> None:
        """DSN without an @ sign in the netloc raises ValidationError."""
        with pytest.raises(ValidationError):
            SentrySettings(dsn="https://o1.ingest.de.sentry.io/1")  # pyright: ignore[reportCallIssue]


@pytest.mark.unit
class TestSentrySettings:
    """Behavioural tests for SentrySettings validation."""

    def test_sentry_settings_rejects_invalid_dsn_http_scheme(self) -> None:
        """DSN with http:// scheme raises ValidationError."""
        with pytest.raises(ValidationError):
            SentrySettings(dsn="http://abc123@o99999.ingest.de.sentry.io/123")  # pyright: ignore[reportCallIssue]

    def test_sentry_settings_rejects_invalid_dsn_missing_domain(self) -> None:
        """DSN with non-Sentry domain raises ValidationError."""
        with pytest.raises(ValidationError):
            SentrySettings(dsn="https://abc123@example.com/123")  # pyright: ignore[reportCallIssue]

    def test_sentry_settings_accepts_valid_dsn(self) -> None:
        """Well-formed DSN with ingest.de.sentry.io domain is accepted."""
        settings = SentrySettings(dsn=_VALID_DSN)  # pyright: ignore[reportCallIssue]
        assert settings.dsn is not None
        assert settings.dsn.get_secret_value() == _VALID_DSN

    def test_sentry_settings_accepts_valid_dsn_us_region(self) -> None:
        """Well-formed DSN with ingest.us.sentry.io domain is accepted."""
        dsn = "https://abc123def456@o99999.ingest.us.sentry.io/1234567"
        settings = SentrySettings(dsn=dsn)  # pyright: ignore[reportCallIssue]
        assert settings.dsn is not None
        assert settings.dsn.get_secret_value() == dsn

    def test_sentry_settings_default_disabled(self) -> None:
        """Sentry is disabled by default (no env vars set)."""
        settings = SentrySettings()  # pyright: ignore[reportCallIssue]
        assert settings.enabled is False


@pytest.mark.unit
class TestSetSentryUser:
    """Behavioural tests for set_sentry_user()."""

    def test_set_sentry_user_maps_sub_to_id(self) -> None:
        """set_sentry_user maps 'sub' claim to 'id' in Sentry user context."""
        mock_set_user = MagicMock()
        with patch(_SENTRY_SET_USER, mock_set_user):
            set_sentry_user({"sub": _AUTH0_USER})
        mock_set_user.assert_called_once_with({"id": _AUTH0_USER})

    def test_set_sentry_user_none_clears_context(self) -> None:
        """set_sentry_user(None) calls sentry_sdk.set_user(None) to clear context."""
        mock_set_user = MagicMock()
        with patch(_SENTRY_SET_USER, mock_set_user):
            set_sentry_user(None)
        mock_set_user.assert_called_once_with(None)

    def test_set_sentry_user_does_nothing_when_sdk_absent(self) -> None:
        """set_sentry_user is a no-op when sentry_sdk is not importable."""
        with patch("aignostics_foundry_core.sentry.find_spec", return_value=None):
            # Should not raise even though sentry_sdk is unavailable
            set_sentry_user({"sub": _AUTH0_USER})

    def test_set_sentry_user_includes_role_from_claim(self) -> None:
        """set_sentry_user includes role from a custom claim when role_claim is provided."""
        mock_set_user = MagicMock()
        with patch(_SENTRY_SET_USER, mock_set_user):
            set_sentry_user(
                {"sub": _AUTH0_USER, "https://my/role": "admin"},
                role_claim="https://my/role",
            )
        assert mock_set_user.call_args[0][0]["role"] == "admin"

    def test_set_sentry_user_maps_multiple_fields(self) -> None:
        """set_sentry_user maps all standard Auth0 fields to Sentry user context."""
        mock_set_user = MagicMock()
        with patch(_SENTRY_SET_USER, mock_set_user):
            set_sentry_user({
                "sub": "auth0|abc",
                "email": "user@example.com",
                "name": "Test User",
                "org_id": "org_123",
            })
        sentry_user = mock_set_user.call_args[0][0]
        assert sentry_user["id"] == "auth0|abc"
        assert sentry_user["email"] == "user@example.com"
        assert sentry_user["name"] == "Test User"
        assert sentry_user["org_id"] == "org_123"
