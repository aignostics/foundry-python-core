"""Utilities around Pydantic settings."""

import sys
from pathlib import Path
from typing import TypeVar

from pydantic import FieldSerializationInfo, SecretStr, ValidationError
from pydantic_settings import BaseSettings
from rich.panel import Panel
from rich.text import Text

from aignostics_foundry_core.console import console

_T = TypeVar("_T", bound=BaseSettings)

UNHIDE_SENSITIVE_INFO = "unhide_sensitive_info"


def strip_to_none_before_validator(v: str | None) -> str | None:
    """Strip whitespace and return None for empty strings.

    Args:
        v: The string to process, or None.

    Returns:
        None if the input is None or whitespace-only, otherwise the stripped string.
    """
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    return v


class OpaqueSettings(BaseSettings):
    """Base settings class with secret masking and path resolution serializers."""

    @staticmethod
    def serialize_sensitive_info(input_value: SecretStr | None, info: FieldSerializationInfo) -> str | None:
        """Serialize a SecretStr, masking it unless context requests unhiding.

        Args:
            input_value: The secret value to serialize.
            info: Pydantic serialization info, may carry context.

        Returns:
            None for empty secrets, the secret value if unhide is requested,
            otherwise the masked representation.
        """
        if not input_value:
            return None
        if info.context and info.context.get(UNHIDE_SENSITIVE_INFO, False):
            return input_value.get_secret_value()
        return str(input_value)

    @staticmethod
    def serialize_path_resolve(input_value: Path | None, _info: FieldSerializationInfo) -> str | None:
        """Serialize a Path by resolving it to an absolute string.

        Args:
            input_value: The path to resolve.
            _info: Pydantic serialization info (unused).

        Returns:
            None if input is `None` or has no path components (e.g. empty string),
            otherwise the resolved absolute path string.
        """
        if input_value is None or not input_value.parts:
            return None
        return str(input_value.resolve())


def load_settings(settings_class: type[_T]) -> _T:
    """Load settings with error handling and nice formatting.

    Args:
        settings_class: The Pydantic settings class to instantiate.

    Returns:
        Instance of the settings class.

    Raises:
        SystemExit: If settings validation fails (exit code 78).
    """
    try:
        return settings_class()
    except ValidationError as e:
        errors = e.errors()
        text = Text()
        text.append(
            "Validation error(s): \n\n",
            style="debug",
        )

        prefix = settings_class.model_config.get("env_prefix", "")
        for error in errors:
            if error["loc"] and isinstance(error["loc"][0], str):
                env_var = f"{prefix}{error['loc'][0]}".upper()
            else:
                env_var = prefix.rstrip("_").upper()
            text.append(f"• {env_var}", style="yellow bold")
            text.append(f": {error['msg']}\n")

        text.append(
            "\nCheck settings defined in the process environment and in file ",
            style="info",
        )
        env_file = str(settings_class.model_config.get("env_file", ".env") or ".env")
        text.append(
            str(Path.cwd() / env_file),
            style="bold blue underline",
        )

        console.print(
            Panel(
                text,
                title="Configuration invalid!",
                border_style="error",
            ),
        )
        sys.exit(78)
