"""Tests for aignostics_foundry_core.log."""

import logging as stdlib_logging
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from aignostics_foundry_core.log import InterceptHandler, LogSettings, logging_initialize

_PROJECT = "testfoundry"
_VERSION = "0.0.1"
_MARKER_MESSAGE = "log_test_unique_marker_4f2a"
_STDLIB_MESSAGE = "stdlib_redirect_unique_marker_9b3c"
_FILE_HANDLER_MARKER = "file_handler_unique_marker_7e9b"
_FILTER_MARKER = "filter_func_unique_marker_3d5f"
_REPLACE_MARKER = "replace_handlers_unique_marker_8c1a"
_SENTRY_MARKER = "sentry.io unique drop marker 2f4e"


@pytest.mark.sequential
@pytest.mark.unit
class TestLoggingInitialize:
    """Behavioural tests for logging_initialize()."""

    def test_logging_initialize_adds_stderr_handler(self, capsys: pytest.CaptureFixture[str]) -> None:
        """After initialization with defaults, a log message appears on stderr."""
        logging_initialize(_PROJECT, _VERSION)
        from loguru import logger

        logger.info(_MARKER_MESSAGE)
        captured = capsys.readouterr()
        assert _MARKER_MESSAGE in captured.err

    def test_logging_initialize_skips_stderr_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When stderr is disabled via env var, no output is written to stderr."""
        monkeypatch.setenv(f"{_PROJECT.upper()}_LOG_STDERR_ENABLED", "false")
        logging_initialize(_PROJECT, _VERSION)
        from loguru import logger

        logger.info(_MARKER_MESSAGE)
        captured = capsys.readouterr()
        assert _MARKER_MESSAGE not in captured.err

    def test_intercept_handler_redirects_stdlib_log(self, capsys: pytest.CaptureFixture[str]) -> None:
        """After initialization, stdlib logging messages are forwarded to loguru (and thus stderr)."""
        logging_initialize(_PROJECT, _VERSION)
        stdlib_logging.getLogger("test.intercept").warning(_STDLIB_MESSAGE)
        captured = capsys.readouterr()
        assert _STDLIB_MESSAGE in captured.err

    def test_logging_initialize_file_handler_writes_to_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """File handler writes log output to the configured file when file_enabled."""
        log_file = tmp_path / "test.log"
        monkeypatch.setenv(f"{_PROJECT.upper()}_LOG_FILE_ENABLED", "true")
        monkeypatch.setenv(f"{_PROJECT.upper()}_LOG_FILE_NAME", str(log_file))
        logging_initialize(_PROJECT, _VERSION)
        from loguru import logger

        logger.info(_FILE_HANDLER_MARKER)
        logger.remove()  # Close/flush the file sink before reading
        assert _FILE_HANDLER_MARKER in log_file.read_text()

    def test_logging_initialize_filter_func_is_applied(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A filter_func returning False suppresses all output from the handler."""
        logging_initialize(_PROJECT, _VERSION, filter_func=lambda _: False)
        from loguru import logger

        logger.info(_FILTER_MARKER)
        assert _FILTER_MARKER not in capsys.readouterr().err

    def test_logging_initialize_replaces_handlers_on_repeated_calls(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Repeated calls replace existing handlers rather than accumulating them."""
        logging_initialize(_PROJECT, _VERSION)
        logging_initialize(_PROJECT, _VERSION)
        capsys.readouterr()  # Drain any buffered output from initialization
        from loguru import logger

        logger.info(_REPLACE_MARKER)
        assert capsys.readouterr().err.count(_REPLACE_MARKER) == 1

    def test_intercept_handler_drops_sentry_messages(self, capsys: pytest.CaptureFixture[str]) -> None:
        """InterceptHandler silently drops stdlib log messages containing 'sentry.io'."""
        logging_initialize(_PROJECT, _VERSION)
        stdlib_logging.getLogger("test.sentry").warning(_SENTRY_MARKER)
        assert _SENTRY_MARKER not in capsys.readouterr().err

    def test_logging_initialize_suppresses_psycopg_loggers(self) -> None:
        """After logging_initialize(), psycopg loggers are set to WARNING to suppress noise."""
        logging_initialize(_PROJECT, _VERSION)
        assert stdlib_logging.getLogger("psycopg").level == stdlib_logging.WARNING
        assert stdlib_logging.getLogger("psycopg.pool").level == stdlib_logging.WARNING


@pytest.mark.unit
class TestLogSettings:
    """Behavioural tests for LogSettings validation."""

    def test_log_settings_file_name_validation_rejects_directory(self, tmp_path: Path) -> None:
        """Passing an existing directory as file_name raises ValidationError when file_enabled."""
        with pytest.raises(ValidationError):
            LogSettings(file_enabled=True, file_name=str(tmp_path))  # pyright: ignore[reportCallIssue]

    def test_log_settings_file_validation_skipped_when_file_disabled(self, tmp_path: Path) -> None:
        """Directory path as file_name is accepted without error when file_enabled is False."""
        settings = LogSettings(file_enabled=False, file_name=str(tmp_path))  # pyright: ignore[reportCallIssue]
        assert settings.file_enabled is False

    def test_log_settings_file_rejects_path_in_missing_parent_dir(self) -> None:
        """LogSettings raises ValidationError when file_name parent directory does not exist."""
        with pytest.raises(ValidationError):
            LogSettings(file_enabled=True, file_name="/nonexistent_dir_xyz/app.log")  # pyright: ignore[reportCallIssue]

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod not supported on Windows")
    def test_log_settings_rejects_unwritable_existing_file(self, tmp_path: Path) -> None:
        """LogSettings raises ValidationError when file_name points to a non-writable existing file."""
        log_file = tmp_path / "readonly.log"
        log_file.write_text("")
        log_file.chmod(0o000)
        try:
            with pytest.raises(ValidationError):
                LogSettings(file_enabled=True, file_name=str(log_file))  # pyright: ignore[reportCallIssue]
        finally:
            log_file.chmod(0o644)


@pytest.mark.unit
class TestInterceptHandler:
    """Behavioural tests for InterceptHandler."""

    def test_intercept_handler_is_logging_handler(self) -> None:
        """InterceptHandler is a subclass of stdlib logging.Handler."""
        assert issubclass(InterceptHandler, stdlib_logging.Handler)

    def test_intercept_handler_uses_debug_for_unknown_level(self) -> None:
        """InterceptHandler falls back to DEBUG for unknown stdlib level names without raising."""
        record = stdlib_logging.LogRecord(
            name="test",
            level=stdlib_logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.levelname = "CUSTOM_UNKNOWN_LEVEL"
        InterceptHandler().emit(record)  # Must not raise

    def test_intercept_handler_handles_task_name(self) -> None:
        """InterceptHandler stores taskName in record extras when present without raising."""
        record = stdlib_logging.LogRecord(
            name="test",
            level=stdlib_logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.taskName = "MyAsyncTask"  # type: ignore[attr-defined]
        InterceptHandler().emit(record)  # Must not raise
