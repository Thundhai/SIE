"""Migration-chain regression test.

Protects specifically against the class of defect discovered while
first integrating a real PostgreSQL + pgvector server: a migration that
adds a new PostgreSQL enum-typed column via `add_column()` to an
already-existing table must explicitly create that enum type first (see
migrations/versions/0005_knowledge_quality_and_semantic_chunking.py's own
docstring — `op.add_column()`, unlike `op.create_table()`, never creates
the enum type a column references). SQLite cannot expose this defect at
all (no native enum type — see tests/postgres_support.py), and neither
can Alembic's offline `--sql` mode (it prints DDL text without ever
executing it) — this test runs the *real* migration chain against a
*real*, freshly-emptied PostgreSQL schema, which is the only way this
class of defect is actually caught. If the enum-creation fix in 0005 is
ever reverted, this test fails with the same
`psycopg.errors.UndefinedObject` that a real fresh deployment would hit.

PostgreSQL-integration test — see tests/postgres_support.py. Skipped
automatically if no real PostgreSQL + pgvector server is reachable.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres


def _fresh_schema_engine():
    """A genuinely empty `public` schema on `PG_TEST_DATABASE_URL` —
    dropped and recreated, not merely `DROP TABLE IF EXISTS`-cleaned, so
    no leftover type/table from a previous run can mask a real failure."""
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    return engine


def _alembic_config() -> Config:
    # cwd is the backend/ directory for the whole test suite (see
    # pyproject.toml's pythonpath=["."]) — the same relative path the
    # `alembic` CLI itself is invoked with throughout this project.
    return Config("alembic.ini")


@requires_postgres
def test_fresh_postgres_database_migrates_through_head_with_no_manual_intervention(
    monkeypatch,
):
    """The core regression test: starting from a completely empty
    PostgreSQL schema, `alembic upgrade head` must succeed end to end
    through 0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 with no manual
    intervention (no pre-created enum types, no pre-enabled pgvector
    extension — migration 0006 enables that itself)."""
    engine = _fresh_schema_engine()
    try:
        # migrations/env.py reads settings.sqlalchemy_database_uri fresh
        # on every alembic invocation — pointing it at the test database
        # here is what makes `command.upgrade()` below target it instead
        # of the application's own configured database.
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)

        command.upgrade(_alembic_config(), "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0006"

            enum_types = {
                row[0]
                for row in conn.execute(
                    text("SELECT typname FROM pg_type WHERE typtype = 'e'")
                ).all()
            }
            assert "knowledge_chunk_content_type" in enum_types
            assert "knowledge_chunk_quality_status" in enum_types
            # Not dropped/redefined by this migration — still exactly
            # the type migration 0004 created.
            assert "extraction_method" in enum_types

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "knowledge_chunk_embeddings" in tables
            assert "knowledge_chunks" in tables
            assert "knowledge_documents" in tables
            assert "organizations" in tables

            extensions = {
                row[0] for row in conn.execute(text("SELECT extname FROM pg_extension")).all()
            }
            assert "vector" in extensions

            # The exact enum values match the application's own enums —
            # not just "a type with this name exists".
            content_type_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum WHERE enumtypid = "
                        "'knowledge_chunk_content_type'::regtype"
                    )
                ).all()
            }
            assert content_type_values == {"TEXT", "TABLE", "IMAGE", "STRUCTURED_RECORD"}

            quality_status_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum WHERE enumtypid = "
                        "'knowledge_chunk_quality_status'::regtype"
                    )
                ).all()
            }
            assert quality_status_values == {"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"}
    finally:
        engine.dispose()


@requires_postgres
def test_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """Downgrade to 0004 (removing 0005 and 0006's own changes) and
    upgrading back to head must both succeed, and must not damage any
    table/type that migration 0004 or earlier created — in particular,
    `extraction_method` must survive 0005's downgrade (only the two enum
    types 0005 itself created are ever dropped by it)."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0004")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0004"

            enum_types = {
                row[0]
                for row in conn.execute(
                    text("SELECT typname FROM pg_type WHERE typtype = 'e'")
                ).all()
            }
            assert "knowledge_chunk_content_type" not in enum_types
            assert "knowledge_chunk_quality_status" not in enum_types
            assert "extraction_method" in enum_types  # untouched by 0005's downgrade

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "knowledge_chunk_embeddings" not in tables
            assert "knowledge_chunks" in tables  # the table itself survives; only 0005's columns go

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0006"
    finally:
        engine.dispose()
