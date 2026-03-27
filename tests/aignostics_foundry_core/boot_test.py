"""Tests for aignostics_foundry_core.boot."""

from __future__ import annotations

import os
import ssl
import sys
import types
from unittest.mock import MagicMock

import pytest

import aignostics_foundry_core.boot as boot_mod
from tests.conftest import make_context

_PROJECT = "testapp"


@pytest.mark.unit
def test_boot_can_be_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """boot() runs without raising when all heavy deps are mocked."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    boot_mod.boot(make_context(_PROJECT), sentry_integrations=None)  # must not raise


@pytest.mark.unit
def test_boot_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling boot() twice only invokes logging_initialize once."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)

    mock_logging = MagicMock()
    monkeypatch.setattr(boot_mod, "logging_initialize", mock_logging)
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)

    boot_mod.boot(make_context(_PROJECT), sentry_integrations=None)
    boot_mod.boot(make_context(_PROJECT), sentry_integrations=None)

    assert mock_logging.call_count == 1


@pytest.mark.unit
def test_parse_env_args_injects_matching_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """--env args matching the project_name prefix are injected into os.environ and removed from sys.argv."""
    monkeypatch.setattr(boot_mod, "_boot_called", False)
    monkeypatch.setattr(boot_mod, "logging_initialize", MagicMock())
    monkeypatch.setattr(boot_mod, "sentry_initialize", MagicMock(return_value=False))
    monkeypatch.setattr(boot_mod, "truststore", None)
    monkeypatch.setattr(boot_mod, "certifi", None)
    monkeypatch.delitem(os.environ, "TESTAPP_FOO", raising=False)
    monkeypatch.setattr(sys, "argv", ["script.py", "--env", "TESTAPP_FOO=bar"])

    boot_mod.boot(make_context(_PROJECT), sentry_integrations=None)

    assert os.environ.get("TESTAPP_FOO") == "bar"
    assert "--env" not in sys.argv
    assert "TESTAPP_FOO=bar" not in sys.argv


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

    boot_mod.boot(make_context(_PROJECT), sentry_integrations=None)

    assert "SSL_CERT_FILE" in os.environ
