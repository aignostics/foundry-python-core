"""Tests for OutputFormat enum."""

import pytest

from aignostics_foundry_core.models import OutputFormat


class TestOutputFormat:
    """Tests for the OutputFormat StrEnum."""

    @pytest.mark.unit
    def test_output_format_yaml_value(self) -> None:
        """OutputFormat.YAML has the string value 'yaml'."""
        assert OutputFormat.YAML == "yaml"

    @pytest.mark.unit
    def test_output_format_json_value(self) -> None:
        """OutputFormat.JSON has the string value 'json'."""
        assert OutputFormat.JSON == "json"

    @pytest.mark.unit
    def test_output_format_is_str(self) -> None:
        """Every OutputFormat member is usable as a plain str."""
        for member in OutputFormat:
            assert isinstance(member, str)
            assert member == member.value
