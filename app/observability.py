"""
observability.py

The three pillars, wired for a multi-tenant app where "is the app up"
is a much less interesting question than "is tenant X having a bad
time right now":

- METRICS: a Prometheus-format /metrics endpoint (prometheus-fastapi-
  instrumentator gives request count/latency/in-flight for free) plus
  hand-rolled business metrics below - the ones that actually let you
  answer product questions from a dashboard, e.g. "did booking
  conflicts spike after last night's deploy?" or "which tenant is
  driving today's error rate?".

- TRACES: OpenTelemetry, auto-instrumenting FastAPI + SQLAlchemy so
  every request produces a trace showing exactly which tenant DB it
  hit and how long that query took. Exported to Azure Application
  Insights when APPLICATIONINSIGHTS_CONNECTION_STRING is set; exported
  to the console otherwise so tracing still works with zero Azure
  resources when running locally or in CI.

- LOGS: see logging_config.py. Correlated to traces via trace_id.

Every exporter here fails soft - a missing connection string disables
that exporter rather than crashing the app, which matters because
observability config should never be a deploy blocker.
"""

from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

from config import get_settings
from logging_config import get_logger

log = get_logger(__name__)

# --- Business metrics ---------------------------------------------------
# Labeled by tenant so a single Grafana/Azure Monitor dashboard can be
# split or filtered per customer - the same isolation principle the
# infra follows, applied to observability.

TENANT_REQUESTS = Counter(
    "tutortrack_tenant_requests_total",
    "Requests handled, labeled by tenant and route",
    ["tenant", "route", "method", "status_code"],
)

SESSIONS_BOOKED = Counter(
    "tutortrack_sessions_booked_total",
    "Tutoring sessions successfully booked",
    ["tenant"],
)

BOOKING_CONFLICTS = Counter(
    "tutortrack_booking_conflicts_total",
    "Booking attempts rejected due to a scheduling conflict",
    ["tenant"],
)

TENANT_RESOLUTION_FAILURES = Counter(
    "tutortrack_tenant_resolution_failures_total",
    "Requests rejected because the tenant could not be resolved (unknown host/header)",
)

SECRET_FETCH_LATENCY = Histogram(
    "tutortrack_keyvault_secret_fetch_seconds",
    "Latency of fetching a tenant secret from Key Vault (cache misses only)",
    ["tenant"],
)


def instrument_app(app) -> None:
    """Call once at startup. Wires metrics + tracing into the FastAPI app."""
    settings = get_settings()

    if settings.enable_metrics:
        Instrumentator(
            should_group_status_codes=False,
            excluded_handlers=["/metrics", "/health/live", "/health/ready"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
        log.info("metrics_enabled", endpoint="/metrics")

    if settings.enable_tracing:
        _configure_tracing(app)


def _configure_tracing(app) -> None:
    settings = get_settings()

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    import os

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import (
                AzureMonitorTraceExporter,
            )

            exporter = AzureMonitorTraceExporter(
                connection_string=settings.applicationinsights_connection_string
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info("tracing_exporter_configured", exporter="azure_monitor")
        except Exception:
            log.warning(
                "azure_monitor_exporter_failed", exc_info=True,
                fallback="console",
            )
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif otlp_endpoint:
        # Used by docker-compose (see docker-compose.yml) to ship local
        # traces to Jaeger over OTLP - gives you a real trace waterfall
        # in a browser without touching Azure at all.
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )
        log.info("tracing_exporter_configured", exporter="otlp", endpoint=otlp_endpoint)
    else:
        # No exporter configured at all (e.g. plain unit tests) - still
        # emit spans so instrumentation is exercised, just to stdout.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        log.info("tracing_exporter_configured", exporter="console")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()