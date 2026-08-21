"""
logging_config.py

Structured logging via structlog. Every log line is emitted as JSON in
non-local environments (so it's directly queryable in Azure Log
Analytics / Application Insights without a parsing step) and as
readable colored text locally.

Two things make these logs actually useful for debugging a multi-tenant
incident instead of just being noise:

1. `trace_id` / `span_id` are injected on every line when a request is
   inside an active OpenTelemetry span (see observability.py), so a
   single log line can be pivoted straight into the matching distributed
   trace in Application Insights.
2. `tenant` and `request_id` are bound once per request in middleware.py
   and then automatically appear on *every* subsequent log line for that
   request, without every log call needing to pass them explicitly.
"""

import logging
import sys

import structlog
from opentelemetry import trace

from config import get_settings


def _add_trace_context(logger, method_name, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)