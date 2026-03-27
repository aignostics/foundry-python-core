"""Logging configuration and utilities.

This module configures loguru as the primary logging framework and redirects
standard library logging to loguru via InterceptHandler.

Special logger configurations:
- psycopg.pool: Set to WARNING level to suppress verbose INFO logs from
  connection pool operations (getconn/putconn). Only non-nominal pool
  messages (warnings and errors) are logged.
"""

import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import platformdirs
from loguru import logger
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aignostics_foundry_core.foundry import get_context

if TYPE_CHECKING:
    from collections.abc import Callable

    from loguru import Record

    from aignostics_foundry_core.foundry import FoundryContext

_DEFAULT_PROJECT = "foundry"


def _validate_file_name(file_name: str | None) -> str | None:
    """Validate the file_name is valid and the file writeable.

    - Checks file_name does not yet exist or is a file
    - If not yet existing, checks it can be created
    - If existing file, checks file is writeable

    Args:
        file_name: The file name of the log file

    Returns:
        str | None: The validated file name

    Raises:
        ValueError: If file name is not valid or the file not writeable
    """
    if file_name is None:
        return file_name

    file_path = Path(file_name)
    if file_path.exists():
        if file_path.is_dir():
            message = f"File name {file_path.absolute()} exists but is a directory"
            raise ValueError(message)
        if not os.access(file_path, os.W_OK):
            message = f"File {file_path.absolute()} is not writable"
            raise ValueError(message)
    else:
        try:
            file_path.touch(exist_ok=True)
        except OSError as e:
            message = f"File {file_path.absolute()} cannot be created: {e}"
            raise ValueError(message) from e

        with contextlib.suppress(OSError):  # Parallel execution e.g. in tests can create race
            file_path.unlink()

    return file_name


class InterceptHandler(logging.Handler):
    """Stdlib logging handler that redirects all records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: PLR6301
        """Emit a log record by forwarding it to loguru.

        Args:
            record: The stdlib logging record to forward.
        """
        # Ignore Sentry-related log messages
        if "sentry.io" in record.getMessage():
            return

        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = "DEBUG"

        # Patch the record to use the original logger name, function, and line from standard logging
        def patcher(record_dict: "Record") -> None:
            record_dict["module"] = record.module
            record_dict["extra"] = record.__dict__.get("extra", {})
            if record.processName and record.process:
                record_dict["process"].id = record.process
                record_dict["process"].name = record.processName
            if record.threadName and record.thread:
                record_dict["thread"].id = record.thread
                record_dict["thread"].name = record.threadName
            if record.taskName:
                record_dict["extra"]["logging.taskName"] = record.taskName
            record_dict["name"] = record.name
            record_dict["function"] = record.funcName
            record_dict["line"] = record.lineno
            record_dict["file"].path = record.pathname
            record_dict["file"].name = record.filename

        # Don't use depth parameter - let it use the patched function/line info instead
        # Use contextlib.suppress to handle Loguru re-entrancy issues in async contexts
        # Silently ignore re-entrancy errors - the message was already logged
        # by another handler or will be logged when the lock is released
        with contextlib.suppress(RuntimeError):
            logger.patch(patcher).opt(exception=record.exc_info).log(level, record.getMessage())


class LogSettings(BaseSettings):
    """Settings for configuring logging behaviour.

    Reads from environment variables with the ``FOUNDRY_LOG_`` prefix by
    default.  Callers can supply a project-specific prefix or env file at
    instantiation time using Pydantic Settings v2 constructor kwargs::

        settings = LogSettings(_env_prefix="BRIDGE_LOG_", _env_file=".env")
    """

    model_config = SettingsConfigDict(
        env_prefix="FOUNDRY_LOG_",
        extra="ignore",
        env_file_encoding="utf-8",
    )

    level: Literal["CRITICAL", "ERROR", "WARNING", "SUCCESS", "INFO", "DEBUG", "TRACE"] = Field(
        default="INFO",
        description="Log level, see https://loguru.readthedocs.io/en/stable/api/logger.html",
    )
    stderr_enabled: bool = Field(default=True, description="Enable logging to stderr")
    file_enabled: bool = Field(default=False, description="Enable logging to file")
    file_name: str = Field(
        default=platformdirs.user_data_dir(_DEFAULT_PROJECT) + f"/{_DEFAULT_PROJECT}.log",
        description="Name of the log file",
    )
    redirect_logging: bool = Field(default=True, description="Redirect standard logging to loguru")

    @field_validator("file_name")
    @classmethod
    def validate_file_name_when_enabled(cls, file_name: str, info: ValidationInfo) -> str:
        """Validate file_name only when file_enabled is True.

        Args:
            file_name: The file name to validate.
            info: Validation info containing other field values.

        Returns:
            str: The validated file name.
        """
        if info.data.get("file_enabled", False):
            _validate_file_name(file_name)
        return file_name


def logging_initialize(
    filter_func: "Callable[[Record], bool] | None" = None,
    *,
    context: "FoundryContext | None" = None,
) -> None:
    """Initialize logging configuration.

    Removes all existing loguru handlers, then adds stderr and/or file
    handlers based on settings read from environment variables with the
    ``{ctx.env_prefix}LOG_`` prefix (derived from the context).

    Args:
        filter_func: Optional loguru filter callable; receives a ``Record``
            and returns ``True`` to keep the message, ``False`` to drop it.
        context: Optional :class:`~aignostics_foundry_core.foundry.FoundryContext`
            providing the project name and version.  Falls back to the
            process-level context installed via
            :func:`~aignostics_foundry_core.foundry.set_context`.
    """
    ctx = context or get_context()
    settings = LogSettings(_env_prefix=f"{ctx.env_prefix}LOG_", _env_file=ctx.env_file)  # pyright: ignore[reportCallIssue]

    logger.remove()  # Remove all default loggers

    logger.configure(
        extra={
            "project_name": ctx.name,
            "version": ctx.version,
            "K_SERVICE": os.getenv("K_SERVICE", ""),
        }
    )

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<yellow>{process: <6}</yellow> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level> | "
        "{extra}"
    )

    if settings.stderr_enabled:
        logger.add(sys.stderr, level=settings.level, format=log_format, filter=filter_func)

    if settings.file_enabled:
        logger.add(settings.file_name, level=settings.level, format=log_format, filter=filter_func)

    if settings.redirect_logging:
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Suppress psycopg connection logs to prevent Loguru deadlock issues.
    # The psycopg library logs during connection setup, and when these logs are
    # intercepted by Loguru's InterceptHandler while Loguru's lock is already held,
    # it causes a re-entrant lock error ("Could not acquire internal lock").
    # Also suppresses verbose getconn/putconn spam from the pool logger.
    logging.getLogger("psycopg").setLevel(logging.WARNING)
    logging.getLogger("psycopg.pool").setLevel(logging.WARNING)
    logger.trace("psycopg and psycopg.pool loggers set to WARNING to prevent deadlock and reduce noise")

    logger.trace("Logging initialized with level: {}", settings.level)
