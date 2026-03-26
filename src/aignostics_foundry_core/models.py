"""Common models reusable across Foundry components."""

from enum import StrEnum


class OutputFormat(StrEnum):
    """Supported output formats for CLI and API responses.

    Usage:
        format = OutputFormat.YAML
        print(f"Using {format} format")
    """

    YAML = "yaml"
    JSON = "json"
