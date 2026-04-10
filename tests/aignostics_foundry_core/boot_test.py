"""Tests for aignostics_foundry_core.boot."""

from __future__ import annotations

import os
import ssl
import sys
import types
from unittest.mock import MagicMock

import pytest

import aignostics_foundry_core.boot as boot_mod
from tests.conftest import TEST_PROJECT_NAME, TEST_PROJECT_PREFIX, make_context

_OTHER_PROJECT = "otherapp"


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
