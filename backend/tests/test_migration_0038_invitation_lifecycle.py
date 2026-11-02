"""Migration 0038 against populated 0037 data, both directions, on real
PostgreSQL. Skipped without one (tests/postgres_support.py)."""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres


@pytest.fixture
def _restore_logger_disabled_state():
    # A real Alembic command re-runs logging.config.fileConfig and disables
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


@pytest.fixture
def at_0037(monkeypatch, _restore_logger_disabled_state):
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
    config = Config("alembic.ini")
    command.upgrade(config, "0037")
    try:
        yield engine, config
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("DROP SCHEMA IF EXISTS commercial_core CASCADE"))
        engine.dispose()


def _org(conn) -> uuid.UUID:
    org_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO organizations (id, name, status, created_at, updated_at) "
            "VALUES (:id, 'Org', 'active', now(), now())"
        ),
        {"id": org_id},
    )
    return org_id


def _user(conn) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO users (id, email, name, status, created_at, updated_at) "
            "VALUES (:id, :email, 'U', 'active', now(), now())"
        ),
        {"id": user_id, "email": f"{user_id.hex}@example.com"},
    )
    return user_id


def _grant(conn, *, kind, org=None, email=None, target=None, redeemed=False, expired=False) -> uuid.UUID:
    grant_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO identity_link_grants (id, kind, token_sha256, organization_id, role, invited_email, "
            "target_user_id, expires_at, redeemed_at, created_at, updated_at) VALUES (:id, :kind, :hash, :org, "
            ":role, :email, :target, now() + make_interval(hours => :ttl), "
            "CASE WHEN :redeemed THEN now() ELSE NULL END, now(), now())"
        ),
        {
            "id": grant_id,
            "kind": kind,
            "hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "org": org,
            "role": "VIEWER" if kind == "INVITATION" else None,
            "email": email,
            "target": target,
            "ttl": -1 if expired else 72,
            "redeemed": redeemed,
        },
    )
    return grant_id


def _status(conn, grant_id):
    return conn.execute(text("SELECT status FROM identity_link_grants WHERE id = :id"), {"id": grant_id}).scalar_one()


@requires_postgres
def test_upgrade_from_populated_0037_expires_legacy_invitations_and_builds_the_index(at_0037):
    engine, config = at_0037
    with engine.begin() as conn:
        org = _org(conn)
        # 0037 allowed several unredeemed invitations for one organization and
        # email, live or expired: exactly what the new unique index forbids.
        dup_live = _grant(conn, kind="INVITATION", org=org, email="dup@example.com")
        dup_expired = _grant(conn, kind="INVITATION", org=org, email="dup@example.com", expired=True)
        redeemed = _grant(conn, kind="INVITATION", org=org, email="done@example.com", redeemed=True)
        link = _grant(conn, kind="ACCOUNT_LINK", target=_user(conn))

    command.upgrade(config, "0038")

    with engine.begin() as conn:
        assert _status(conn, dup_live) == "EXPIRED"
        assert _status(conn, dup_expired) == "EXPIRED"
        assert _status(conn, redeemed) == "ACCEPTED"
        assert _status(conn, link) == "PENDING"
        index = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_identity_link_grants_open_invitation'")
        ).scalar_one()
        assert "UNIQUE" in index


@requires_postgres
def test_downgrade_expires_open_and_revoked_grants_so_0037_cannot_revive_them(at_0037):
    engine, config = at_0037
    command.upgrade(config, "0038")
    with engine.begin() as conn:
        org = _org(conn)
        open_invitation = _grant(conn, kind="INVITATION", org=org, email="open@example.com")
        conn.execute(text("UPDATE identity_link_grants SET status = 'PENDING' WHERE id = :id"), {"id": open_invitation})
        revoked_link = _grant(conn, kind="ACCOUNT_LINK", target=_user(conn))
        conn.execute(text("UPDATE identity_link_grants SET status = 'REVOKED' WHERE id = :id"), {"id": revoked_link})
        live_link = _grant(conn, kind="ACCOUNT_LINK", target=_user(conn))

    command.downgrade(config, "0037")

    with engine.begin() as conn:

        def expired(grant_id):
            return conn.execute(
                text("SELECT expires_at <= now() FROM identity_link_grants WHERE id = :id"), {"id": grant_id}
            ).scalar_one()

        assert expired(open_invitation) is True
        assert expired(revoked_link) is True
        assert expired(live_link) is False  # an untouched account link keeps working
