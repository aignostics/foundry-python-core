"""Tests for console module."""

import importlib
import sys

import pytest
from rich.console import Console

from aignostics_foundry_core.console import console
from aignostics_foundry_core.foundry import set_context
from tests.conftest import make_context

EXPECTED_THEME_KEYS = ["success", "info", "warning", "error", "debug", "logging.level.info"]
CUSTOM_WIDTH = "120"
EXPECTED_CUSTOM_WIDTH = 120
CONSOLE_MODULE = "aignostics_foundry_core.console"


class TestConsole:
    """Tests for the themed rich console module."""

    @pytest.mark.unit
    def test_console_is_console_instance(self) -> None:
        """Module-level console is a rich.console.Console instance."""
        assert isinstance(console, Console)

    @pytest.mark.unit
    @pytest.mark.sequential
    def test_console_default_width(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Module-level console has Rich's default width (80) when no context is set."""
        reloaded = importlib.reload(sys.modules[CONSOLE_MODULE])
        assert reloaded.console.width == 80

    @pytest.mark.unit
    @pytest.mark.sequential
    def test_console_width_uses_env_prefix_from_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Console width is read from {env_prefix}CONSOLE_WIDTH when a context is set."""
        ctx = make_context()
        set_context(ctx)
        monkeypatch.setenv(f"{ctx.env_prefix}CONSOLE_WIDTH", CUSTOM_WIDTH)
        reloaded = importlib.reload(sys.modules[CONSOLE_MODULE])
        assert reloaded.console.width == EXPECTED_CUSTOM_WIDTH

    @pytest.mark.unit
    @pytest.mark.sequential
    def test_console_width_is_auto_when_no_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Console width defaults to Rich's auto-detection (80 in non-TTY) when no context is set."""
        reloaded = importlib.reload(sys.modules[CONSOLE_MODULE])
        assert reloaded.console.width == 80

    @pytest.mark.unit
    def test_console_theme_contains_expected_keys(self) -> None:
        """Console can render text with all required theme style names without error."""
        for key in EXPECTED_THEME_KEYS:
            style = console.get_style(key)
            assert style is not None, f"Theme style '{key}' should be defined on the console."
