"""
tenant_context.py

Resolves which tenant a request belongs to (via subdomain or header)
and fetches THAT tenant's secrets from THAT tenant's Key Vault - never
a shared config value. This is what prevents a code bug from
accidentally cross-wiring tenant data: there is no global "the"
database connection or "the" API key, only a per-request, per-tenant
lookup.

Secrets are cached briefly (5 min TTL) to avoid hammering Key Vault on
every request, while still picking up rotations reasonably fast.
Cache-miss fetch latency is recorded to the
`tutortrack_keyvault_secret_fetch_seconds` metric so a slow/throttled
vault shows up on a dashboard instead of just as vague p99 latency.
"""

import time

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from cachetools import TTLCache
from fastapi import HTTPException, Request

from config import get_settings
from logging_config import get_logger

log = get_logger(__name__)

# In Azure, ManagedIdentityCredential is used automatically. Locally,
# DefaultAzureCredential falls back to `az login`, keeping dev/prod
# parity without code branches. Skipped entirely in test mode so unit
# tests never try to talk to Azure.
_settings = get_settings()
_credential = None
if not _settings.testing:
    _credential = (
        ManagedIdentityCredential(client_id=_settings.app_identity_client_id)
        if _settings.app_identity_client_id
        else DefaultAzureCredential()
    )

# tenant_name -> Key Vault URI. In production this map is populated
# from Terraform's `tenant_key_vaults` output at deploy time (baked
# into an env var or fetched from a small control-plane table) rather
# than hardcoded - this stub is intentionally simple for the starter kit.
TENANT_VAULT_MAP: dict[str, str] = {
    "brightpath-tutors": "https://tt-brightpath--kv.vault.azure.net/",
    "riverside-learning": "https://tt-riverside-l-kv.vault.azure.net/",
}

# Test-only escape hatch: lets tests register a fake tenant -> fake
# secret map without touching Key Vault or TENANT_VAULT_MAP at all.
_TEST_SECRETS: dict[str, dict[str, str]] = {}


def register_test_tenant(tenant_name: str, connection_string: str, api_key: str = "test-key") -> None:
    """Test-only helper. Raises if called outside TESTING=true to prevent misuse in prod."""
    if not get_settings().testing:
        raise RuntimeError("register_test_tenant() is only usable when TESTING=true")
    TENANT_VAULT_MAP.setdefault(tenant_name, f"test://{tenant_name}")
    _TEST_SECRETS[tenant_name] = {
        "db-connection-string": connection_string,
        "api-key": api_key,
    }


_secret_cache: TTLCache = TTLCache(maxsize=256, ttl=300)


def resolve_tenant_from_request(request: Request) -> str:
    """
    Tenant resolution strategy: subdomain first (brightpath-tutors.tutortrack.app),
    falling back to an explicit header for local dev / API clients.
    """
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else None

    tenant = request.headers.get("x-tenant-id") or subdomain
    if not tenant or tenant not in TENANT_VAULT_MAP:
        from observability import TENANT_RESOLUTION_FAILURES

        TENANT_RESOLUTION_FAILURES.inc()
        log.warning("tenant_resolution_failed", host=host, header_tenant=request.headers.get("x-tenant-id"))
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


def _fetch_secret(tenant_name: str, secret_name: str) -> str:
    cache_key = f"{secret_name}:{tenant_name}"
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    start = time.perf_counter()

    if get_settings().testing:
        value = _TEST_SECRETS.get(tenant_name, {}).get(secret_name)
        if value is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
    else:
        vault_uri = TENANT_VAULT_MAP[tenant_name]
        client = SecretClient(vault_url=vault_uri, credential=_credential)
        value = client.get_secret(secret_name).value

    from observability import SECRET_FETCH_LATENCY

    SECRET_FETCH_LATENCY.labels(tenant=tenant_name).observe(time.perf_counter() - start)
    log.info("secret_fetched", tenant=tenant_name, secret=secret_name, cache_hit=False)

    _secret_cache[cache_key] = value
    return value


def get_tenant_connection_string(tenant_name: str) -> str:
    return _fetch_secret(tenant_name, "db-connection-string")


def get_tenant_api_key(tenant_name: str) -> str | None:
    try:
        return _fetch_secret(tenant_name, "api-key")
    except HTTPException:
        return None