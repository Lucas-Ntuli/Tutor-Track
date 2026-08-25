from fastapi import FastAPI

from config import get_settings
from exceptions import register_exception_handlers
from logging_config import configure_logging, get_logger
from middleware import RateLimitMiddleware, RequestContextMiddleware
from observability import instrument_app
from routers import health, sessions, students

configure_logging()
log = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="TutorTrack API",
    description="Multi-tenant scheduling API for tutoring centers - each tenant fully isolated at the infrastructure layer.",
    version="1.1.0",
)

# Order matters: Starlette makes the LAST middleware added the
# OUTERMOST one, i.e. it runs first on the way in. Rate limiting should
# reject a request before any request-context/logging work is spent on
# it, so RateLimitMiddleware is added last (runs first).
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)

register_exception_handlers(app)
instrument_app(app)

app.include_router(health.router)
app.include_router(students.router)
app.include_router(sessions.router)


@app.on_event("startup")
async def on_startup():
    log.info(
        "app_startup",
        environment=settings.environment,
        metrics_enabled=settings.enable_metrics,
        tracing_enabled=settings.enable_tracing,
        api_key_required=settings.require_api_key,
    )

    if settings.testing:
        # Local/dev convenience only (docker-compose sets TESTING=true):
        # seeds one usable tenant backed by a file-based SQLite DB, so
        # `docker compose up` gives a fully working API with zero Azure
        # resources. Never happens in a real deployment - see the
        # RuntimeError guard inside register_test_tenant().
        from database import _engine_for_tenant
        from models import Base
        from tenant_context import TENANT_VAULT_MAP, register_test_tenant

        if "local-dev" not in TENANT_VAULT_MAP:
            register_test_tenant(
                "local-dev",
                connection_string="sqlite:////app/data/local-dev.db",
                api_key="local-dev-key",
            )
            Base.metadata.create_all(_engine_for_tenant("local-dev"))
            log.info("local_dev_tenant_seeded", tenant="local-dev")