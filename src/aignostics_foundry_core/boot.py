"""Boot sequence for Foundry-based applications.

Provides a single :func:`boot` entry-point that initialises logging, SSL trust
chain, and optional Sentry integration in the correct order.  All
project-specific metadata is passed as explicit parameters so the function is
reusable across any project without hard-coded constants.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import ssl
import sys
from typing import TYPE_CHECKING

from loguru import logger

from aignostics_foundry_core.log import logging_initialize
from aignostics_foundry_core.process import get_process_info
from aignostics_foundry_core.sentry import sentry_initialize

# Optional SSL certificate modules - gracefully degrade if not available
try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

try:
    import truststore  # pyright: ignore[reportMissingImports]
except ImportError:
    truststore = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Callable

    from loguru import Record
    from sentry_sdk.integrations import Integration

    from aignostics_foundry_core.foundry import FoundryContext

_boot_called = False


def boot(
    context: FoundryContext,
    sentry_integrations: list[Integration] | None,
    log_filter: Callable[[Record], bool] | None = None,
    show_cmdline: bool = True,
) -> None:
    """Boot the application or library.

    Runs the full initialisation sequence exactly once per process.  Subsequent
    calls are silent no-ops, making it safe to call from multiple entry-points.

    The sequence is:

    1. Parse ``--env``/``-e`` CLI arguments and inject matching env vars.
    2. Initialise loguru logging via :func:`~aignostics_foundry_core.log.logging_initialize`.
    3. Amend the SSL trust chain with *truststore* and *certifi*.
    4. Initialise Sentry via :func:`~aignostics_foundry_core.sentry.sentry_initialize`.
    5. Log a boot message with version, PID, and process information.
    6. Register an atexit shutdown message.

    Args:
        context: :class:`~aignostics_foundry_core.foundry.FoundryContext` providing
            project name, version, environment, and runtime mode flags for logging,
            Sentry, and ``--env`` argument injection.
        sentry_integrations: List of Sentry SDK integrations to register, or
            ``None`` to skip Sentry initialisation.
        log_filter: Optional loguru filter callable forwarded to
            :func:`~aignostics_foundry_core.log.logging_initialize`.
        show_cmdline: Whether to include the process command line in the
            boot log message (default: ``True``).
    """
    global _boot_called  # noqa: PLW0603
    if _boot_called:
        return
    _boot_called = True

    _parse_env_args(context.name)
    logging_initialize(filter_func=log_filter, context=context)
    _amend_ssl_trust_chain()
    sentry_initialize(
        integrations=sentry_integrations,
        context=context,
    )
    _log_boot_message(
        project_name=context.name,
        version=context.version,
        is_library_mode=context.is_library,
        show_cmdline=show_cmdline,
        context=context,
    )
    _register_shutdown_message(project_name=context.name, version=context.version)
    logger.trace("Boot sequence completed successfully.")


def _parse_env_args(project_name: str) -> None:
    """Parse ``--env``/``-e`` arguments from the command line.

    Arguments of the form ``--env KEY=VALUE`` where ``KEY`` starts with the
    upper-cased project name prefix are added to :data:`os.environ`.  The
    processed arguments are then removed from :data:`sys.argv` so that CLI
    parsers (e.g. Typer) do not receive unknown flags.

    Args:
        project_name: Project name used to build the env-var prefix.
    """
    i = 1  # Start after script name
    to_remove: list[int] = []
    prefix = f"{project_name.upper()}_"

    while i < len(sys.argv):
        current_arg = sys.argv[i]

        # Handle "--env KEY=VALUE" or "-e KEY=VALUE" (two separate arguments)
        if (current_arg in {"--env", "-e"}) and i + 1 < len(sys.argv):
            key_value = sys.argv[i + 1]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                if key.startswith(prefix):
                    os.environ[key] = value.strip("\"'")
                to_remove.extend([i, i + 1])
                i += 2
                continue

        i += 1

    # Remove processed arguments from sys.argv in reverse order
    for index in sorted(to_remove, reverse=True):
        del sys.argv[index]


def _amend_ssl_trust_chain() -> None:
    """Amend the SSL trust chain with *truststore* and *certifi* if available."""
    if truststore is not None:
        truststore.inject_into_ssl()
        logger.trace("Injected truststore into SSL ...")
    else:
        logger.warning("Module truststore not available, injection skipped.")  # type: ignore[unreachable]

    cafile: str | None = ssl.get_default_verify_paths().cafile or None  # pyright: ignore[reportUnnecessaryComparison]
    if cafile is None and os.environ.get("SSL_CERT_FILE") is None:
        if certifi is not None:
            os.environ["SSL_CERT_FILE"] = certifi.where()
            logger.trace("SSL_CERT_FILE set to certifi bundle path.")
        else:
            logger.warning("Module certifi not available, SSL_CERT_FILE configuration skipped.")  # type: ignore[unreachable]
    else:
        logger.trace(
            "Use of certifi skipped, given CA File is {}, SSL_CERT_FILE is {}.".format(
                cafile,
                os.environ.get("SSL_CERT_FILE"),
            )
        )


def _log_boot_message(
    project_name: str,
    version: str,
    is_library_mode: bool,
    show_cmdline: bool = True,
    context: FoundryContext | None = None,
) -> None:
    """Log a boot message including version, PID, and parent process info.

    Args:
        project_name: Project name for the boot message.
        version: Version string for the boot message.
        is_library_mode: Whether to append ``", library-mode"`` to the message.
        show_cmdline: Whether to append the process command line.
        context: Project context for resolving the project root path.
    """
    process_info = get_process_info(context=context)
    mode_suffix = ", library-mode" if is_library_mode else ""
    message = (
        f"⭐ Booting {project_name} v{version} "
        f"(project root {process_info.project_root}, pid {process_info.pid}), "
        f"parent '{process_info.parent.name}' (pid {process_info.parent.pid}){mode_suffix}"
    )
    if show_cmdline and process_info.cmdline:
        cmdline_str = " ".join(process_info.cmdline)
        message += f", command: {cmdline_str}"
    logger.debug(message)


def _register_shutdown_message(project_name: str, version: str) -> None:
    """Register an atexit handler that logs a shutdown message.

    The handler is skipped in pytest environments (to avoid Loguru warnings
    about closed stream handles) and when stderr is already closed.

    Args:
        project_name: Project name for the shutdown message.
        version: Version string for the shutdown message.
    """

    def _shutdown_handler() -> None:
        # In test environments (pytest), stderr may be closed/replaced before
        # atexit runs.  Skip logging in tests to avoid loguru stream errors.
        if "pytest" in sys.modules:
            return

        if not sys.stderr.closed:
            with contextlib.suppress(ValueError, OSError):
                logger.trace("Exiting {} v{} ...", project_name, version)

    atexit.register(_shutdown_handler)
