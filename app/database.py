"""
database.py

Builds a SQLAlchemy engine PER REQUEST, pointed at the resolved
tenant's database. Engines are cached per tenant (connection pooling
still works normally within a tenant) but never shared across tenants.
"""

from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from tenant_context import get_tenant_connection_string


@lru_cache(maxsize=64)
def _engine_for_tenant(tenant_name: str):
    conn_str = get_tenant_connection_string(tenant_name)

    # Test-only branch: register_test_tenant() in tenant_context hands
    # back a sqlite:// URL instead of a real Azure SQL connection
    # string, so unit tests never require pyodbc or network access.
    if conn_str.startswith("sqlite"):
        return create_engine(
            conn_str,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={conn_str}",
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_session(tenant_name: str) -> Session:
    engine = _engine_for_tenant(tenant_name)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()