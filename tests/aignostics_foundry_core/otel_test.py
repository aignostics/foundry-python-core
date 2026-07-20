"""Tests for aignostics_foundry_core.otel."""

import logging
import os
import sys
from unittest.mock import ANY, MagicMock, patch

import pytest
from opentelemetry.sdk.resources import Resource

from aignostics_foundry_core.foundry import set_context
from aignostics_foundry_core.otel import (
    _OS_CA_BUNDLE_PATH,
    OTelSettings,
    _default_otlp_certificate_setdefault,
    _make_otel_log_sink,
    _otel_log_sink_filter,
    _otel_logs_initialize,
    _otel_metrics_initialize,
    _otel_traces_initialize,
    default_otel_instrumentors,
    instrument_fastapi,
    otel_initialize,
)
from tests.conftest import TEST_PROJECT_NAME, TEST_PROJECT_PREFIX, make_context

_OTEL_PREFIX = f"{TEST_PROJECT_PREFIX}OTEL_"
_OTLP_ENDPOINT = "https://otel-gateway.example.com:4317"
_OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
_OTEL_EXPORTER_OTLP_CERTIFICATE = "OTEL_EXPORTER_OTLP_CERTIFICATE"
_OTEL_SERVICE_NAME = "OTEL_SERVICE_NAME"
_TRACE_SET_TRACER_PROVIDER = "opentelemetry.trace.set_tracer_provider"
_METRICS_SET_METER_PROVIDER = "opentelemetry.metrics.set_meter_provider"
_LOGS_SET_LOGGER_PROVIDER = "opentelemetry._logs.set_logger_provider"
_OTEL_INSTRUMENTORS_APPLY = "aignostics_foundry_core.otel._otel_instrumentors_apply"


@pytest.fixture(autouse=True)
def _clean_otlp_certificate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure OTEL_EXPORTER_OTLP_CERTIFICATE starts unset for every test in this module.

    otel_initialize() sets this directly via os.environ (not monkeypatch, since it must
    outlive the call for the exporter constructors that follow) whenever it defaults it,
    so without this fixture one test's default would leak into every later test in the
    process, regardless of file, given pytest-randomly reorders tests.
    """
    monkeypatch.delenv(_OTEL_EXPORTER_OTLP_CERTIFICATE, raising=False)


_LOGURU_LOGGER_ADD = "aignostics_foundry_core.otel.logger.add"


@pytest.mark.integration
class TestOtelInitialize:
    """Behavioural tests for otel_initialize()."""

    def test_otel_initialize_returns_false_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when TESTPROJECT_OTEL_ENABLED is not set (default False)."""
        monkeypatch.delenv(f"{_OTEL_PREFIX}ENABLED", raising=False)
        result = otel_initialize()
        assert result is False

    def test_otel_initialize_returns_false_when_sdk_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when opentelemetry.sdk is not importable (find_spec returns None)."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with patch("aignostics_foundry_core.otel.find_spec", return_value=None):
            result = otel_initialize()
        assert result is False

    def test_otel_initialize_returns_false_when_enabled_but_endpoint_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns False when enabled but no OTLP endpoint is configured."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.delenv(_OTEL_EXPORTER_OTLP_ENDPOINT, raising=False)
        result = otel_initialize()
        assert result is False

    def test_otel_initialize_returns_true_and_sets_providers_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns True and installs tracer/meter providers when enabled with an endpoint."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        monkeypatch.delenv(_OTEL_SERVICE_NAME, raising=False)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER) as mock_set_tracer_provider,
            patch(_METRICS_SET_METER_PROVIDER) as mock_set_meter_provider,
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            result = otel_initialize()
        assert result is True
        mock_set_tracer_provider.assert_called_once()
        mock_set_meter_provider.assert_called_once()

    def test_otel_initialize_sets_foundry_service_resource_attribute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The shared Resource carries foundry_service=<context name>, disambiguated from service.name."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_OTEL_INSTRUMENTORS_APPLY),
            patch("opentelemetry.sdk.resources.Resource.create", wraps=Resource.create) as mock_create,
        ):
            otel_initialize()
        mock_create.assert_called_once_with({"service.version": ANY, "foundry_service": TEST_PROJECT_NAME})

    def test_otel_initialize_skips_traces_when_traces_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tracer provider is not installed when traces_enabled=false, metrics still are."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_OTEL_PREFIX}TRACES_ENABLED", "false")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER) as mock_set_tracer_provider,
            patch(_METRICS_SET_METER_PROVIDER) as mock_set_meter_provider,
        ):
            result = otel_initialize()
        assert result is True
        mock_set_tracer_provider.assert_not_called()
        mock_set_meter_provider.assert_called_once()

    def test_otel_initialize_skips_metrics_when_metrics_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Meter provider is not installed when metrics_enabled=false, traces still are."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_OTEL_PREFIX}METRICS_ENABLED", "false")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER) as mock_set_tracer_provider,
            patch(_METRICS_SET_METER_PROVIDER) as mock_set_meter_provider,
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            result = otel_initialize()
        assert result is True
        mock_set_tracer_provider.assert_called_once()
        mock_set_meter_provider.assert_not_called()

    def test_otel_initialize_skips_logs_setup_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logs bridge is not installed when only 'enabled' (not 'logs_enabled') is set."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.delenv(f"{_OTEL_PREFIX}LOGS_ENABLED", raising=False)
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_LOGS_SET_LOGGER_PROVIDER) as mock_set_logger_provider,
            patch(_LOGURU_LOGGER_ADD) as mock_logger_add,
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            result = otel_initialize()
        assert result is True
        mock_set_logger_provider.assert_not_called()
        mock_logger_add.assert_not_called()

    def test_otel_initialize_installs_logs_bridge_when_logs_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logs bridge is installed when both 'enabled' and 'logs_enabled' are set."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_OTEL_PREFIX}LOGS_ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_LOGS_SET_LOGGER_PROVIDER) as mock_set_logger_provider,
            patch(_LOGURU_LOGGER_ADD) as mock_logger_add,
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            result = otel_initialize()
        assert result is True
        mock_set_logger_provider.assert_called_once()
        mock_logger_add.assert_called_once()

    def test_otel_initialize_defaults_service_name_to_context_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OTEL_SERVICE_NAME defaults to the context project name when unset."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        monkeypatch.delenv(_OTEL_SERVICE_NAME, raising=False)
        ctx = make_context()
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            otel_initialize(context=ctx)
        assert os.environ[_OTEL_SERVICE_NAME] == TEST_PROJECT_NAME

    def test_otel_initialize_does_not_override_explicit_service_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicitly set OTEL_SERVICE_NAME is left untouched."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        monkeypatch.setenv(_OTEL_SERVICE_NAME, "explicit-service")
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_OTEL_INSTRUMENTORS_APPLY),
        ):
            otel_initialize()
        assert os.environ[_OTEL_SERVICE_NAME] == "explicit-service"

    def test_otel_initialize_returns_false_when_all_signals_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False (and installs nothing) when enabled but every signal is off."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_OTEL_PREFIX}TRACES_ENABLED", "false")
        monkeypatch.setenv(f"{_OTEL_PREFIX}METRICS_ENABLED", "false")
        monkeypatch.setenv(f"{_OTEL_PREFIX}LOGS_ENABLED", "false")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER) as mock_set_tracer_provider,
            patch(_METRICS_SET_METER_PROVIDER) as mock_set_meter_provider,
        ):
            result = otel_initialize()
        assert result is False
        mock_set_tracer_provider.assert_not_called()
        mock_set_meter_provider.assert_not_called()


@pytest.mark.integration
class TestDefaultOtelInstrumentors:
    """Behavioural tests for default_otel_instrumentors()."""

    def test_returns_httpx_instrumentor_when_package_installed(self) -> None:
        """Includes an HTTPXClientInstrumentor when both httpx and its instrumentor are importable."""
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        instrumentors = default_otel_instrumentors()
        assert any(isinstance(i, HTTPXClientInstrumentor) for i in instrumentors)

    def test_returns_sqlalchemy_instrumentor_when_package_installed(self) -> None:
        """Includes a SQLAlchemyInstrumentor when both sqlalchemy and its instrumentor are importable."""
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        instrumentors = default_otel_instrumentors()
        assert any(isinstance(i, SQLAlchemyInstrumentor) for i in instrumentors)

    def test_returns_empty_list_when_optional_instrumentation_absent(self) -> None:
        """Returns an empty list when no optional instrumentation package is importable."""
        with patch("aignostics_foundry_core.otel.find_spec", return_value=None):
            assert default_otel_instrumentors() == []


@pytest.mark.integration
class TestOtelInitializeInstrumentors:
    """Behavioural tests for otel_initialize()'s instrumentors handling."""

    def test_applies_default_instrumentors_when_none_given(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """default_otel_instrumentors() is used, and each is instrumented, when instrumentors=None."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        mock_instrumentor = MagicMock()
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch("aignostics_foundry_core.otel.default_otel_instrumentors", return_value=[mock_instrumentor]),
        ):
            result = otel_initialize()
        assert result is True
        mock_instrumentor.instrument.assert_called_once()

    def test_applies_given_instrumentors_instead_of_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit instrumentors list is used instead of default_otel_instrumentors()."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        mock_default = MagicMock()
        mock_custom = MagicMock()
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch("aignostics_foundry_core.otel.default_otel_instrumentors", return_value=[mock_default]),
        ):
            result = otel_initialize(instrumentors=[mock_custom])
        assert result is True
        mock_custom.instrument.assert_called_once()
        mock_default.instrument.assert_not_called()

    def test_empty_instrumentors_list_opts_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing instrumentors=[] applies nothing, without falling back to the default."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        mock_default = MagicMock()
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch("aignostics_foundry_core.otel.default_otel_instrumentors", return_value=[mock_default]),
        ):
            result = otel_initialize(instrumentors=[])
        assert result is True
        mock_default.instrument.assert_not_called()

    def test_instrumentors_not_applied_when_traces_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Instrumentors are skipped entirely when traces_enabled=false."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(f"{_OTEL_PREFIX}TRACES_ENABLED", "false")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        mock_instrumentor = MagicMock()
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
        ):
            result = otel_initialize(instrumentors=[mock_instrumentor])
        assert result is True
        mock_instrumentor.instrument.assert_not_called()

    def test_instrumentors_not_applied_when_tracer_provider_already_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The re-init guard (traces init returns False) means instrumentors aren't re-applied."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        mock_instrumentor = MagicMock()
        with (
            patch("aignostics_foundry_core.otel._otel_traces_initialize", return_value=False),
            patch(_METRICS_SET_METER_PROVIDER),
        ):
            result = otel_initialize(instrumentors=[mock_instrumentor])
        assert result is True
        mock_instrumentor.instrument.assert_not_called()


@pytest.mark.unit
class TestOtelExporterCertificateDefault:
    """Behavioural tests for the OTEL_EXPORTER_OTLP_CERTIFICATE default."""

    def test_defaults_to_os_ca_bundle_when_present(self) -> None:
        """Points at the OS CA bundle (installed by the Dockerfile) when it exists."""
        with patch("os.path.isfile", return_value=True):
            _default_otlp_certificate_setdefault()
        assert os.environ.get(_OTEL_EXPORTER_OTLP_CERTIFICATE) == _OS_CA_BUNDLE_PATH

    def test_falls_back_to_certifi_when_os_bundle_absent(self) -> None:
        """Falls back to certifi's bundle when the OS CA bundle file isn't present."""
        import certifi

        with patch("os.path.isfile", return_value=False):
            _default_otlp_certificate_setdefault()
        assert os.environ.get(_OTEL_EXPORTER_OTLP_CERTIFICATE) == certifi.where()

    def test_does_not_override_explicit_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicitly set OTEL_EXPORTER_OTLP_CERTIFICATE is left untouched."""
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_CERTIFICATE, "/explicit/ca.pem")
        _default_otlp_certificate_setdefault()
        assert os.environ[_OTEL_EXPORTER_OTLP_CERTIFICATE] == "/explicit/ca.pem"

    def test_leaves_unset_when_neither_os_bundle_nor_certifi_present(self) -> None:
        """Doesn't set the env var if neither the OS bundle nor certifi is available."""
        with (
            patch("os.path.isfile", return_value=False),
            patch("aignostics_foundry_core.otel.find_spec", return_value=None),
        ):
            _default_otlp_certificate_setdefault()
        assert _OTEL_EXPORTER_OTLP_CERTIFICATE not in os.environ

    def test_otel_initialize_sets_certificate_default_when_traces_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """otel_initialize() defaults the certificate as part of its normal startup."""
        monkeypatch.setenv(f"{_OTEL_PREFIX}ENABLED", "true")
        monkeypatch.setenv(_OTEL_EXPORTER_OTLP_ENDPOINT, _OTLP_ENDPOINT)
        with (
            patch(_TRACE_SET_TRACER_PROVIDER),
            patch(_METRICS_SET_METER_PROVIDER),
            patch(_OTEL_INSTRUMENTORS_APPLY),
            patch("os.path.isfile", return_value=True),
        ):
            otel_initialize()
        assert os.environ.get(_OTEL_EXPORTER_OTLP_CERTIFICATE) == _OS_CA_BUNDLE_PATH


@pytest.mark.integration
class TestOtelProviderReinitGuards:
    """Each per-signal init no-ops when a real provider is already registered."""

    def test_traces_initialize_noops_when_already_registered(self) -> None:
        """_otel_traces_initialize returns False when a real TracerProvider is registered."""
        from opentelemetry.sdk.trace import TracerProvider

        with patch("opentelemetry.trace.get_tracer_provider", return_value=TracerProvider()):
            assert _otel_traces_initialize(MagicMock()) is False

    def test_metrics_initialize_noops_when_already_registered(self) -> None:
        """_otel_metrics_initialize doesn't re-register when a real MeterProvider exists."""
        from opentelemetry.sdk.metrics import MeterProvider

        with (
            patch("opentelemetry.metrics.get_meter_provider", return_value=MeterProvider(metric_readers=[])),
            patch(_METRICS_SET_METER_PROVIDER) as mock_set,
        ):
            _otel_metrics_initialize(MagicMock())
        mock_set.assert_not_called()

    def test_logs_initialize_noops_when_already_registered(self) -> None:
        """_otel_logs_initialize doesn't re-register when a real LoggerProvider exists."""
        from opentelemetry.sdk._logs import LoggerProvider

        with (
            patch("opentelemetry._logs.get_logger_provider", return_value=LoggerProvider()),
            patch(_LOGS_SET_LOGGER_PROVIDER) as mock_set,
            patch(_LOGURU_LOGGER_ADD) as mock_add,
        ):
            _otel_logs_initialize(MagicMock())
        mock_set.assert_not_called()
        mock_add.assert_not_called()


@pytest.mark.integration
class TestOtelSettings:
    """Behavioural tests for OTelSettings."""

    def test_otel_settings_default_disabled(self) -> None:
        """OpenTelemetry is disabled by default (no env vars set)."""
        settings = OTelSettings()  # pyright: ignore[reportCallIssue]
        assert settings.enabled is False

    def test_otel_settings_logs_default_disabled(self) -> None:
        """Logs bridging is disabled by default, independent of 'enabled'."""
        settings = OTelSettings()  # pyright: ignore[reportCallIssue]
        assert settings.logs_enabled is False

    def test_otel_settings_traces_and_metrics_default_enabled(self) -> None:
        """Traces and metrics default to enabled, independent of the master 'enabled' switch."""
        settings = OTelSettings()  # pyright: ignore[reportCallIssue]
        assert settings.traces_enabled is True
        assert settings.metrics_enabled is True

    def test_otel_settings_uses_context_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OTelSettings reads env vars from the prefix supplied by FoundryContext."""
        set_context(make_context())
        monkeypatch.setenv(f"{TEST_PROJECT_PREFIX}OTEL_ENABLED", "true")
        settings = OTelSettings()  # pyright: ignore[reportCallIssue]
        assert settings.enabled is True


def _make_loguru_message(
    *,
    level_name: str = "INFO",
    message: str = "hello",
    exception: object = None,
) -> MagicMock:
    """Build a minimal fake loguru Message with a `.record` dict for sink tests."""
    level = MagicMock()
    level.name = level_name
    file_ = MagicMock()
    file_.path = "app.py"
    msg = MagicMock()
    msg.record = {
        "name": "my_module",
        "level": level,
        "file": file_,
        "line": 42,
        "message": message,
        "function": "my_func",
        "exception": exception,
    }
    return msg


@pytest.mark.unit
class TestMakeOtelLogSink:
    """Behavioural tests for _make_otel_log_sink()."""

    def test_sink_emits_stdlib_log_record_from_loguru_message(self) -> None:
        """Sink converts a loguru message into a stdlib LogRecord and emits it via the handler."""
        handler = MagicMock()
        sink = _make_otel_log_sink(handler)
        sink(_make_loguru_message(level_name="WARNING", message="disk almost full"))
        handler.emit.assert_called_once()
        record = handler.emit.call_args.args[0]
        assert isinstance(record, logging.LogRecord)
        assert record.name == "my_module"
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "disk almost full"
        assert record.funcName == "my_func"
        assert record.exc_info is None

    def test_sink_maps_loguru_only_levels_to_stdlib(self) -> None:
        """TRACE and SUCCESS (loguru-only levels) map to the closest stdlib level."""
        handler = MagicMock()
        sink = _make_otel_log_sink(handler)

        sink(_make_loguru_message(level_name="TRACE"))
        assert handler.emit.call_args.args[0].levelno == logging.DEBUG

        sink(_make_loguru_message(level_name="SUCCESS"))
        assert handler.emit.call_args.args[0].levelno == logging.INFO

    def test_sink_includes_exc_info_when_exception_present(self) -> None:
        """An exception on the loguru record is forwarded as exc_info.

        Raises:
            ValueError: deliberately, to obtain a real exc_info tuple.
        """
        handler = MagicMock()
        sink = _make_otel_log_sink(handler)
        error_message = "boom"
        try:
            raise ValueError(error_message)  # noqa: TRY301
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            exception = MagicMock(type=exc_type, value=exc_value, traceback=exc_tb)

        sink(_make_loguru_message(exception=exception))
        record = handler.emit.call_args.args[0]
        assert record.exc_info is not None
        assert record.exc_info[1] is exc_value


@pytest.mark.unit
class TestOtelLogSinkFilter:
    """Behavioural tests for _otel_log_sink_filter()."""

    @pytest.mark.parametrize("name", ["opentelemetry.sdk.trace.export", "grpc._channel"])
    def test_excludes_otel_and_grpc_records(self, name: str) -> None:
        """Records originating from opentelemetry/grpc are dropped to avoid a feedback loop."""
        assert _otel_log_sink_filter({"name": name}) is False  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize("name", ["my_module", "aignostics_foundry_core.otel", None])
    def test_keeps_application_records(self, name: str | None) -> None:
        """Application records (and nameless ones) are forwarded to the OTLP sink."""
        assert _otel_log_sink_filter({"name": name}) is True  # pyright: ignore[reportArgumentType]


@pytest.mark.unit
class TestInstrumentFastapi:
    """Behavioural tests for instrument_fastapi()."""

    def test_instrument_fastapi_returns_false_when_package_absent(self) -> None:
        """Returns False when opentelemetry-instrumentation-fastapi is not importable."""
        with patch("aignostics_foundry_core.otel.find_spec", return_value=None):
            result = instrument_fastapi(MagicMock())
        assert result is False

    def test_instrument_fastapi_returns_true_and_instruments_app(self) -> None:
        """Returns True and calls FastAPIInstrumentor.instrument_app with the given app."""
        from opentelemetry.sdk.trace import TracerProvider

        mock_app = MagicMock()
        with (
            patch("opentelemetry.trace.get_tracer_provider", return_value=TracerProvider()),
            patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app") as mock_instrument,
        ):
            result = instrument_fastapi(mock_app)
        assert result is True
        mock_instrument.assert_called_once_with(mock_app)

    def test_instrument_fastapi_noops_when_no_tracer_provider_registered(self) -> None:
        """Returns False and skips instrumentation when no real TracerProvider is registered."""
        with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app") as mock_instrument:
            result = instrument_fastapi(MagicMock())
        assert result is False
        mock_instrument.assert_not_called()
