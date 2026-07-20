"""OpenTelemetry integration for application telemetry.

Mirrors the pattern used by :mod:`aignostics_foundry_core.sentry`: a
pydantic-settings-driven ``enabled`` flag, one initialisation entry-point
called from :func:`~aignostics_foundry_core.boot.boot`, and graceful
degradation when the optional SDK or an OTLP endpoint isn't configured.

Each signal is independently toggleable: ``traces_enabled`` and
``metrics_enabled`` default to ``True`` once the master ``enabled`` switch is
on, while ``logs_enabled`` defaults to ``False`` (different volume/cost
characteristics, see :class:`OTelSettings`).

Endpoint, service name, and all other exporter behaviour are read directly
from the standard OpenTelemetry environment variables (``OTEL_EXPORTER_OTLP_ENDPOINT``,
``OTEL_SERVICE_NAME``, ``OTEL_RESOURCE_ATTRIBUTES``, etc. — see
https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
rather than project-prefixed settings, so that services already familiar with
the OTel spec don't have to learn a second set of variable names.

``boot()`` sets up whichever of the process-wide TracerProvider/MeterProvider/
LoggerProvider are enabled, and FastAPI/ASGI-independent instrumentation,
including bridging loguru records into OTLP logs. Request-level FastAPI
tracing needs :func:`instrument_fastapi` applied to the app instance, which
can't happen here (``boot()`` runs before any FastAPI app is constructed) —
instead, :func:`~aignostics_foundry_core.api.core.init_api` calls it on the
app (and every versioned sub-app) it builds, since that function does
construct the instance and always runs after ``boot()``.

Beyond FastAPI, :func:`otel_initialize` also applies a list of
``BaseInstrumentor`` instances — unlike ``instrument_fastapi``, these don't
need a live app object, so they can run here. Defaults to
:func:`default_otel_instrumentors` (``HTTPXClientInstrumentor``, since
without it an outbound ``httpx`` call to another Foundry service drops the
W3C ``traceparent`` header and starts a new, disconnected trace at the callee
instead of continuing the caller's; and ``SQLAlchemyInstrumentor``, since
every Foundry "service" gets a SQLAlchemy-backed database layer
unconditionally). Pass ``instrumentors=[]`` to opt out, or a project-built
list (mirroring how ``constants.py`` builds ``SENTRY_INTEGRATIONS``) to opt
into more.

``OTEL_SEMCONV_STABILITY_OPT_IN`` also defaults to ``"http"``, opting HTTP
instrumentation into the stable semantic conventions instead of the old,
experimental ones both ``HTTPXClientInstrumentor`` and ``FastAPIInstrumentor``
still default to — the old conventions name a span after the literal request
path (unbounded cardinality for any route with a path parameter), the stable
ones require a low-cardinality route template instead.

``OTEL_EXPORTER_OTLP_CERTIFICATE`` also defaults to the OS's CA bundle, if
present (falling back to certifi's bundle otherwise), since the OTel
gateway's TLS-facing endpoints are signed by the fleet's internal
``aignx-ca-root-authority`` CA, not a publicly trusted root. The Foundry
Cloud Run Dockerfile installs that CA into the OS trust store via
``update-ca-certificates``, merging it with the distro's own roots into one
file — pointing at that file (rather than assembling a bundle here) keeps
trust independent of any one language/library, and still works for a
service that redirects ``OTEL_EXPORTER_OTLP_ENDPOINT`` at a publicly-signed
vendor. An explicit value for either env var always overrides the default.
"""

from __future__ import annotations

import atexit
import logging
import os
import pathlib
from importlib.util import find_spec
from typing import TYPE_CHECKING, Annotated, Any

from loguru import logger
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from aignostics_foundry_core.foundry import get_context
from aignostics_foundry_core.settings import OpaqueSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    import fastapi
    from loguru import Message, Record
    from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
    from opentelemetry.sdk._logs import LoggingHandler  # pyright: ignore[reportPrivateImportUsage]
    from opentelemetry.sdk.resources import Resource

    from aignostics_foundry_core.foundry import FoundryContext

_OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
_OTEL_EXPORTER_OTLP_CERTIFICATE = "OTEL_EXPORTER_OTLP_CERTIFICATE"
_OTEL_SERVICE_NAME = "OTEL_SERVICE_NAME"
_OTEL_SEMCONV_STABILITY_OPT_IN = "OTEL_SEMCONV_STABILITY_OPT_IN"

# Opts HTTP instrumentation (HTTPXClientInstrumentor, FastAPIInstrumentor) into the stable
# semantic conventions instead of the old, experimental ones both still default to. The old
# conventions name a span after the literal request path (e.g. "GET /items/42" — unbounded
# cardinality for any route with a path parameter); the stable conventions require a
# low-cardinality route template instead (e.g. "GET /items/{item_id}"). "http" opts fully into
# the new conventions; "http/dup" would emit both old and new attributes side by side for a
# migration window, which nothing here needs.
_OTEL_SEMCONV_STABILITY_OPT_IN_DEFAULT = "http"

# The fleet's OTel push-gateway instances (shared-tools, sandbox, ...) serve their
# HTTPProxy/ingress-facing TLS off certs issued by the internal aignx-ca-root-authority
# CA (GoogleCASClusterIssuer, CA pool aignx-ca-pool in aignx-host-project-kah) — not a
# publicly trusted root. In-cluster GKE consumers avoid this by using the collector's
# plaintext otlp/insecure:4319 receiver directly; Cloud Run and anything else reaching
# the gateway through its HTTPProxy over TLS needs this root to validate the connection.
#
# The Foundry Cloud Run Dockerfile installs that CA into the OS trust store via
# update-ca-certificates, which merges it with the distro's own roots into one bundle
# file at the path below — trusting it is then just a matter of pointing
# OTEL_EXPORTER_OTLP_CERTIFICATE there, no per-language cert handling needed (see
# _default_otlp_certificate_setdefault()). Falls back to certifi's bundle (public roots
# only, no internal CA) when that file isn't present, e.g. running outside the container.
_OS_CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"

# Logger-name prefixes whose records must never reach the OTLP log sink. opentelemetry's
# and grpc's own diagnostics arrive at loguru through log.py's root InterceptHandler;
# re-exporting them feeds OTel's export-failure logs straight back into the log export
# pipeline — an amplification loop that gets worse exactly when the backend is unhealthy.
_OTEL_LOG_SINK_EXCLUDED_LOGGER_PREFIXES = ("opentelemetry", "grpc")

# Opaque per-instance identifiers that are high-cardinality by construction (a fresh
# random/unique value every time a container or process starts) and carry no debugging
# value on their own — unlike e.g. k8s.pod.name, nothing about them is human-readable or
# stable enough to group on. Left in, they turn into an unbounded label dimension on any
# backend that flattens resource attributes into labels (e.g. the OTel gateway's Prometheus
# exporter with resource_to_telemetry_conversion enabled). Dropped from the shared Resource
# in otel_initialize() before any provider is built, so this holds for traces/metrics/logs
# alike and for every backend, not just ones that happen to filter it back out downstream.
_HIGH_CARDINALITY_RESOURCE_ATTRS = frozenset({
    "service.instance.id",  # auto-generated by opentelemetry-sdk's Resource.create() itself
    "faas.instance",  # set by GoogleCloudResourceDetector for Cloud Run
})

# Loguru level names are a superset of stdlib logging's (e.g. TRACE, SUCCESS).
# Map them to the closest stdlib numeric level so OTel's LoggingHandler (which
# expects a stdlib logging.LogRecord) records a sensible severity.
_LOGURU_TO_STDLIB_LEVEL = {
    "TRACE": logging.DEBUG,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "SUCCESS": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class OTelSettings(OpaqueSettings):
    """Configuration settings for OpenTelemetry integration.

    Reads environment variables using the prefix derived from the active
    :class:`~aignostics_foundry_core.foundry.FoundryContext` (e.g.
    ``MYPROJECT_OTEL_`` when the context's ``env_prefix`` is ``MYPROJECT_``).

    Only carries the project-scoped ``enabled`` switch — exporter endpoint,
    service name, and sampling are configured via the standard unprefixed
    ``OTEL_*`` environment variables the OpenTelemetry SDK reads itself.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialise settings, deriving env_prefix from the active FoundryContext."""
        super().__init__(_env_prefix=f"{get_context().env_prefix}OTEL_", **kwargs)  # pyright: ignore[reportCallIssue]

    enabled: Annotated[
        bool,
        Field(
            description="Master switch for OpenTelemetry export via OTLP. Individual signals are "
            "further gated by 'traces_enabled'/'metrics_enabled'/'logs_enabled'.",
            default=False,
        ),
    ]

    traces_enabled: Annotated[
        bool,
        Field(
            description="Export traces via OTLP. On by default once 'enabled' is set.",
            default=True,
        ),
    ]

    metrics_enabled: Annotated[
        bool,
        Field(
            description="Export metrics via OTLP. On by default once 'enabled' is set.",
            default=True,
        ),
    ]

    logs_enabled: Annotated[
        bool,
        Field(
            description=(
                "Bridge loguru records into OTLP log export. Off by default even when 'enabled' "
                "is set, since log volume/cost characteristics differ from traces/metrics."
            ),
            default=False,
        ),
    ]


def _default_otlp_certificate_setdefault() -> None:
    """Default ``OTEL_EXPORTER_OTLP_CERTIFICATE`` to the OS CA bundle, or certifi's.

    A no-op if the env var is already set — an explicit value, e.g. pointing at
    a different vendor's endpoint entirely, always wins.

    ``OTEL_EXPORTER_OTLP_CERTIFICATE`` *replaces* gRPC's trust roots rather than
    adding to them, so this needs a bundle that trusts both the internal CA and
    any public vendor a service might redirect the endpoint to. The Foundry
    Cloud Run Dockerfile installs the internal CA into the OS trust store,
    which merges it with the distro's own roots into one file at
    :data:`_OS_CA_BUNDLE_PATH` — pointing there covers both, with no
    per-language cert handling needed. Falls back to certifi's bundle (public
    roots only, no internal CA) when that file isn't present, e.g. running
    locally outside the container.
    """
    if os.environ.get(_OTEL_EXPORTER_OTLP_CERTIFICATE):
        return

    if pathlib.Path(_OS_CA_BUNDLE_PATH).is_file():
        os.environ[_OTEL_EXPORTER_OTLP_CERTIFICATE] = _OS_CA_BUNDLE_PATH
        return

    if find_spec("certifi"):
        import certifi  # noqa: PLC0415

        os.environ[_OTEL_EXPORTER_OTLP_CERTIFICATE] = certifi.where()


def default_otel_instrumentors() -> list[BaseInstrumentor]:
    """Build the best-practice default list of OTel auto-instrumentors.

    Mirrors how a project's own ``constants.py`` builds ``SENTRY_INTEGRATIONS``:
    try/except-import each optional instrumentation package, degrade
    gracefully if it isn't installed. Unlike ``FastAPIInstrumentor``, these
    instrumentors patch their target library globally and don't need a live
    app instance, so :func:`otel_initialize` can apply them directly.

    ``HTTPXClientInstrumentor``: without it, an outbound ``httpx`` call to
    another Foundry service doesn't get the W3C ``traceparent`` header
    injected, so the callee's span starts a new, disconnected trace instead
    of continuing the caller's — undermining the actual point of exporting
    traces at all.

    ``SQLAlchemyInstrumentor``: every Foundry "service" project gets a
    SQLAlchemy-backed database layer unconditionally (see
    :mod:`aignostics_foundry_core.database`), so DB query spans are as much a
    baseline expectation as HTTP ones. Calling ``.instrument()`` with no
    ``engine`` argument hooks SQLAlchemy's event system globally — it
    instruments any engine created afterward, which fits
    :func:`~aignostics_foundry_core.database.init_engine` being called later,
    after ``boot()`` (and therefore this) has already run.

    Returns:
        list[BaseInstrumentor]: Instantiated (not yet applied) instrumentors
            for every optional package found installed. Empty if none are.
    """
    instrumentors: list[BaseInstrumentor] = []

    # Each instrumentation package depends on its target library, so its own presence is
    # a sufficient gate — no need to separately probe httpx/sqlalchemy.
    if find_spec("opentelemetry.instrumentation.httpx"):
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415

        instrumentors.append(HTTPXClientInstrumentor())

    if find_spec("opentelemetry.instrumentation.sqlalchemy"):
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: PLC0415

        instrumentors.append(SQLAlchemyInstrumentor())

    return instrumentors


def _gcp_resource_detect() -> Resource:
    """Detect GCP resource attributes (``cloud.*``, ``faas.*``, ``k8s.*``), if any.

    Off GCP (local dev, non-GCP CI), ``GoogleCloudResourceDetector`` returns an empty
    ``Resource`` rather than raising, so this is always safe to merge in unconditionally.

    Returns:
        Resource: The detected attributes, empty if not running on GCP.
    """
    from opentelemetry.resourcedetector.gcp_resource_detector import (  # noqa: PLC0415
        GoogleCloudResourceDetector,
    )

    return GoogleCloudResourceDetector().detect()


def _drop_high_cardinality_resource_attrs(resource: Resource) -> Resource:
    """Strip :data:`_HIGH_CARDINALITY_RESOURCE_ATTRS` from a fully-merged ``Resource``.

    ``Resource.merge()`` can only overwrite a key's value, not remove it — so the
    auto-generated ``service.instance.id``/``faas.instance`` values can't be suppressed
    by merging over them, only by rebuilding the resource without them, after every
    other source (detectors, ``Resource.create()``'s own defaults) has already merged in.

    Args:
        resource: The fully-merged ``Resource`` about to be handed to a provider.

    Returns:
        Resource: A copy with the high-cardinality keys removed, same schema_url.
    """
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

    filtered = {k: v for k, v in resource.attributes.items() if k not in _HIGH_CARDINALITY_RESOURCE_ATTRS}
    return Resource(filtered, resource.schema_url)


def otel_initialize(
    *,
    context: FoundryContext | None = None,
    instrumentors: list[BaseInstrumentor] | None = None,
) -> bool:
    """Initialize OpenTelemetry tracing, metrics, and/or logs.

    Sets up a process-wide ``TracerProvider``, ``MeterProvider``, and/or
    ``LoggerProvider`` exporting via OTLP/gRPC, using ``OTEL_EXPORTER_OTLP_ENDPOINT``
    as configured target — independently for each signal, per
    :attr:`OTelSettings.traces_enabled`/``metrics_enabled``/``logs_enabled``.
    Does nothing (returns ``False``) unless explicitly enabled *and* an OTLP
    endpoint is configured, so that services which don't opt in never pay the
    cost of provider setup.

    Logs are bridged from loguru (which this project uses instead of stdlib
    ``logging``) via a loguru sink that forwards each record into OTel's own
    ``LoggingHandler`` — loguru has no first-party OTel integration, so this
    is the simplest way to reuse the SDK's own record conversion and trace
    correlation instead of duplicating it.

    Args:
        context: :class:`~aignostics_foundry_core.foundry.FoundryContext` providing
            the project name (used as the ``OTEL_SERVICE_NAME`` fallback) and
            version. Falls back to the global context set via
            :func:`~aignostics_foundry_core.foundry.set_context`.
        instrumentors: ``BaseInstrumentor`` instances to apply once traces are
            initialised (gated by :attr:`OTelSettings.traces_enabled`, same as
            ``instrument_fastapi``'s purpose). ``None`` (the default) uses
            :func:`default_otel_instrumentors`; pass ``[]`` to opt out entirely,
            or a longer list to opt into more than the default.

    Returns:
        bool: ``True`` if OpenTelemetry was initialised successfully, ``False`` otherwise.
    """
    ctx = context or get_context()

    settings = OTelSettings(
        _env_file=ctx.env_file,  # pyright: ignore[reportCallIssue]
    )

    if not find_spec("opentelemetry.sdk") or not settings.enabled:
        logger.trace("OpenTelemetry integration is disabled or opentelemetry.sdk not found, initialization skipped.")
        return False

    if not os.environ.get(_OTEL_EXPORTER_OTLP_ENDPOINT):
        logger.warning(
            "OpenTelemetry integration is enabled but {} is not set, initialization skipped.",
            _OTEL_EXPORTER_OTLP_ENDPOINT,
        )
        return False

    if not (settings.traces_enabled or settings.metrics_enabled or settings.logs_enabled):
        logger.warning(
            "OpenTelemetry integration is enabled but every signal "
            "(traces/metrics/logs) is disabled, nothing will be exported."
        )
        return False

    os.environ.setdefault(_OTEL_SERVICE_NAME, ctx.name)
    os.environ.setdefault(_OTEL_SEMCONV_STABILITY_OPT_IN, _OTEL_SEMCONV_STABILITY_OPT_IN_DEFAULT)
    _default_otlp_certificate_setdefault()

    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

    # foundry_service duplicates service.name under an unambiguous label. On metrics
    # (via the gateway's resource_to_telemetry_conversion), service.name lands as
    # `service_name`, and Prometheus's own scrape-level `job`/`instance` labels (naming
    # the collector pod, not this service) shadow the app's same-named resource
    # attributes into `exported_job`/`exported_instance` — confusing unless you already
    # know that convention. `foundry_service` sidesteps the whole collision.
    #
    # Merged with GoogleCloudResourceDetector so Cloud Run/GKE/GCE deployments also get
    # the standard cloud.*/faas.*/k8s.* resource attributes GCP's own detector fills in
    # (it no-ops with an empty Resource off-GCP, e.g. local dev or non-GCP CI).
    resource = _drop_high_cardinality_resource_attrs(
        _gcp_resource_detect().merge(
            Resource.create({"service.version": ctx.version_full, "foundry_service": ctx.name})
        )
    )

    if settings.traces_enabled and _otel_traces_initialize(resource):
        _otel_instrumentors_apply(instrumentors if instrumentors is not None else default_otel_instrumentors())

    if settings.metrics_enabled:
        _otel_metrics_initialize(resource)

    if settings.logs_enabled:
        _otel_logs_initialize(resource)

    logger.trace("OpenTelemetry integration initialized, exporting to {}.", os.environ[_OTEL_EXPORTER_OTLP_ENDPOINT])

    return True


def _otel_traces_initialize(resource: Resource) -> bool:
    """Set up the OTLP ``TracerProvider``.

    Split out of :func:`otel_initialize` since traces export is gated by
    :attr:`OTelSettings.traces_enabled`.

    No-ops if a real (non-proxy) ``TracerProvider`` is already registered —
    guards against ``boot()`` running twice in the same process (e.g. in tests,
    or a subprocess that inherited the parent's OTel state), which would
    otherwise register a second ``BatchSpanProcessor``/exporter pair on top of
    the first. Registers an ``atexit`` shutdown so the final batch of spans
    still buffered in the ``BatchSpanProcessor`` is flushed on process exit —
    on Cloud Run in particular, the container can be frozen or killed shortly
    after the last request without this.

    Args:
        resource: The shared OTel ``Resource`` used by all providers.

    Returns:
        bool: ``True`` if a provider was freshly registered, ``False`` if the
            re-initialisation guard skipped setup. The caller uses this to avoid
            re-applying instrumentors against an already-instrumented process.
    """
    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    if isinstance(trace.get_tracer_provider(), TracerProvider):
        logger.trace("OTel TracerProvider already registered, skipping re-initialization.")
        return False

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    atexit.register(tracer_provider.shutdown)
    return True


def _otel_instrumentors_apply(instrumentors: list[BaseInstrumentor]) -> None:
    """Apply each instrumentor's global ``.instrument()``.

    Called after :func:`_otel_traces_initialize` so instrumentors that read
    the global ``TracerProvider`` at instrument-time (rather than lazily per
    call) pick up the one this module just configured.

    Args:
        instrumentors: Instrumentors to apply, e.g. from
            :func:`default_otel_instrumentors`.
    """
    for instrumentor in instrumentors:
        instrumentor.instrument()
        logger.trace("Applied OTel instrumentor {}.", type(instrumentor).__name__)


def _otel_metrics_initialize(resource: Resource) -> None:
    """Set up the OTLP ``MeterProvider``.

    Split out of :func:`otel_initialize` since metrics export is gated by
    :attr:`OTelSettings.metrics_enabled`.

    No-ops if a real (non-proxy) ``MeterProvider`` is already registered, and
    registers an ``atexit`` shutdown — see :func:`_otel_traces_initialize` for
    why both matter. ``PeriodicExportingMetricReader`` only exports on its
    timer; without a shutdown flush, whatever accumulated since the last tick
    (up to the full export interval) is lost when the process exits.

    Args:
        resource: The shared OTel ``Resource`` used by all providers.
    """
    from opentelemetry import metrics  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter  # noqa: PLC0415
    from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # noqa: PLC0415

    if isinstance(metrics.get_meter_provider(), MeterProvider):
        logger.trace("OTel MeterProvider already registered, skipping re-initialization.")
        return

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)
    atexit.register(meter_provider.shutdown)


def _otel_logs_initialize(resource: Resource) -> None:
    """Set up the OTLP ``LoggerProvider`` and bridge loguru records into it.

    Split out of :func:`otel_initialize` since logs export is opt-in via
    :attr:`OTelSettings.logs_enabled`, off by default even when traces/metrics
    are enabled.

    No-ops if a real (non-proxy) ``LoggerProvider`` is already registered, and
    registers an ``atexit`` shutdown — see :func:`_otel_traces_initialize`.
    Logs are the highest-value signal to lose on an ungraceful exit (they're
    often what explains *why* the process is exiting), so this flush matters
    most here.

    Args:
        resource: The shared OTel ``Resource`` used by the tracer/meter providers.
    """
    # opentelemetry-python's logs API is still under a leading-underscore module path
    # even in stable releases (see open-telemetry/opentelemetry-python#3565) — noqa/
    # pyright-ignore below are for that upstream naming, not our own code.
    from opentelemetry import _logs as logs  # noqa: PLC0415, PLC2701
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter  # noqa: PLC0415, PLC2701
    from opentelemetry.sdk._logs import (  # noqa: PLC0415, PLC2701
        LoggerProvider,  # pyright: ignore[reportPrivateImportUsage]
        LoggingHandler,  # pyright: ignore[reportPrivateImportUsage]
    )
    from opentelemetry.sdk._logs.export import (  # noqa: PLC0415, PLC2701
        BatchLogRecordProcessor,  # pyright: ignore[reportPrivateImportUsage]
    )

    if isinstance(logs.get_logger_provider(), LoggerProvider):
        logger.trace("OTel LoggerProvider already registered, skipping re-initialization.")
        return

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    logs.set_logger_provider(logger_provider)
    atexit.register(logger_provider.shutdown)
    logger.add(
        _make_otel_log_sink(LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)),
        filter=_otel_log_sink_filter,
    )


def _otel_log_sink_filter(record: Record) -> bool:
    """Keep OTel/grpc self-diagnostics out of the OTLP log sink.

    log.py routes all stdlib logging into loguru via a root ``InterceptHandler``,
    so opentelemetry's and grpc's own log records (including export failures)
    reach loguru with their originating logger name preserved. Forwarding those
    back into the OTLP log pipeline would re-export the exporter's own error
    logs, amplifying volume precisely when the backend is unhealthy — this drops
    them at the sink.

    Args:
        record: The loguru record about to be handed to the OTel log sink.

    Returns:
        bool: ``False`` for records originating from OpenTelemetry/grpc itself.
    """
    return not str(record["name"] or "").startswith(_OTEL_LOG_SINK_EXCLUDED_LOGGER_PREFIXES)


def _make_otel_log_sink(handler: LoggingHandler) -> Callable[[Message], None]:
    """Build a loguru sink that forwards records to an OTel ``LoggingHandler``.

    Loguru has no first-party OTel integration, so this converts each loguru
    record into the stdlib ``logging.LogRecord`` shape ``LoggingHandler.emit``
    expects, reusing the SDK's own conversion/trace-correlation logic instead
    of reimplementing it.

    Args:
        handler: The OTel ``LoggingHandler`` to forward converted records to.

    Returns:
        A callable suitable for passing to ``loguru.logger.add()``.
    """

    def sink(message: Message) -> None:
        record = message.record
        exc_info = None
        if record["exception"] is not None:
            exc = record["exception"]
            exc_info = (exc.type, exc.value, exc.traceback)
        handler.emit(
            logging.LogRecord(
                name=record["name"] or "",
                level=_LOGURU_TO_STDLIB_LEVEL.get(record["level"].name, logging.INFO),
                pathname=record["file"].path,
                lineno=record["line"],
                msg=record["message"],
                args=None,
                exc_info=exc_info,  # pyright: ignore[reportArgumentType]
                func=record["function"],
            )
        )

    return sink


def instrument_fastapi(app: fastapi.FastAPI) -> bool:
    """Instrument a FastAPI app instance for request-level tracing.

    Called automatically by :func:`~aignostics_foundry_core.api.core.init_api`
    for the app (and every versioned sub-app) it builds — most projects never
    need to call this directly. Exposed for a project that constructs its
    ``FastAPI`` instance some other way; in that case, call it once, after the
    app is constructed and after :func:`otel_initialize` has run (so the
    TracerProvider it sets up is already in place).

    No-ops if no real (non-proxy) ``TracerProvider`` is registered — mirrors the
    guard :func:`_otel_traces_initialize` uses, so a service with tracing
    disabled (or not yet initialized) doesn't pay for ``OpenTelemetryMiddleware``
    on every request for nothing. Without this, :func:`init_api` calling this
    unconditionally would instrument every app regardless of whether OTel is
    even enabled, unlike :func:`default_otel_instrumentors`'s HTTPX/SQLAlchemy
    instrumentors, which are only applied once :func:`_otel_traces_initialize`
    confirms a provider was actually registered.

    Args:
        app: The FastAPI application instance to instrument.

    Returns:
        bool: ``True`` if instrumentation was applied, ``False`` if the
            ``opentelemetry-instrumentation-fastapi`` package isn't installed
            or no real ``TracerProvider`` is registered.
    """
    if not find_spec("opentelemetry.instrumentation.fastapi"):
        logger.trace("opentelemetry-instrumentation-fastapi not found, FastAPI instrumentation skipped.")
        return False

    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        logger.trace("No TracerProvider registered, skipping FastAPI instrumentation.")
        return False

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415

    FastAPIInstrumentor.instrument_app(app)
    logger.trace("FastAPI instrumentation applied.")
    return True
