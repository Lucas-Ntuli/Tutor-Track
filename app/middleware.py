"""
middleware.py

Two middlewares, both deliberately simple:

1. RequestContextMiddleware - assigns/propagates a request ID, resolves
   the tenant (best-effort, without raising - route-level deps still do
   the authoritative resolution/auth), binds both to structlog's
   contextvars for the lifetime of the request, logs one structured
   line per request with status/duration/tenant, and records the
   `tutortrack_tenant_requests_total` metric.

2. RateLimitMiddleware - an in-process, best-effort token bucket per
   tenant. This is explicitly NOT a substitute for a real distributed
   rate limiter (e.g. Redis-backed, or Azure Front Door/API Management
   in front of the app) - it resets on every restart and doesn't
   coordinate across replicas. It exists to (a) protect a single
   instance from a runaway client and (b) demonstrate the pattern.
   Documented as a known limitation in the README rather than hidden.
"""

import time
import uuid
from collections import defaultdict, deque

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_settings
from logging_config import get_logger
from observability import TENANT_REQUESTS

log = get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"


def _best_effort_tenant(request: Request) -> str:
    """Non-raising tenant guess, for logging/metrics only - never for auth."""
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else None
    return request.headers.get("x-tenant-id") or subdomain or "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        tenant = _best_effort_tenant(request)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, tenant=tenant, path=request.url.path
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.error("request_unhandled_exception", exc_info=True)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id

        route = request.scope.get("route")
        route_path = route.path if route else request.url.path
        TENANT_REQUESTS.labels(
            tenant=tenant,
            route=route_path,
            method=request.method,
            status_code=response.status_code,
        ).inc()

        log.info(
            "request_handled",
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window token bucket, per tenant, per process. See module docstring."""

    def __init__(self, app):
        super().__init__(app)
        self._settings = get_settings()
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not self._settings.rate_limit_enabled or request.url.path in (
            "/health/live",
            "/health/ready",
            "/metrics",
        ):
            return await call_next(request)

        tenant = _best_effort_tenant(request)
        now = time.monotonic()
        window = 60.0
        bucket = self._hits[tenant]

        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= self._settings.rate_limit_per_minute:
            log.warning("rate_limit_exceeded", tenant=tenant)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
                headers={"Retry-After": "60"},
            )

        bucket.append(now)
        return await call_next(request)