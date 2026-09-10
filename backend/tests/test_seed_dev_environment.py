"""SIE Milestone UI-DEV-01 — tests for `scripts/seed_dev_environment.py`.

Two concerns, tested at the process boundary (subprocess), exactly how a
developer actually runs this script — not by importing its internals,
so these tests exercise the real fail-closed guard a developer would
hit, not a mock of it:

1. The script refuses to run at all when `DEV_MODE` is not enabled —
   this is the one safety property the whole milestone depends on (§7:
   "DEV_MODE cannot be accidentally enabled by frontend configuration
   alone" implies the backend-side seed tooling must itself refuse
   just as hard as the request-time dev-auth mechanism already does).
2. The script is idempotent-by-refusal: seeding twice against the same
   database is rejected, not silently duplicated or merged.

Both tests need a real reachable PostgreSQL server (the script imports
`app.core.database.SessionLocal`, a real engine, not the SQLite
`db_session` test fixture) — see tests/postgres_support.py. Skipped,
not failed, when none is configured, same as every other Postgres
integration test in this suite.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_DIR / "scripts" / "seed_dev_environment.py"
DEV_ORGANIZATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000d01")


def _run_script(*, dev_mode: str | None, database_url: str) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    if dev_mode is None:
        env.pop("DEV_MODE", None)
    else:
        env["DEV_MODE"] = dev_mode
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@requires_postgres
def test_seed_script_refuses_without_dev_mode(pg_session):
    """The core production-safety property: pointed at a real database,
    the script still refuses to write anything at all when DEV_MODE is
    not explicitly enabled — mirrors the request-time dev-auth
    mechanism's own fail-closed posture (app/api/deps_auth.py)."""
    result = _run_script(dev_mode=None, database_url=PG_TEST_DATABASE_URL)
    assert result.returncode != 0
    assert "DEV_MODE" in result.stdout + result.stderr

    result_false = _run_script(dev_mode="false", database_url=PG_TEST_DATABASE_URL)
    assert result_false.returncode != 0
    assert "DEV_MODE" in result_false.stdout + result_false.stderr

    # Nothing was created.
    row = pg_session.execute(
        text("SELECT 1 FROM organizations WHERE id = :id"), {"id": str(DEV_ORGANIZATION_ID)}
    ).first()
    assert row is None


@requires_postgres
def test_seed_script_is_idempotent_by_refusal_not_by_silent_duplication(pg_session):
    """First run succeeds and creates the fixed-id development
    organization; a second run against the same database refuses
    rather than creating a duplicate or silently merging into existing
    state (the script's own documented idempotency contract)."""
    first = _run_script(dev_mode="true", database_url=PG_TEST_DATABASE_URL)
    assert first.returncode == 0, first.stdout + first.stderr
    assert str(DEV_ORGANIZATION_ID) in first.stdout

    second = _run_script(dev_mode="true", database_url=PG_TEST_DATABASE_URL)
    assert second.returncode != 0
    assert "already exists" in second.stdout + second.stderr

    # Exactly one organization row at the fixed id, not two.
    count = pg_session.execute(
        text("SELECT count(*) FROM organizations WHERE id = :id"), {"id": str(DEV_ORGANIZATION_ID)}
    ).scalar_one()
    assert count == 1
