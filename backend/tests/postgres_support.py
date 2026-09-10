"""Shared support for PostgreSQL-*integration* tests — semantic
embeddings and retrieval need real pgvector operators (`<=>` cosine
distance, `.cosine_distance()`) that plain SQLite cannot execute (see
app/models/embedding.py and app/retrieval/retrieval_service.py). This is
deliberately a *separate* module from tests/conftest.py's SQLite-backed
`db_session`/`client` fixtures — the milestone spec is explicit that
pgvector integration tests must not be faked against SQLite and reported
as PostgreSQL coverage.

Every test that needs a real Postgres connection should import
`pg_session` from this module and be marked `@pytest.mark.postgres`. If
no reachable PostgreSQL + pgvector server is configured, those tests are
**skipped**, not failed — a plain `pytest` run in an environment with no
Postgres available still passes cleanly (the milestone's own "existing
tests continue passing... tests run without requiring an external AI
provider" — and, by the same principle, without requiring a database
this project doesn't provide by default in every environment).

Configure the target database via `PG_TEST_DATABASE_URL` (defaults to
`postgresql+psycopg://sie:sie@localhost:5432/sie_test` — a *separate*
database from the application's own `sie` database, so these tests never
touch development data). In this session's own environment, PostgreSQL 16
with the `postgresql-16-pgvector` package (pgvector 0.6.0) was installed
and a local server started specifically to run these tests for real — see
the final report for exact commands. A CI environment would provision the
same thing (e.g. a `postgres:16` service container with pgvector, or the
`pgvector/pgvector` image) rather than relying on it happening to already
exist on the runner.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

PG_TEST_DATABASE_URL = os.environ.get(
    "PG_TEST_DATABASE_URL", "postgresql+psycopg://sie:sie@localhost:5432/sie_test"
)


def _postgres_with_pgvector_available() -> bool:
    try:
        engine = create_engine(PG_TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001 - genuinely "is anything reachable at all"
        return False


# Evaluated once per test session (import time), not per test — a single
# connection attempt, not a probe on every postgres-marked test.
POSTGRES_AVAILABLE = _postgres_with_pgvector_available()

requires_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason=(
        f"No reachable PostgreSQL + pgvector server at {PG_TEST_DATABASE_URL} "
        "(set PG_TEST_DATABASE_URL to point at one). See "
        "tests/postgres_support.py for how to provision one."
    ),
)

# The `pg_session` fixture itself lives in tests/conftest.py (not here) so
# that pytest's normal fixture-discovery makes it available to any test
# by parameter name alone, with no explicit import — importing a fixture
# function directly and using it as a parameter name in the same module
# reads to static analysis as shadowing/redefinition. `requires_postgres`
# above is a plain marker, not a fixture, so it *is* meant to be imported
# directly into each test module that uses it.
