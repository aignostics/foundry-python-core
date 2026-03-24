"""Tests for console module."""

import importlib
import sys

import pytest
from rich.console import Console

from aignostics_foundry_core.console import console

EXPECTED_THEME_KEYS = ["success", "info", "warning", "error", "debug", "logging.level.info"]


class TestConsole:
    """Tests for the themed rich console module."""

    @pytest.mark.unit
    def test_console_is_console_instance(self) -> None:
        """Module-level console is a rich.console.Console instance."""
        assert isinstance(console, Console)

    @pytest.mark.unit
    @pytest.mark.sequential
    def test_console_default_width(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Module-level console has Rich's default width (80) when env var is not set."""
        monkeypatch.delenv("AIGNOSTICS_CONSOLE_WIDTH", raising=False)
        reloaded = importlib.reload(sys.modules["aignostics_foundry_core.console"])
        assert reloaded.console.width == 80

    @pytest.mark.unit
    @pytest.mark.sequential
    def test_console_custom_width(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Module-level console uses width from AIGNOSTICS_CONSOLE_WIDTH env var."""
        monkeypatch.setenv("AIGNOSTICS_CONSOLE_WIDTH", "100")
        reloaded = importlib.reload(sys.modules["aignostics_foundry_core.console"])
        assert reloaded.console.width == 100

    @pytest.mark.unit
    def test_console_theme_contains_expected_keys(self) -> None:
        """Console can render text with all required theme style names without error."""
        for key in EXPECTED_THEME_KEYS:
            style = console.get_style(key)
            assert style is not None, f"Theme style '{key}' should be defined on the console."
