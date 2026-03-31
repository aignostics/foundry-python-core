"""Tests for the settings module."""

import os
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import RootModel, SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from aignostics_foundry_core.settings import (
    UNHIDE_SENSITIVE_INFO,
    OpaqueSettings,
    load_settings,
    strip_to_none_before_validator,
)

_SECRET_VALUE = "sensitive"  # noqa: S105
_MASKED_VALUE = "**********"
_AIGNOSTICS_FOUNDRY_CORE_CONSOLE = "aignostics_foundry_core.console"


class _TheTestSettings(OpaqueSettings):
    """Test settings class."""

    test_value: str = "default"
    secret_value: SecretStr | None = None
    required_value: str


class _TheTestSettingsWithEnvPrefix(OpaqueSettings):
    """Test settings class with an environment prefix."""

    model_config = SettingsConfigDict(env_prefix="TEST_")

    value: str


def _make_info(context: dict[str, Any] | None) -> MagicMock:
    """Create a mock FieldSerializationInfo with the given context."""
    info = MagicMock()
    info.context = context
    return info


class TestStripToNoneBeforeValidator:
    """Tests for strip_to_none_before_validator."""

    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        """Test that None is returned when None is passed."""
        assert strip_to_none_before_validator(None) is None

    @pytest.mark.unit
    def test_empty_string_returns_none(self) -> None:
        """Test that None is returned when an empty string is passed."""
        assert strip_to_none_before_validator("") is None

    @pytest.mark.unit
    def test_whitespace_returns_none(self) -> None:
        """Test that None is returned when a whitespace string is passed."""
        assert strip_to_none_before_validator("  \t\n  ") is None

    @pytest.mark.unit
    def test_valid_string_returns_stripped(self) -> None:
        """Test that a stripped string is returned when a valid string is passed."""
        assert strip_to_none_before_validator("  test  ") == "test"


class TestOpaqueSettings:
    """Tests for OpaqueSettings static serializers."""

    @pytest.mark.unit
    def test_serialize_sensitive_info_unhide_true(self) -> None:
        """Test that sensitive info is revealed when unhide_sensitive_info is True."""
        secret = SecretStr(_SECRET_VALUE)
        result = OpaqueSettings.serialize_sensitive_info(secret, _make_info({UNHIDE_SENSITIVE_INFO: True}))
        assert result == _SECRET_VALUE

    @pytest.mark.unit
    def test_serialize_sensitive_info_unhide_false(self) -> None:
        """Test that sensitive info is hidden when unhide_sensitive_info is False."""
        secret = SecretStr(_SECRET_VALUE)
        result = OpaqueSettings.serialize_sensitive_info(secret, _make_info({UNHIDE_SENSITIVE_INFO: False}))
        assert result == _MASKED_VALUE

    @pytest.mark.unit
    def test_serialize_sensitive_info_empty_secret(self) -> None:
        """Test that None is returned when the SecretStr is empty."""
        result = OpaqueSettings.serialize_sensitive_info(SecretStr(""), _make_info({}))
        assert result is None

    @pytest.mark.unit
    def test_serialize_sensitive_info_none_input(self) -> None:
        """Test that None is returned when input_value is None."""
        result = OpaqueSettings.serialize_sensitive_info(cast("SecretStr", None), _make_info({}))
        assert result is None

    @pytest.mark.unit
    def test_serialize_sensitive_info_no_context(self) -> None:
        """Test that sensitive info is hidden when no context is provided."""
        secret = SecretStr(_SECRET_VALUE)
        result = OpaqueSettings.serialize_sensitive_info(secret, _make_info(None))
        assert result == _MASKED_VALUE

    @pytest.mark.unit
    def test_serialize_path_resolve(self, tmp_path: Path) -> None:
        """Test that Path is resolved correctly."""
        test_path = tmp_path / "test_file.txt"
        test_path.touch()
        result = OpaqueSettings.serialize_path_resolve(test_path, _make_info(None))
        assert result == str(test_path.resolve())

    @pytest.mark.unit
    def test_serialize_path_resolve_none(self) -> None:
        """Test that None is returned when Path is None."""
        result = OpaqueSettings.serialize_path_resolve(cast("Path", None), _make_info(None))
        assert result is None

    @pytest.mark.unit
    def test_serialize_path_resolve_empty_path(self) -> None:
        """Test that None is returned for Path("") rather than resolving to CWD."""
        result = OpaqueSettings.serialize_path_resolve(Path(), _make_info(None))
        assert result is None


class TestLoadSettings:
    """Tests for load_settings."""

    @pytest.mark.unit
    @patch.dict(os.environ, {"REQUIRED_VALUE": "test_value"})
    def test_load_settings_success(self) -> None:
        """Test successful settings loading."""
        settings = load_settings(_TheTestSettings)
        assert settings.test_value == "default"
        assert settings.required_value == "test_value"

    @pytest.mark.unit
    @patch.dict(os.environ, {"TEST_VALUE": "prefixed_value"})
    def test_load_settings_with_env_prefix(self) -> None:
        """Test that settings with environment prefix work correctly."""
        settings = load_settings(_TheTestSettingsWithEnvPrefix)
        assert settings.value == "prefixed_value"

    @pytest.mark.unit
    @patch("sys.exit")
    @patch("aignostics_foundry_core.console.console.print")
    def test_load_settings_validation_error_exits(self, mock_console_print: MagicMock, mock_exit: MagicMock) -> None:
        """Test that validation error prints a Rich Panel and calls sys.exit(78)."""
        from rich.panel import Panel

        load_settings(_TheTestSettings)

        mock_exit.assert_called_once_with(78)
        assert mock_console_print.call_count == 1
        panel_arg = mock_console_print.call_args[0][0]
        assert isinstance(panel_arg, Panel)

    @pytest.mark.unit
    def test_load_settings_success_does_not_import_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful load must not trigger the console import (lazy-import check)."""
        import sys

        monkeypatch.setenv("REQUIRED_VALUE", "test_value")
        # Temporarily remove the console module so we can detect if it gets imported.
        console_module = sys.modules.pop(_AIGNOSTICS_FOUNDRY_CORE_CONSOLE, None)
        try:
            load_settings(_TheTestSettings)
            assert _AIGNOSTICS_FOUNDRY_CORE_CONSOLE not in sys.modules
        finally:
            if console_module is not None:
                sys.modules[_AIGNOSTICS_FOUNDRY_CORE_CONSOLE] = console_module

    @pytest.mark.unit
    @patch("sys.exit")
    @patch("aignostics_foundry_core.console.console.print")
    def test_load_settings_invalid_prints_panel_and_exits(
        self, mock_console_print: MagicMock, mock_exit: MagicMock
    ) -> None:
        """Lazy-imported console still renders a Rich Panel on ValidationError."""
        from rich.panel import Panel

        load_settings(_TheTestSettings)  # missing REQUIRED_VALUE → ValidationError

        mock_exit.assert_called_once_with(78)
        assert mock_console_print.call_count == 1
        panel_arg = mock_console_print.call_args[0][0]
        assert isinstance(panel_arg, Panel)

    @pytest.mark.unit
    @patch("sys.exit")
    @patch("aignostics_foundry_core.console.console.print")
    def test_load_settings_validation_error_integer_loc(
        self, mock_console_print: MagicMock, mock_exit: MagicMock
    ) -> None:
        """Test that integer loc[0] falls back to the model prefix instead of "PREFIX_0"."""
        # RootModel[list[int]] produces loc=(0,) where loc[0] is an integer
        int_loc_error: ValidationError | None = None
        try:
            RootModel[list[int]].model_validate(["not_an_int"])
        except ValidationError as e:
            int_loc_error = e

        assert int_loc_error is not None
        assert isinstance(int_loc_error.errors()[0]["loc"][0], int)

        with patch.object(_TheTestSettingsWithEnvPrefix, "__new__", side_effect=int_loc_error):
            load_settings(_TheTestSettingsWithEnvPrefix)

        mock_exit.assert_called_once_with(78)
        panel_arg = mock_console_print.call_args[0][0]
        panel_text = str(panel_arg.renderable)
        assert "TEST_0" not in panel_text
        assert "• TEST:" in panel_text
