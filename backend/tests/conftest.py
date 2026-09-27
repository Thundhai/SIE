"""Shared pytest fixtures.

Tests run against an in-memory SQLite database rather than PostgreSQL.
This is safe because every model column uses SQLAlchemy's portable types
(`Uuid`, `DateTime(timezone=True)`, `String`) rather than any
PostgreSQL-specific dialect type, so the schema behaves identically. This
keeps the test suite fast and dependency-free; PostgreSQL is still the
target production database, exercised via Alembic + docker-compose.

**Database Boundary Separation milestone.** Some models now declare a
real PostgreSQL schema (`__table_args__ = {"schema": "commercial_core"}`,
see backend/docs/DATABASE_BOUNDARY.md) -- SQLite has no equivalent
concept, so the engine below sets `schema_translate_map` to collapse
`commercial_core` back onto SQLite's own single default namespace at
connection time. This is SQLAlchemy's own documented mechanism for
exactly this case (see "schema_translate_map" in SQLAlchemy's
Schema-level operations docs): the ORM layer, cross-schema foreign keys,
and every existing test's queries are completely unaffected -- only the
literal schema-qualified name is remapped, purely for SQLite's benefit.
Real Postgres (Alembic, CI) uses the actual `commercial_core` schema
unchanged.
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
    execution_options={"schema_translate_map": {"commercial_core": None}},
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
    only exist on PostgreSQL). Both schemas are dropped and freshly
    recreated for this one test, both before (guarding against leftover
    objects from a previous run or an ad hoc session against the same
    database) and after — the same `DROP SCHEMA ... CASCADE` approach
    `tests/test_migrations.py`'s own `_fresh_schema_engine()` uses, not
    merely `Base.metadata.drop_all()`.

    **Why `Base.metadata.create_all()`/`drop_all()` alone are not enough
    here (Database Boundary Separation milestone).** Some models now
    declare a real `commercial_core` schema (see
    backend/docs/DATABASE_BOUNDARY.md). Unlike Alembic's own migration
    chain (which creates that schema itself, in migration `0031`), this
    fixture builds tables directly from `Base.metadata` with no migration
    involved — `create_all()` does not create a missing schema on its
    own, so `commercial_core` must exist before it runs, or every
    `commercial_core`-schema table's `CREATE TABLE` fails outright.
    `drop_all()` alone is also unsafe on teardown: `commercial_core.
    recommendation_candidates` (migration `0033`) has no SQLAlchemy model
    by design (see that migration's own docstring), so `Base.metadata` has
    no record of it or its foreign keys into `public` — if a *different*,
    Alembic-driven test left it behind in this same database,
    `drop_all()`'s dependency-ordered `DROP TABLE`s on `public.users`/
    `public.safety_actions` fail with "other objects depend on it" instead
    of dropping cleanly. Dropping both schemas wholesale with `CASCADE`
    sidesteps this regardless of what created the leftover.

    Defined here, not in tests/postgres_support.py, so it's available to
    any test by parameter name alone via pytest's normal fixture
    discovery — no import, so no false "redefined name" shadowing warning
    the way importing a fixture function directly would cause. Every test
    using this fixture must be marked `@postgres_support.requires_postgres`
    so it's skipped, not failed, when no real server is reachable.
    """
    from sqlalchemy import create_engine, text

    from app.models import Base
    from tests.postgres_support import PG_TEST_DATABASE_URL

    engine = create_engine(PG_TEST_DATABASE_URL)

    def _reset_schemas() -> None:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
            conn.execute(text("CREATE SCHEMA commercial_core"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    _reset_schemas()
    Base.metadata.create_all(engine)

    pg_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = pg_session_factory()
    try:
        yield session
    finally:
        session.close()
        _reset_schemas()
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
