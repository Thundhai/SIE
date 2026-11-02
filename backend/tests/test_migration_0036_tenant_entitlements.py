"""Migration 0036: Commercial Core's tenant-entitlement tables, against a
real PostgreSQL database (skipped without one; see tests/postgres_support.py).

Proves the tables land in `commercial_core`, start empty, enforce the
rules Commercial Core relies on (default-deny status, known capabilities
only, one row per organization, organizations cannot be deleted from
under a grant, a replayed `jti` inserts nothing), and that downgrade and
re-upgrade round-trip.
"""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres

TABLES = {"tenant_entitlements", "tenant_entitlement_events", "tenant_assertion_jti"}


@pytest.fixture
def migrated(monkeypatch, _restore_logger_disabled_state):
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    try:
        yield engine, config
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
        engine.dispose()


@pytest.fixture
def _restore_logger_disabled_state():
    # Same reason as tests/test_database_boundary_separation.py: a real
    # Alembic command re-runs logging.config.fileConfig and disables
    # unrelated loggers for the rest of the process.
    import logging

    manager = logging.Logger.manager
    previous = {name: lg.disabled for name, lg in manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    root_previous = logging.root.disabled
    yield
    for name, disabled in previous.items():
        lg = manager.loggerDict.get(name)
        if isinstance(lg, logging.Logger):
            lg.disabled = disabled
    logging.root.disabled = root_previous


def _tables(conn, schema: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": schema}
        )
    }


def _org(conn) -> uuid.UUID:
    org_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO organizations (id, name, status, created_at, updated_at) "
            "VALUES (:id, 'Org', 'ACTIVE', now(), now())"),
        {"id": org_id},
    )
    return org_id


@requires_postgres
def test_tables_are_created_empty_in_commercial_core(migrated):
    engine, _ = migrated
    with engine.connect() as conn:
        assert TABLES <= _tables(conn, "commercial_core")
        assert not TABLES & _tables(conn, "public")
        for table in TABLES:
            assert conn.execute(text(f"SELECT count(*) FROM commercial_core.{table}")).scalar_one() == 0


@requires_postgres
def test_a_new_entitlement_defaults_to_suspended_with_no_capabilities(migrated):
    engine, _ = migrated
    with engine.begin() as conn:
        org_id = _org(conn)
        conn.execute(
            text("INSERT INTO commercial_core.tenant_entitlements (id, organization_id, reason) VALUES (:id, :org, 'r')"),
            {"id": uuid.uuid4(), "org": org_id},
        )
        status, caps, version = conn.execute(
            text("SELECT status, capabilities, version FROM commercial_core.tenant_entitlements")
        ).one()
    assert (status, caps, version) == ("SUSPENDED", [], 1)


@requires_postgres
@pytest.mark.parametrize(
    "column,value,constraint",
    [
        ("status", "'GRANTED'", "ck_tenant_entitlements_status"),
        ("capabilities", "ARRAY['commercial_core:everything']::text[]", "ck_tenant_entitlements_known_capabilities"),
    ],
)
def test_unknown_status_and_capabilities_are_rejected(migrated, column, value, constraint):
    engine, _ = migrated
    with pytest.raises(IntegrityError, match=constraint):
        with engine.begin() as conn:
            org_id = _org(conn)
            conn.execute(
                text(
                    f"INSERT INTO commercial_core.tenant_entitlements (id, organization_id, reason, {column}) "
                    f"VALUES (:id, :org, 'r', {value})"
                ),
                {"id": uuid.uuid4(), "org": org_id},
            )


@requires_postgres
def test_every_known_capability_is_accepted_and_one_row_per_organization(migrated):
    engine, _ = migrated
    caps = [
        "commercial_core:attention_read",
        "commercial_core:analytics_read",
        "commercial_core:enterprise_intelligence_read",
        "commercial_core:decisions_read",
        "commercial_core:decisions_write",
        "commercial_core:rag_query",
    ]
    insert = text(
        "INSERT INTO commercial_core.tenant_entitlements (id, organization_id, reason, status, capabilities) "
        "VALUES (:id, :org, 'r', 'ACTIVE', :caps)"
    )
    with engine.begin() as conn:
        org_id = _org(conn)
        conn.execute(insert, {"id": uuid.uuid4(), "org": org_id, "caps": caps})
    with pytest.raises(IntegrityError, match="uq_tenant_entitlements_organization_id"):
        with engine.begin() as conn:
            conn.execute(insert, {"id": uuid.uuid4(), "org": org_id, "caps": caps[:1]})


@requires_postgres
@pytest.mark.parametrize(
    "row_sql,constraint",
    [
        (
            "INSERT INTO commercial_core.tenant_entitlements (id, organization_id, reason) VALUES (:id, :org, 'r')",
            "fk_tenant_entitlements_organization_id",
        ),
        (
            "INSERT INTO commercial_core.tenant_entitlement_events (id, organization_id, action, actor, reason) "
            "VALUES (:id, :org, 'grant', 'owner', 'r')",
            "fk_tenant_entitlement_events_organization_id",
        ),
    ],
    ids=["entitlement_row", "audit_row"],
)
def test_an_organization_with_a_grant_or_audit_row_cannot_be_deleted(migrated, row_sql, constraint):
    """Each table's RESTRICT is checked on its own: the organization has
    only the one row, so the other table's foreign key cannot be what
    blocks the delete."""
    engine, _ = migrated
    with engine.begin() as conn:
        org_id = _org(conn)
        conn.execute(text(row_sql), {"id": uuid.uuid4(), "org": org_id})
    with pytest.raises(IntegrityError, match=constraint):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM organizations WHERE id = :org"), {"org": org_id})


@requires_postgres
def test_a_replayed_jti_inserts_nothing(migrated):
    engine, _ = migrated
    jti = uuid.uuid4()
    insert = text(
        "INSERT INTO commercial_core.tenant_assertion_jti (jti, organization_id, cap, expires_at) "
        "VALUES (:jti, :org, 'commercial_core:decisions_write', now() + interval '1 minute') "
        "ON CONFLICT DO NOTHING RETURNING jti"
    )
    with engine.begin() as conn:
        first = conn.execute(insert, {"jti": jti, "org": uuid.uuid4()}).all()
        second = conn.execute(insert, {"jti": jti, "org": uuid.uuid4()}).all()
    assert len(first) == 1 and second == []


@requires_postgres
def test_downgrade_drops_only_these_tables_and_reupgrade_restores_them(migrated):
    engine, config = migrated
    command.downgrade(config, "0035")
    with engine.connect() as conn:
        remaining = _tables(conn, "commercial_core")
        assert not TABLES & remaining
        assert "ontology_concepts" in remaining  # earlier migrations untouched
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert TABLES <= _tables(conn, "commercial_core")
