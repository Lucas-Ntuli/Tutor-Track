"""
routers/health.py

Two distinct checks, because conflating them is a classic way to make
an outage worse:

- /health/live: is the process itself alive and able to handle HTTP at
  all? No dependency checks. This is what a container orchestrator
  should use to decide "should I restart this instance" - restarting
  won't fix a downstream Key Vault or SQL outage, so it must not
  depend on either.
- /health/ready: is this instance ready to actually serve traffic
  right now? This is what should gate "should traffic be routed here"
  (e.g. Container Apps readiness probe / load balancer). It does a
  lightweight check against one known tenant's Key Vault to catch
  "app is up but can't reach its dependencies" - the case liveness
  deliberately ignores.

/health is kept as a plain alias for /health/live for backwards
compatibility with anything already probing the old single endpoint.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import get_settings
from tenant_context import TENANT_VAULT_MAP, get_tenant_connection_string

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness():
    settings = get_settings()

    if settings.testing or not TENANT_VAULT_MAP:
        return {"status": "ready", "checked_dependency": None}

    probe_tenant = next(iter(TENANT_VAULT_MAP))
    try:
        get_tenant_connection_string(probe_tenant)
    except Exception as exc:  # pragma: no cover - exercised via integration/staging checks
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checked_dependency": "key_vault",
                "detail": str(exc.__class__.__name__),
            },
        )

    return {"status": "ready", "checked_dependency": "key_vault"}