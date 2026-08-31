"""Shared pytest fixtures.

Tests run against an in-memory SQLite database rather than PostgreSQL.
This is safe because every model column uses SQLAlchemy's portable types
(`Uuid`, `DateTime(timezone=True)`, `String`) rather than any
PostgreSQL-specific dialect type, so the schema behaves identically. This
keeps the test suite fast and dependency-free; PostgreSQL is still the
target production database, exercised via Alembic + docker-compose.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps_auth import DEV_USER_HEADER
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import Base

# The development-only identity mechanism (app/api/deps_auth.py) is gated
# by DEV_MODE, off by default in production. Tests exercise that pipeline
# deliberately, so it is turned on for the whole test session here — see
# tests/test_dev_mode_gate.py for a dedicated test that DEV_MODE=False
# fails closed, using its own local override rather than this shared one.
settings.DEV_MODE = True


def dev_auth_headers(user_id) -> dict[str, str]:
    """Build the development-mode identity header for `client` requests.
    See app/api/deps_auth.py — this names an existing user id; it cannot
    assert a role, permission, or organization directly."""
    return {DEV_USER_HEADER: str(user_id)}


engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def _reset_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _override_get_db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
