"""
config.py

Single source of truth for runtime configuration. Everything that used
to be an `os.environ.get(...)` scattered across modules now lives here,
validated at startup via pydantic-settings - so a missing/misspelled
env var fails fast on boot instead of surfacing as a confusing runtime
error three requests later.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App / environment ---------------------------------------------
    environment: str = "local"  # local | staging | prod
    log_level: str = "INFO"
    log_json: bool = True  # JSON logs in prod, pretty console logs locally can override

    # --- Auth ------------------------------------------------------------
    # When true, requests must present a valid X-API-Key for the resolved
    # tenant (checked against that tenant's Key Vault). Off by default
    # locally so `curl` against the starter kit works with zero setup.
    require_api_key: bool = False

    # --- Azure identity / Key Vault --------------------------------------
    app_identity_client_id: str | None = None

    # --- Observability -----------------------------------------------------
    applicationinsights_connection_string: str | None = None
    enable_tracing: bool = True
    enable_metrics: bool = True
    otel_service_name: str = "tutortrack-api"

    # --- Rate limiting (best-effort, in-process; see middleware.py) -----
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120

    # --- Testing ----------------------------------------------------------
    # Lets tests (and only tests) swap in a SQLite engine and a fake
    # tenant map without touching Azure at all. Never set this in a real
    # deployment.
    testing: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()