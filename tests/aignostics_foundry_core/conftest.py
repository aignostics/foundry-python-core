"""Shared fixtures for the aignostics_foundry_core test modules."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

from aignostics_foundry_core.log import InterceptHandler
from tests.conftest import TEST_PROJECT_PREFIX

if TYPE_CHECKING:
    from collections.abc import Generator

    from opentelemetry.sdk._logs import LoggerProvider  # pyright: ignore[reportPrivateImportUsage]

_OTEL_PREFIX = f"{TEST_PROJECT_PREFIX}OTEL_"
_OTLP_ENDPOINT = "https://otel-gateway.example.com:4317"

# otel_initialize() writes these with os.environ.setdefault(), so monkeypatch cannot undo them.
_OTEL_SDK_ENV_DEFAULTS = ("OTEL_SERVICE_NAME", "OTEL_SEMCONV_STABILITY_OPT_IN", "OTEL_EXPORTER_OTLP_CERTIFICATE")


class OtlpLogCapture:
    """Access to the log records that the OTLP log sink exports."""

    def __init__(self, exporter: InMemoryLogRecordExporter, set_logger_provider: MagicMock) -> None:
        """Keep the in-memory exporter and the patched ``set_logger_provider``.

        Args:
            exporter: The exporter that the ``LoggerProvider`` sends batches to.
            set_logger_provider: The patched ``opentelemetry._logs.set_logger_provider``.
        """
        self._exporter = exporter
        self._set_logger_provider = set_logger_provider

    @property
    def provider(self) -> LoggerProvider | None:
        """The ``LoggerProvider`` that ``otel_initialize`` built, or ``None`` if it built none."""
        call = self._set_logger_provider.call_args
        return None if call is None else call.args[0]

    @property
    def bodies(self) -> list[str]:
        """Bodies of the exported log records, after a flush of the ``LoggerProvider``."""
        provider = self.provider
        assert provider is not None, "otel_initialize() did not build a LoggerProvider"
        provider.force_flush()
        return [str(data.log_record.body) for data in self._exporter.get_finished_logs()]


@pytest.fixture
def otlp_log_exporter(monkeypatch: pytest.MonkeyPatch) -> Generator[OtlpLogCapture, None, None]:
    """Enable only the OTel logs signal and export its records to memory.

    Traces and metrics are off, so ``otel_initialize`` applies no global
    instrumentors and starts no span or metric export threads.  The fixture
    patches only OpenTelemetry symbols, so the global ``LoggerProvider`` stays
    unset.

    Teardown shuts the ``LoggerProvider`` down, removes all loguru sinks, removes
    the ``InterceptHandler`` that ``logging_initialize`` puts on the stdlib root
    logger, and restores the root logger level and the ``OTEL_*`` defaults.

    Yields:
        OtlpLogCapture: Access to the exported log records.
    """
    monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
    monkeypatch.setenv(f"{_OTEL_PREFIX}LOGS_ENABLED", "true")
    monkeypatch.setenv(f"{_OTEL_PREFIX}TRACES_ENABLED", "false")
    monkeypatch.setenv(f"{_OTEL_PREFIX}METRICS_ENABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", _OTLP_ENDPOINT)
    saved_env = {name: os.environ.get(name) for name in _OTEL_SDK_ENV_DEFAULTS}
    root_logger = logging.getLogger()
    saved_root_level = root_logger.level

    exporter = InMemoryLogRecordExporter()
    with (
        patch("opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter", return_value=exporter),
        patch("opentelemetry._logs.set_logger_provider") as set_logger_provider,
    ):
        capture = OtlpLogCapture(exporter, set_logger_provider)
        try:
            yield capture
        finally:
            if capture.provider is not None:
                capture.provider.shutdown()
            logger.remove()
            for handler in [h for h in root_logger.handlers if isinstance(h, InterceptHandler)]:
                root_logger.removeHandler(handler)
            root_logger.setLevel(saved_root_level)
            for name, value in saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
