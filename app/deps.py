"""
deps.py

Shared FastAPI dependencies.

`get_authenticated_tenant` is the single choke point every route
depends on: it resolves + authenticates the tenant (see security.py)
before any handler code runs, so no route can accidentally skip auth.

`get_db` depends on it in turn, guaranteeing a DB session can only be
obtained for a tenant that has already been resolved and authenticated
- there's no code path that reaches a query without going through both.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_session
from security import verify_api_key


def get_authenticated_tenant(tenant_name: str = Depends(verify_api_key)) -> str:
    return tenant_name


def get_db(tenant_name: str = Depends(get_authenticated_tenant)) -> Session:
    db = get_session(tenant_name)
    try:
        yield db
    finally:
        db.close()