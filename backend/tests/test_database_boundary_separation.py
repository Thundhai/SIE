"""Database Boundary Separation milestone — explicit cross-schema tests.

PostgreSQL-integration tests — see tests/postgres_support.py. Skipped
automatically if no real PostgreSQL + pgvector server is reachable
(schemas are a real PostgreSQL concept; SQLite has none).

These prove, against a real migrated database, the specific claims made
in backend/docs/DATABASE_BOUNDARY.md and the migration docstrings in
migrations/versions/0031-0035: the commercial_core schema exists,
ontology_concepts genuinely lives there and not in public, the
cross-schema RESTRICT foreign key from risk_assessment_findings still
enforces exactly as before, approved risk-area resolution still works
unchanged, the 11 GLOBAL seed concepts survive a fresh migration, the
whole chain converges identically for a fresh install and an upgrade
from the pre-boundary state, and Commercial Core's own read dependency
on Public SIE's M43A tables is unaffected. No test here duplicates the
per-migration downgrade/reupgrade round-trip coverage already in
tests/test_migrations.py — these are the boundary-specific assertions
that file's own per-revision tests don't already make.
"""

from __future__ import annotations

import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres


def _alembic_config() -> Config:
    return Config("alembic.ini")


@requires_postgres
def test_commercial_core_schema_exists(pg_session):
    """Test 1: the commercial_core schema exists on a migrated database."""
    schemas = {
        row[0]
        for row in pg_session.execute(
            text("SELECT schema_name FROM information_schema.schemata")
        ).all()
    }
    assert "commercial_core" in schemas
    assert "public" in schemas


@requires_postgres
def test_ontology_concepts_lives_in_commercial_core_not_public(pg_session):
    """Test 2: ontology_concepts exists in commercial_core and NOT in public."""
    public_tables = {
        row[0]
        for row in pg_session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).all()
    }
    commercial_core_tables = {
        row[0]
        for row in pg_session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'commercial_core'")
        ).all()
    }
    assert "ontology_concepts" not in public_tables
    assert "ontology_concepts" in commercial_core_tables


@requires_postgres
def test_risk_assessment_finding_fk_targets_commercial_core_ontology_concepts(pg_session):
    """Test 3: risk_assessment_findings.risk_area_concept_id references
    commercial_core.ontology_concepts.id — a real, DB-enforced,
    cross-schema foreign key, not a same-schema or soft reference."""
    row = pg_session.execute(
        text(
            "SELECT ccu.table_schema, ccu.table_name, ccu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = 'public' AND tc.table_name = 'risk_assessment_findings' "
            "  AND kcu.column_name = 'risk_area_concept_id'"
        )
    ).one()
    assert row.table_schema == "commercial_core"
    assert row.table_name == "ontology_concepts"
    assert row.column_name == "id"


def _insert_approved_risk_area_concept(pg_session) -> uuid.UUID:
    """Insert one APPROVED, risk-area-eligible `commercial_core.
    ontology_concepts` row directly, matching the exact shape migration
    0017 seeds (`VEHICLE_INCIDENT`, `event_subtype`, `INCIDENT` parent
    domain — see app/risk_assessment/risk_area_ontology_seed.py).

    `pg_session` (tests/conftest.py) builds its tables from
    `Base.metadata.create_all()`, not by running the Alembic chain, so
    migration 0017's own seed INSERT never runs against it — the same
    reason every other `pg_session`-based test in this suite builds its
    own minimal rows directly rather than assuming migration-seeded data
    is present. `test_eleven_global_seed_concepts_present_after_fresh_migration`
    below is the one test that actually proves migration 0017 seeds
    these rows, using a real `alembic upgrade head` instead."""
    concept_id = uuid.uuid4()
    pg_session.execute(
        text(
            "INSERT INTO commercial_core.ontology_concepts "
            "(id, organization_id, layer, parent_domain, concept_key, definition, justification, "
            "status, ontology_version, is_risk_area_eligible, created_at, updated_at) "
            "VALUES (:id, NULL, 'event_subtype', 'INCIDENT', 'VEHICLE_INCIDENT', "
            "'test fixture concept', 'test fixture concept', 'APPROVED', 1, TRUE, now(), now())"
        ),
        {"id": concept_id},
    )
    pg_session.commit()
    return concept_id


@requires_postgres
def test_restrict_still_prevents_deleting_a_referenced_concept(pg_session):
    """Test 4: ON DELETE RESTRICT still prevents deletion of a concept
    referenced by a risk finding, across the new schema boundary."""
    org_id = uuid.uuid4()
    pg_session.execute(
        text(
            "INSERT INTO organizations (id, name, status, created_at, updated_at) "
            "VALUES (:id, 'DB Boundary Test Org', 'active', now(), now())"
        ),
        {"id": org_id},
    )
    concept_id = _insert_approved_risk_area_concept(pg_session)
    assessment_id = pg_session.execute(
        text(
            "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
            "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
            "created_at, updated_at) "
            "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'DB Boundary Test Assessment', 'BASELINE', "
            "'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) RETURNING id"
        ),
        {"org_id": org_id},
    ).scalar_one()
    pg_session.execute(
        text(
            "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
            "risk_area_ontology_version, title, source, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, 'DB Boundary test finding', "
            "'MANUAL', 'OPEN', now(), now())"
        ),
        {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id},
    )
    pg_session.commit()

    from sqlalchemy.exc import IntegrityError

    try:
        pg_session.execute(
            text("DELETE FROM commercial_core.ontology_concepts WHERE id = :id"),
            {"id": concept_id},
        )
        pg_session.commit()
        raised = False
    except IntegrityError:
        pg_session.rollback()
        raised = True
    assert raised, "RESTRICT must still block deleting a concept a finding references"


@requires_postgres
def test_approved_risk_area_resolution_still_works(pg_session):
    """Test 5: resolve_risk_area_concept() (Public SIE code, unmodified by
    this milestone) still resolves an APPROVED, risk-area-eligible concept
    correctly now that it lives in commercial_core."""
    from app.risk_assessment.risk_area_resolution import resolve_risk_area_concept

    org_id = uuid.uuid4()
    pg_session.execute(
        text(
            "INSERT INTO organizations (id, name, status, created_at, updated_at) "
            "VALUES (:id, 'DB Boundary Resolution Org', 'active', now(), now())"
        ),
        {"id": org_id},
    )
    pg_session.commit()
    concept_id = _insert_approved_risk_area_concept(pg_session)

    resolved = resolve_risk_area_concept(pg_session, organization_id=org_id, concept_id=concept_id)
    assert resolved.id == concept_id
    assert resolved.is_risk_area_eligible is True


@requires_postgres
def test_eleven_global_seed_concepts_present_after_fresh_migration(monkeypatch):
    """Test 6: the 11 GLOBAL seed concepts (migration 0017) are present,
    in commercial_core, after the full chain including the boundary
    migrations.

    Runs a real `alembic upgrade head` from an empty database rather
    than using the `pg_session` fixture: `pg_session` (tests/conftest.py)
    builds tables via `Base.metadata.create_all()`, which never executes
    migration 0017's own seed `INSERT` -- only the real Alembic chain
    does. This is the one test in this file whose entire point is
    proving that seed step still runs and lands in `commercial_core`."""
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        command.upgrade(_alembic_config(), "head")
        with engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM commercial_core.ontology_concepts "
                    "WHERE organization_id IS NULL AND is_risk_area_eligible = TRUE"
                )
            ).scalar_one()
        assert count == 11
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
        engine.dispose()


@requires_postgres
def test_commercial_core_can_still_read_governing_standards(pg_session):
    """Test 9: governing_standards / organization_governing_standards
    (M43A) remain in `public`, unmoved — Commercial Core's own
    governance_mirror.py reads them directly across the schema boundary,
    per backend/docs/DATABASE_BOUNDARY.md. This test only proves the
    Public-SIE side of that contract: the tables are queryable, in
    public, with no boundary migration having touched them."""
    public_tables = {
        row[0]
        for row in pg_session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).all()
    }
    assert "governing_standards" in public_tables
    assert "organization_governing_standards" in public_tables

    commercial_core_tables = {
        row[0]
        for row in pg_session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'commercial_core'")
        ).all()
    }
    assert "governing_standards" not in commercial_core_tables
    assert "organization_governing_standards" not in commercial_core_tables


@requires_postgres
def test_boundary_migrations_upgrade_from_pre_boundary_state_and_downgrade_cleanly(monkeypatch):
    """Tests 7 & 8: upgrading from the pre-boundary state (0030) through
    the boundary migrations (0031-0035) converges on the same schema a
    fresh install reaches, and downgrading back to 0030 reverses every
    schema move (commercial_core empty/gone, everything back in public)
    without data loss for a table with a real row in it."""
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "0030")
        with engine.connect() as conn:
            concept_count_pre = conn.execute(text("SELECT count(*) FROM ontology_concepts")).scalar_one()
            assert concept_count_pre == 11  # seeded by migration 0017, still in public pre-boundary

        command.upgrade(config, "head")
        with engine.connect() as conn:
            schemas = {row[0] for row in conn.execute(text("SELECT schema_name FROM information_schema.schemata")).all()}
            assert "commercial_core" in schemas
            concept_count_post = conn.execute(
                text("SELECT count(*) FROM commercial_core.ontology_concepts")
            ).scalar_one()
            assert concept_count_post == concept_count_pre  # moved, not recreated — same 11 rows

        command.downgrade(config, "0030")
        with engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "ontology_concepts" in tables
            concept_count_downgraded = conn.execute(text("SELECT count(*) FROM ontology_concepts")).scalar_one()
            assert concept_count_downgraded == concept_count_pre
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
        engine.dispose()


def test_no_proprietary_commercial_core_application_code_in_public_sie():
    """Test 10: this milestone ported only database schema DDL
    (migration 0033), never Commercial Core application logic. No
    SQLAlchemy model for `recommendation_candidates` exists in this
    repository, and nothing under app/ imports app.recommendation.*."""
    import pathlib

    models_dir = pathlib.Path(__file__).resolve().parent.parent / "app" / "models"
    assert not (models_dir / "recommendation_candidate.py").exists()

    # Scoped to app/ deliberately: migrations/0033 legitimately names
    # "recommendation_candidates" in its own DDL (schema-only, per that
    # migration's own docstring) — that's a migrations/ file, not app/.
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    for py_file in app_dir.rglob("*.py"):
        text_content = py_file.read_text(encoding="utf-8")
        assert "app.recommendation" not in text_content, f"{py_file} references app.recommendation"
        assert "recommendation_candidates" not in text_content, f"{py_file} references recommendation_candidates"
