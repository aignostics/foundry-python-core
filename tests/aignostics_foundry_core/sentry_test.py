"""Tests for aignostics_foundry_core.sentry."""

import json
from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import httpx
import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
_AUTH0_USER = "auth0|x"
_AUTH0_ORG_ID = "org_123"
_ROLE_CLAIM = "https://example.com/role"
_FULL_AUTH0_CLAIMS: dict[str, Any] = {
    "sub": _AUTH0_USER,
    "email": "user@example.com",
    "name": "Test User",
    "nickname": "tester",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://example.com/avatar.png",
    "org_id": _AUTH0_ORG_ID,
    "org_name": "Example Org",
    "updated_at": "2026-01-01T00:00:00.000Z",
}
_SENTRY_PREFIX = f"{TEST_PROJECT_PREFIX}SENTRY_"
_PROBE_MESSAGE = "probe"
_EVENT_ITEM_TYPES = {"event", "transaction"}
_SECRET_LOCAL_NAME = "client_secret"  # ruff: ignore[hardcoded-password-string]
_SECRET_LOCAL_VALUE = "s3cr3t"  # ruff: ignore[hardcoded-password-string]
_FAILING_ROUTE = "/fail"
_SIGNED_URL_QUERY = "sig=secret"
_SIGNED_URL_MARKER = "sig="
_SIGNED_BLOB_URL = f"https://storage.example.com/blob?{_SIGNED_URL_QUERY}"
_HTTP_QUERY_KEY = "http.query"
_HTTP_FRAGMENT_KEY = "http.fragment"
_HTTPLIB_CATEGORY = "httplib"


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


def _fail_with_secret_local() -> None:
    """Raise from a frame that holds a secret in a local variable.

    Raises:
        ValueError: Always.
    """
    client_secret = _SECRET_LOCAL_VALUE
    msg = f"login failed for a secret of length {len(client_secret)}"
    raise ValueError(msg)


def _capture_exception_with_secret_local() -> None:
    """Call :func:`_fail_with_secret_local` and send the exception to Sentry."""
    try:
        _fail_with_secret_local()
    except ValueError:
        sentry_sdk.capture_exception()


def _exception_frames(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all stack frames of all exceptions in *event*."""
    return [frame for value in event["exception"]["values"] for frame in value["stacktrace"]["frames"]]


def _post_secret_to_failing_fastapi_route() -> None:
    """Send a JSON body with a secret to a FastAPI route that raises :class:`RuntimeError`."""
    app = FastAPI()

    @app.post(_FAILING_ROUTE)
    def fail() -> None:  # pyright: ignore[reportUnusedFunction]
        msg = "request failed"
        raise RuntimeError(msg)

    TestClient(app, raise_server_exceptions=False).post(_FAILING_ROUTE, json={_SECRET_LOCAL_NAME: _SECRET_LOCAL_VALUE})


def _get_signed_blob_url() -> None:
    """Send a GET with a signed query string through an :class:`httpx.Client` on a mock transport."""
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as client:
        client.get(_SIGNED_BLOB_URL)


def _breadcrumbs(event: dict[str, Any], category: str) -> list[dict[str, Any]]:
    """Return the breadcrumbs of *event* that have *category*."""
    return [crumb for crumb in event["breadcrumbs"]["values"] if crumb.get("category") == category]


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
class TestSentryDataCollection:
    """Tests for the data that Sentry events carry with default and opt-in settings."""

    def test_exception_event_has_no_frame_vars_by_default(self, sentry_capture: SentryCapture) -> None:
        """No stack frame of an exception event carries local variables at default settings."""
        sentry_capture.start()
        _capture_exception_with_secret_local()

        (event,) = sentry_capture.events
        frames = _exception_frames(event)
        assert frames
        assert all("vars" not in frame for frame in frames)

    def test_exception_event_has_frame_vars_when_enabled(
        self, sentry_capture: SentryCapture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The raising frame carries its local variables when INCLUDE_LOCAL_VARIABLES is true."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}INCLUDE_LOCAL_VARIABLES", "true")
        sentry_capture.start()
        _capture_exception_with_secret_local()

        (event,) = sentry_capture.events
        (frame,) = [f for f in _exception_frames(event) if f["function"] == _fail_with_secret_local.__name__]
        assert _SECRET_LOCAL_NAME in frame["vars"]

    def test_failed_fastapi_request_event_has_no_request_data_by_default(self, sentry_capture: SentryCapture) -> None:
        """The event of a failed FastAPI request carries request info but no request body at default settings.

        The SDK keeps the ``data`` key with an empty value and marks it as removed in ``_meta``.
        The request can also produce a sampled transaction, so the error event is read by its item
        type, and the secret is looked for in every captured payload.
        """
        sentry_capture.start()
        _post_secret_to_failing_fastapi_route()

        (event,) = sentry_capture.items("event")
        assert "request" in event
        assert not event["request"].get("data")
        assert _SECRET_LOCAL_VALUE not in json.dumps(sentry_capture.events)

    def test_failed_fastapi_request_event_has_request_data_when_always(
        self, sentry_capture: SentryCapture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The event of a failed FastAPI request carries the JSON body when MAX_REQUEST_BODY_SIZE is always."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}MAX_REQUEST_BODY_SIZE", "always")
        sentry_capture.start()
        _post_secret_to_failing_fastapi_route()

        (event,) = sentry_capture.items("event")
        assert event["request"]["data"][_SECRET_LOCAL_NAME] == _SECRET_LOCAL_VALUE


@pytest.mark.integration
class TestSentryHttpData:
    """Tests for the URL data that HTTP breadcrumbs and spans carry to Sentry."""

    def test_http_breadcrumb_has_no_query_string(self, sentry_capture: SentryCapture) -> None:
        """The ``httplib`` breadcrumb of an httpx request carries no query string."""
        sentry_capture.start()
        _get_signed_blob_url()
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.items("event")
        (crumb,) = _breadcrumbs(event, _HTTPLIB_CATEGORY)
        assert _HTTP_QUERY_KEY not in crumb["data"]
        assert _SIGNED_URL_MARKER not in crumb["data"]["url"]

    def test_manual_http_breadcrumb_with_query_in_url_is_stripped(self, sentry_capture: SentryCapture) -> None:
        """An HTTP breadcrumb added by hand loses the query keys and the query of its URL."""
        sentry_capture.start()
        sentry_sdk.add_breadcrumb(
            type="http",
            category=_HTTPLIB_CATEGORY,
            data={"url": _SIGNED_BLOB_URL + "#part", _HTTP_QUERY_KEY: _SIGNED_URL_QUERY, _HTTP_FRAGMENT_KEY: "part"},
        )
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.items("event")
        (crumb,) = _breadcrumbs(event, _HTTPLIB_CATEGORY)
        assert crumb["data"] == {"url": "https://storage.example.com/blob"}

    def test_non_http_breadcrumb_is_unchanged(self, sentry_capture: SentryCapture) -> None:
        """A breadcrumb of another type and category keeps its data, also URL-like keys."""
        data = {"url": _SIGNED_BLOB_URL, _HTTP_QUERY_KEY: _SIGNED_URL_QUERY}
        sentry_capture.start()
        sentry_sdk.add_breadcrumb(type="default", category="app", data=data)
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.items("event")
        (crumb,) = _breadcrumbs(event, "app")
        assert crumb["data"] == data

    def test_transaction_span_has_no_query_string(
        self, sentry_capture: SentryCapture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The HTTP client span of an httpx request inside a transaction carries no query string."""
        monkeypatch.setenv(f"{_SENTRY_PREFIX}TRACES_SAMPLE_RATE", "1.0")
        sentry_capture.start()
        with sentry_sdk.start_transaction(name=_PROBE_MESSAGE):
            _get_signed_blob_url()

        (transaction,) = sentry_capture.items("transaction")
        http_spans = [span for span in transaction["spans"] if span["op"] == "http.client"]
        assert http_spans
        assert all(_HTTP_QUERY_KEY not in span["data"] for span in http_spans)
        assert _SIGNED_URL_MARKER not in json.dumps(transaction)


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


@pytest.mark.integration
class TestSetSentryUser:
    """Behavioural tests for set_sentry_user()."""

    def test_set_sentry_user_sends_only_id_and_org_id(self, sentry_capture: SentryCapture) -> None:
        """Of a full Auth0 claim set, only ``sub`` (as ``id``) and ``org_id`` get to the event user."""
        sentry_capture.start()
        set_sentry_user(_FULL_AUTH0_CLAIMS)
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        assert event["user"] == {"id": _AUTH0_USER, "org_id": _AUTH0_ORG_ID}

    def test_set_sentry_user_includes_role_from_claim(self, sentry_capture: SentryCapture) -> None:
        """The event user carries the value of the custom role claim when role_claim is provided."""
        sentry_capture.start()
        set_sentry_user({**_FULL_AUTH0_CLAIMS, _ROLE_CLAIM: "admin"}, role_claim=_ROLE_CLAIM)
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        assert event["user"]["role"] == "admin"

    def test_set_sentry_user_none_clears_user(self, sentry_capture: SentryCapture) -> None:
        """set_sentry_user(None) removes a previously set user from later events."""
        sentry_capture.start()
        set_sentry_user(_FULL_AUTH0_CLAIMS)
        set_sentry_user(None)
        sentry_sdk.capture_message(_PROBE_MESSAGE)

        (event,) = sentry_capture.events
        assert "user" not in event

    def test_set_sentry_user_does_nothing_when_sdk_absent(self) -> None:
        """set_sentry_user is a no-op when sentry_sdk is not importable."""
        with patch("aignostics_foundry_core.sentry.find_spec", return_value=None):
            # Should not raise even though sentry_sdk is unavailable
            set_sentry_user({"sub": _AUTH0_USER})
