"""
security.py

Per-tenant API key check. Follows the same trust model as
tenant_context.py: there is no global API key. Each tenant's key lives
as its own secret in that tenant's Key Vault, fetched (and briefly
cached) the same way the DB connection string is, so a leaked key for
tenant A is useless against tenant B by construction - not because of
an application-level check that could have a bug, but because the
key simply doesn't exist anywhere tenant B's data is reachable from.

Disabled by default locally (`REQUIRE_API_KEY=false`) so the starter
kit is curl-able with zero setup; enabled in the reference Terraform
for staging/prod via the app's environment variables.
"""

import secrets

from fastapi import Header, HTTPException, Request

from config import get_settings
from logging_config import get_logger
from tenant_context import get_tenant_api_key, resolve_tenant_from_request

log = get_logger(__name__)


def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> str:
    """
    Dependency chain: resolves the tenant (raises 404 if unknown, same
    as get_db does), then - only if REQUIRE_API_KEY is on - validates
    the caller's key against that tenant's own stored key using a
    constant-time comparison to avoid leaking key material via timing.
    Returns the tenant name so route dependencies don't have to
    re-resolve it.
    """
    settings = get_settings()
    tenant_name = resolve_tenant_from_request(request)

    if not settings.require_api_key:
        return tenant_name

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    expected = get_tenant_api_key(tenant_name)
    if not expected or not secrets.compare_digest(x_api_key, expected):
        log.warning("api_key_rejected", tenant=tenant_name)
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant_name