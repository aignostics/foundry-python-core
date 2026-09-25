"""Tests for aignostics_foundry_core.boot."""

from __future__ import annotations

import logging
import os
import ssl
import sys
import types
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import certifi
import pytest

import aignostics_foundry_core.boot as boot_mod
from tests.conftest import TEST_PROJECT_NAME, TEST_PROJECT_PREFIX, make_context

if TYPE_CHECKING:
    from tests.aignostics_foundry_core.conftest import OtlpLogCapture

_OTHER_PROJECT = "otherapp"
_REJECTED_LOGGER = "noisy.lib"
_REJECTED_MARKER = "boot_otlp_rejected_marker_4c7d"
_KEPT_MARKER = "boot_otlp_kept_marker_8f2b"


@pytest.mark.unit
def test_boot_can_be_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """boot() runs without raising when all heavy deps are mocked."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    boot_mod.boot(context=make_context(), sentry_integrations=None)  # must not raise


@pytest.mark.unit
def test_boot_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling boot() twice only invokes logging_initialize once."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)

    mock_logging = MagicMock()
    monkeypatch.setattr(boot_mod, "logging_initialize", mock_logging)
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    boot_mod.boot(context=make_context(), sentry_integrations=None)
    boot_mod.boot(context=make_context(), sentry_integrations=None)

    assert mock_logging.call_count == 1


@pytest.mark.unit
def test_parse_env_args_injects_matching_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """--env args matching the project_name prefix are injected into os.environ and removed from sys.argv."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)
    monkeypatch.delitem(os.environ, f"{TEST_PROJECT_PREFIX}FOO", raising=False)
    monkeypatch.setattr(sys, "argv", ["script.py", "--env", f"{TEST_PROJECT_PREFIX}FOO=bar"])

    boot_mod.boot(context=make_context(), sentry_integrations=None)

    assert os.environ.get(f"{TEST_PROJECT_PREFIX}FOO") == "bar"
    assert "--env" not in sys.argv
    assert f"{TEST_PROJECT_PREFIX}FOO=bar" not in sys.argv


@pytest.mark.unit
def test_boot_amends_ssl_trust_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """boot() sets SSL_CERT_FILE when certifi is available and no system CA bundle is found."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    # Disable truststore to isolate the certifi code path
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.delitem(os.environ, "SSL_CERT_FILE", raising=False)

    # Simulate a system with no default CA bundle
    mock_paths = types.SimpleNamespace(cafile=None)
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: mock_paths)

    boot_mod.boot(context=make_context(), sentry_integrations=None)

    assert "SSL_CERT_FILE" in os.environ


@pytest.mark.unit
def test_boot_uses_global_context_when_none_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    """boot() falls back to the process-level context when no context argument is given."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    mock_logging = MagicMock()
    monkeypatch.setattr(boot_mod, "logging_initialize", mock_logging)
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    boot_mod.boot(sentry_integrations=None)

    call_ctx = mock_logging.call_args.kwargs["context"]
    assert call_ctx.name == TEST_PROJECT_NAME


@pytest.mark.unit
def test_boot_explicit_context_overrides_global(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit context passed to boot() takes precedence over the global context."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    mock_sentry = MagicMock(return_value=False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", mock_sentry)
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    explicit_ctx = make_context(_OTHER_PROJECT)
    boot_mod.boot(context=explicit_ctx, sentry_integrations=None)

    call_ctx = mock_sentry.call_args.kwargs["context"]
    assert call_ctx.name == _OTHER_PROJECT


@pytest.mark.unit
def test_boot_forwards_otel_instrumentors_to_otel_initialize(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit otel_instrumentors list is forwarded to otel_initialize()."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    mock_otel = MagicMock(return_value=False)
    monkeypatch.setattr(boot_mod, "otel_initialize", mock_otel)
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    sentinel_instrumentors = [MagicMock()]
    boot_mod.boot(
        context=make_context(),
        sentry_integrations=None,
        otel_instrumentors=sentinel_instrumentors,  # pyright: ignore[reportArgumentType]
    )

    assert mock_otel.call_args.kwargs["instrumentors"] is sentinel_instrumentors


@pytest.mark.integration
def test_boot_applies_log_filter_to_otlp_sink(
    monkeypatch: pytest.MonkeyPatch, otlp_log_exporter: OtlpLogCapture
) -> None:
    """boot() gives its log_filter to the OTLP log sink, which then drops the rejected records."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(sys, "argv", ["boot_test"])
    # Keep boot() from changing the process-wide SSL setup and SSL_CERT_FILE.
    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())

    with patch("truststore.inject_into_ssl"):
        boot_mod.boot(
            context=make_context(),
            sentry_integrations=None,
            log_filter=lambda record: record["name"] != _REJECTED_LOGGER,
        )

    logging.getLogger(_REJECTED_LOGGER).warning(_REJECTED_MARKER)
    logging.getLogger(TEST_PROJECT_NAME).warning(_KEPT_MARKER)

    bodies = otlp_log_exporter.bodies
    assert _KEPT_MARKER in bodies
    assert _REJECTED_MARKER not in bodies
