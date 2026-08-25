"""
conftest.py

Test fixtures. Sets TESTING=true before anything under app/ is
imported, which:
- skips real Azure credential creation in tenant_context.py
- allows register_test_tenant() to register a fake tenant backed by an
  in-memory SQLite database instead of a real Azure SQL connection

This means the whole test suite runs with zero Azure resources and
zero network access - a deliberate choice so CI (see
.github/workflows/ci.yml) can run these on every PR with no secrets.
"""

import os

os.environ["TESTING"] = "true"
os.environ["LOG_JSON"] = "false"
os.environ["ENABLE_TRACING"] = "false"  # keep test output quiet
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from database import _engine_for_tenant
from models import Base
from tenant_context import _TEST_SECRETS, TENANT_VAULT_MAP, register_test_tenant

TEST_TENANT = "test-academy"


@pytest.fixture(scope="session", autouse=True)
def _setup_test_tenant():
    get_settings.cache_clear()
    register_test_tenant(TEST_TENANT, connection_string="sqlite:///:memory:")
    engine = _engine_for_tenant(TEST_TENANT)
    Base.metadata.create_all(engine)
    yield
    TENANT_VAULT_MAP.pop(TEST_TENANT, None)
    _TEST_SECRETS.pop(TEST_TENANT, None)


@pytest.fixture
def client():
    from main import app

    return TestClient(app, headers={"x-tenant-id": TEST_TENANT})


@pytest.fixture
def unknown_tenant_client():
    from main import app

    return TestClient(app, headers={"x-tenant-id": "does-not-exist"})