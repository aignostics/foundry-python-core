"""Themed rich console."""

import os

from rich.console import Console
from rich.theme import Theme


def _get_console() -> Console:
    """Get a themed rich console.

    The console width is controlled by ``{env_prefix}CONSOLE_WIDTH`` when a
    ``FoundryContext`` is available (e.g. ``MYPROJECT_CONSOLE_WIDTH``).
    If no context has been set the width defaults to Rich's auto-detection.

    Returns:
        Console: The themed rich console.
    """
    try:
        from aignostics_foundry_core.foundry import get_context  # noqa: PLC0415

        env_var = f"{get_context().env_prefix}CONSOLE_WIDTH"
        width: int | None = int(os.environ.get(env_var, "0")) or None
    except RuntimeError:
        width = None

    return Console(
        theme=Theme({
            "logging.level.info": "purple4",
            "debug": "light_cyan3",
            "success": "green",
            "info": "purple4",
            "warning": "yellow1",
            "error": "red1",
        }),
        width=width,
        legacy_windows=False,  # Modern Windows (10+) doesn't need width adjustment
    )


console = _get_console()
