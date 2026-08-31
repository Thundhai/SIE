"""Shared pytest fixtures.

Tests run against an in-memory SQLite database rather than PostgreSQL.
This is safe because every model column uses SQLAlchemy's portable types
(`Uuid`, `DateTime(timezone=True)`, `String`) rather than any
PostgreSQL-specific dialect type, so the schema behaves identically. This
keeps the test suite fast and dependency-free; PostgreSQL is still the
target production database, exercised via Alembic + docker-compose.
"""

from collections.abc import Generator
from pathlib import Path

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


# Small, non-confidential fixture files for the ingestion adapters (PDF,
# DOCX, XLSX, CSV, PPTX, RTF, TXT) — see tests/fixtures/ingestion/README.md
# for how they were generated.
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ingestion"


def load_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


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


@pytest.fixture
def pg_session() -> Generator[Session, None, None]:
    """A real PostgreSQL + pgvector session — see tests/postgres_support.py
    for why embedding/retrieval tests need one distinct from the SQLite
    `db_session` above (pgvector's `<=>`/`.cosine_distance()` operators
    only exist on PostgreSQL). Schema is dropped and freshly created for
    this one test, both before (guarding against leftover data from a
    previous run or an ad hoc session against the same database) and
    after. Defined here, not in tests/postgres_support.py, so it's
    available to any test by parameter name alone via pytest's normal
    fixture discovery — no import, so no false "redefined name" shadowing
    warning the way importing a fixture function directly would cause.
    Every test using this fixture must be marked
    `@postgres_support.requires_postgres` so it's skipped, not failed,
    when no real server is reachable.
    """
    from sqlalchemy import create_engine, text

    from app.models import Base
    from tests.postgres_support import PG_TEST_DATABASE_URL

    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    pg_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = pg_session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def _ingestion_storage(tmp_path) -> Generator[None, None, None]:
    """Point the ingestion engine's StorageProvider at a fresh per-test
    temp directory rather than the real `var/ingested_files` — see
    app/ingestion/storage.py. Autouse so no test forgets it and
    accidentally writes into the repo working tree."""
    from app.ingestion.storage import LocalFilesystemStorageProvider
    from app.services.ingestion_service import ingestion_service

    previous = ingestion_service._storage
    ingestion_service._storage = LocalFilesystemStorageProvider(tmp_path / "ingested_files")
    yield
    ingestion_service._storage = previous
