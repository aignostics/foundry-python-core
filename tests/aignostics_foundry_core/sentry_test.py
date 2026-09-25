"""Tests for aignostics_foundry_core.sentry."""

from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
import sentry_sdk
from pydantic import ValidationError
from sentry_sdk.client import NonRecordingClient
from sentry_sdk.transport import Transport

from aignostics_foundry_core.foundry import set_context
from aignostics_foundry_core.sentry import SentrySettings, sentry_initialize, set_sentry_user
from tests.conftest import TEST_PROJECT_NAME, TEST_PROJECT_PREFIX, make_context

if TYPE_CHECKING:
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.integrations import Integration

    from aignostics_foundry_core.foundry import FoundryContext

_VALID_DSN = "https://abc123def456@o99999.ingest.de.sentry.io/1234567"
_SENTRY_SET_USER = "sentry_sdk.set_user"
_AUTH0_USER = "auth0|x"
_SENTRY_PREFIX = f"{TEST_PROJECT_PREFIX}SENTRY_"
_PROBE_MESSAGE = "probe"
_EVENT_ITEM_TYPES = {"event", "transaction"}


class _CapturingTransport(Transport):
    """Sentry transport that keeps every envelope in memory instead of sending it."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        """Initialise the transport with an empty envelope list."""
        super().__init__(options)
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: "Envelope") -> None:
        """Store *envelope* for later inspection."""
        self.envelopes.append(envelope)


class SentryCapture:
    """Handle returned by the ``sentry_capture`` fixture.

    Starts Sentry through :func:`sentry_initialize` and gives access to the envelope
    items that the SDK would have sent to Sentry.
    """

    def __init__(self, transport: _CapturingTransport) -> None:
        """Wrap *transport*, which receives every envelope of the started client."""
        self._transport = transport

    def start(
        self,
        integrations: "list[Integration] | None" = None,
        *,
        context: "FoundryContext | None" = None,
    ) -> bool:
        """Call :func:`sentry_initialize` with *integrations* (and optional *context*).

        Returns:
            bool: The return value of :func:`sentry_initialize`.
        """
        return sentry_initialize(integrations, context=context)

    def items(self, item_type: str) -> list[dict[str, Any]]:
        """Return the JSON payloads of all captured envelope items of *item_type* (e.g. ``"log"``).

        Calls :func:`sentry_sdk.flush` first so that buffered items arrive.
        """
        return self._payloads({item_type})

    @property
    def events(self) -> list[dict[str, Any]]:
        """Payloads of all captured ``event`` and ``transaction`` items, read after :func:`sentry_sdk.flush`."""
        return self._payloads(_EVENT_ITEM_TYPES)

    def _payloads(self, item_types: set[str]) -> list[dict[str, Any]]:
        sentry_sdk.flush()
        return [
            item.payload.json
            for envelope in self._transport.envelopes
            for item in envelope.items
            if item.type in item_types and item.payload.json is not None
        ]


@pytest.fixture
def sentry_capture(monkeypatch: pytest.MonkeyPatch) -> Generator[SentryCapture, None, None]:
    """Enable Sentry with a valid DSN and capture all envelopes in memory.

    Test-specific ``{PREFIX}SENTRY_*`` env vars must be set before ``start()`` because
    :func:`sentry_initialize` reads the settings when it runs.

    On teardown the client is closed, the isolation and current scopes are cleared and the
    global scope gets a :class:`~sentry_sdk.client.NonRecordingClient`, so the next test
    starts without an active client or user.

    Yields:
        SentryCapture: Handle to start Sentry and read the captured payloads.
    """
    monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
    monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
    transport = _CapturingTransport()
    with patch("sentry_sdk.client.make_transport", return_value=transport):
        yield SentryCapture(transport)
    sentry_sdk.get_client().close()
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()
    sentry_sdk.get_global_scope().set_client(NonRecordingClient())


@pytest.mark.integration
class TestSentryInitialize:
    """Behavioural tests for sentry_initialize()."""

    def test_sentry_initialize_returns_false_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when TESTPROJECT_SENTRY_ENABLED is not set (default False)."""
        monkeypatch.delenv(f"{_SENTRY_PREFIX}ENABLED", raising=False)
        result = sentry_initialize(integrations=None)
        assert result is False

    def test_sentry_initialize_returns_false_when_sdk_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when sentry_sdk is not importable (find_spec returns None)."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_SENTRY_PREFIX}DSN", _VALID_DSN)
        with patch("aignostics_foundry_core.sentry.find_spec", return_value=None):
            result = sentry_initialize(integrations=None)
        assert result is False

    def test_sentry_initialize_returns_true_when_enabled(self, sentry_capture: SentryCapture) -> None:
        """Returns True and events carry the release ``{name}@{version_full}`` when enabled with a valid DSN."""
        result = sentry_capture.start()
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        assert result is True
        (event,) = sentry_capture.events
        assert event["release"] == f"{TEST_PROJECT_NAME}@0.0.0"

    def test_sentry_initialize_returns_false_when_enabled_but_dsn_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when enabled but no DSN is configured."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}ENABLED", "true")
        monkeypatch.delenv(f"{_SENTRY_PREFIX}DSN", raising=False)
        result = sentry_initialize(integrations=None)
        assert result is False

    def test_sentry_initialize_uses_context_project_name(self, sentry_capture: SentryCapture) -> None:
        """The event release uses the project name of the given context."""
        ctx = make_context(name="other_project", version="1.2.3")
        sentry_capture.start(context=ctx)
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        assert event["release"] == "other_project@1.2.3"

    def test_sentry_initialize_uses_context_environment(self, sentry_capture: SentryCapture) -> None:
        """The event environment matches context.environment."""
        sentry_capture.start(context=make_context(environment="staging"))
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        assert event["environment"] == "staging"

    def test_sentry_initialize_uses_sentry_context_flags(self, sentry_capture: SentryCapture) -> None:
        """The ``aignx/base`` event context carries the runtime mode flags of the context."""
        sentry_capture.start(context=make_context(is_test=True))
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        base_context = event["contexts"]["aignx/base"]
        assert base_context["project_name"] == TEST_PROJECT_NAME
        assert base_context["test_mode"] is True


@pytest.mark.integration
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


@pytest.mark.integration
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

    def test_sentry_settings_uses_context_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SentrySettings reads env vars from the prefix supplied by FoundryContext."""
        set_context(make_context())
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}SENTRY_ENABLED", "true")
        settings = SentrySettings()  # pyright: ignore[reportCallIssue]
        assert settings.enabled is True


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
