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
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.postgres_support import PG_TEST_DATABASE_URL, requires_postgres


def _current_head_revision(config: Config) -> str:
    """Resolves the migration chain's actual current head via Alembic's
    own `ScriptDirectory` API -- never a hardcoded literal. Every
    "still/now at head" assertion in this file must compare against
    this, not a string like `"0020"`, so a new migration becoming the
    new true head (e.g. `0021`) never re-breaks this test class the way
    SIE Milestone 34 did. (A `downgrade(config, "0017")` -- or any other
    *specific historical* target -- is a different thing entirely: that
    literal names the migration under test's own predecessor and is
    correct forever, regardless of where head later moves; only "head"
    itself is the moving target this helper exists for.)"""
    return ScriptDirectory.from_config(config).get_current_head()


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
    through 0001 -> ... -> 0011 with no manual intervention (no
    pre-created enum types, no pre-enabled pgvector extension —
    migration 0006 enables that itself)."""
    engine = _fresh_schema_engine()
    try:
        # migrations/env.py reads settings.sqlalchemy_database_uri fresh
        # on every alembic invocation — pointing it at the test database
        # here is what makes `command.upgrade()` below target it instead
        # of the application's own configured database.
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

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
            assert "safety_events" in tables
            assert "api_clients" in tables
            assert "feature_snapshots" in tables
            assert "model_registry_entries" in tables
            assert "predictions" in tables
            assert "dataset_versions" in tables
            assert "model_approvals" in tables
            assert "model_review_flags" in tables
            assert "prediction_outcomes" in tables
            assert "idempotency_keys" in tables
            assert "enterprise_ingestion_batches" in tables
            assert "enterprise_ingestion_records" in tables

            data_source_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'data_sources'"
                    )
                ).all()
            }
            assert "system_identifier" in data_source_columns
            assert "schema_version" in data_source_columns
            assert "config_metadata" in data_source_columns
            assert "api_client_id" in data_source_columns

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "source_record_version" in safety_event_columns
            assert "correlation_id" in safety_event_columns
            assert "source_schema_version" in safety_event_columns
            assert "ingestion_source_id" in safety_event_columns

            api_client_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'api_clients'"
                    )
                ).all()
            }
            assert "expires_at" in api_client_columns

            audit_log_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'audit_logs'"
                    )
                ).all()
            }
            assert "request_id" in audit_log_columns

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
def test_alembic_check_reports_no_drift_after_upgrade_head(monkeypatch):
    """Milestone 19A regression test — guards against a repeat of the
    `ix_knowledge_chunk_embeddings_model_identity` drift: migration 0006
    created that composite index via a raw `op.create_index(...)`, but
    `app/models/embedding.py` never declared a matching `Index(...)`, so
    every `alembic check`/`--autogenerate` run against a freshly migrated
    database proposed dropping a real, still-used index (see
    `app/models/embedding.py`'s own docstring on the `Index` now in its
    `__table_args__`, and `app/retrieval/retrieval_service.py`'s
    `_model_clause()`, which is the query that index actually speeds up).

    `alembic check` (`alembic.command.check`) runs the same
    autogenerate-diff comparison the real `alembic check` CLI command
    does, against a genuinely fresh, fully-migrated PostgreSQL schema —
    not SQLite, which cannot even represent this pgvector-adjacent index.
    It must find no diff: every model's metadata must exactly match what
    the full migration chain (0001 through head) actually produces.
    """
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)

        command.upgrade(_alembic_config(), "head")

        # Raises alembic.util.exc.AutogenerateDiffsDetected if the
        # database (as migrated) and the models' metadata disagree about
        # anything — the same failure this milestone's CI workflow
        # (.github/workflows/ci.yml) surfaces via the real `alembic
        # check` CLI command.
        command.check(_alembic_config())
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
            assert version == _current_head_revision(config)
    finally:
        engine.dispose()


@requires_postgres
def test_intelligence_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0007's own downgrade/re-upgrade round trip, isolated from the
    others above: `safety_events`/`api_clients` must both disappear on
    downgrade to 0006 and both reappear, correctly, on re-upgrade — and
    nothing 0006 or earlier created is disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0006")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0006"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "safety_events" not in tables
            assert "api_clients" not in tables
            # Untouched by 0007's downgrade.
            assert "knowledge_chunk_embeddings" in tables
            assert "organizations" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "safety_events" in tables
            assert "api_clients" in tables
    finally:
        engine.dispose()


@requires_postgres
def test_predictive_modeling_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0008's own downgrade/re-upgrade round trip, isolated from the
    others above: `feature_snapshots`/`model_registry_entries`/
    `predictions` must all disappear on downgrade to 0007 and all
    reappear, correctly, on re-upgrade — and nothing 0007 or earlier
    created is disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0007")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0007"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "feature_snapshots" not in tables
            assert "model_registry_entries" not in tables
            assert "predictions" not in tables
            # Untouched by 0008's downgrade.
            assert "safety_events" in tables
            assert "api_clients" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "feature_snapshots" in tables
            assert "model_registry_entries" in tables
            assert "predictions" in tables
    finally:
        engine.dispose()


@requires_postgres
def test_governance_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0009's own downgrade/re-upgrade round trip, isolated from the
    others above: `dataset_versions`/`model_approvals`/`model_review_flags`/
    `prediction_outcomes` must all disappear on downgrade to 0008, and
    `model_registry_entries.dataset_version_id` must disappear too — and
    all must reappear correctly on re-upgrade, with nothing 0008 or
    earlier disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0008")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0008"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "dataset_versions" not in tables
            assert "model_approvals" not in tables
            assert "model_review_flags" not in tables
            assert "prediction_outcomes" not in tables
            # Untouched by 0009's downgrade.
            assert "model_registry_entries" in tables
            assert "predictions" in tables
            assert "feature_snapshots" in tables

            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'model_registry_entries'"
                    )
                ).all()
            }
            assert "dataset_version_id" not in columns

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "dataset_versions" in tables
            assert "model_approvals" in tables
            assert "model_review_flags" in tables
            assert "prediction_outcomes" in tables

            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'model_registry_entries'"
                    )
                ).all()
            }
            assert "dataset_version_id" in columns
    finally:
        engine.dispose()


@requires_postgres
def test_enterprise_api_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0010's own downgrade/re-upgrade round trip, isolated from the
    others above: `idempotency_keys` must disappear on downgrade to
    0009, and `api_clients.expires_at`/`audit_logs.request_id` must both
    disappear too — and all must reappear correctly on re-upgrade, with
    nothing 0009 or earlier disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0009")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0009"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "idempotency_keys" not in tables
            # Untouched by 0010's downgrade.
            assert "dataset_versions" in tables
            assert "model_registry_entries" in tables

            api_client_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'api_clients'"
                    )
                ).all()
            }
            assert "expires_at" not in api_client_columns

            audit_log_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'audit_logs'"
                    )
                ).all()
            }
            assert "request_id" not in audit_log_columns

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "idempotency_keys" in tables

            api_client_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'api_clients'"
                    )
                ).all()
            }
            assert "expires_at" in api_client_columns

            audit_log_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'audit_logs'"
                    )
                ).all()
            }
            assert "request_id" in audit_log_columns
    finally:
        engine.dispose()


@requires_postgres
def test_data_ingestion_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0011's own downgrade/re-upgrade round trip, isolated from the
    others above: `enterprise_ingestion_batches`/`enterprise_ingestion_records`
    must both disappear on downgrade to 0010, and
    `data_sources.system_identifier`/`schema_version`/`config_metadata`/
    `api_client_id` and `safety_events.source_record_version`/
    `correlation_id`/`source_schema_version`/`ingestion_source_id` must
    all disappear too — and all must reappear correctly on re-upgrade,
    with nothing 0010 or earlier disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0010")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0010"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "enterprise_ingestion_batches" not in tables
            assert "enterprise_ingestion_records" not in tables
            # Untouched by 0011's downgrade.
            assert "idempotency_keys" in tables
            assert "data_sources" in tables
            assert "safety_events" in tables

            data_source_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'data_sources'"
                    )
                ).all()
            }
            assert "system_identifier" not in data_source_columns
            assert "schema_version" not in data_source_columns
            assert "config_metadata" not in data_source_columns
            assert "api_client_id" not in data_source_columns

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "source_record_version" not in safety_event_columns
            assert "correlation_id" not in safety_event_columns
            assert "source_schema_version" not in safety_event_columns
            assert "ingestion_source_id" not in safety_event_columns

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "enterprise_ingestion_batches" in tables
            assert "enterprise_ingestion_records" in tables

            data_source_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'data_sources'"
                    )
                ).all()
            }
            assert "system_identifier" in data_source_columns
            assert "api_client_id" in data_source_columns

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "source_record_version" in safety_event_columns
            assert "ingestion_source_id" in safety_event_columns
    finally:
        engine.dispose()


def test_enterprise_dataset_validation_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0012's own downgrade/re-upgrade round trip, isolated from the
    others above: `hse_expert_reviews` must disappear on downgrade to
    0011 and reappear correctly on re-upgrade, with nothing 0011 or
    earlier disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0011")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0011"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "hse_expert_reviews" not in tables
            # Untouched by 0012's downgrade.
            assert "enterprise_ingestion_batches" in tables
            assert "safety_events" in tables

        command.upgrade(config, "0012")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0012"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "hse_expert_reviews" in tables

            hse_review_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'hse_expert_reviews'"
                    )
                ).all()
            }
            assert "target_type" in hse_review_columns
            assert "target_reference" in hse_review_columns
            assert "provenance" in hse_review_columns
            assert "outcome" in hse_review_columns
            assert "organization_id" in hse_review_columns
    finally:
        engine.dispose()


def test_real_enterprise_terminology_ontology_calibration_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0013's own downgrade/re-upgrade round trip, isolated from the
    others above: `terminology_mapping_decisions` must disappear on
    downgrade to 0012 and reappear correctly on re-upgrade, with nothing
    0012 or earlier disturbed either way."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0012")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0012"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "terminology_mapping_decisions" not in tables
            # Untouched by 0013's downgrade.
            assert "hse_expert_reviews" in tables
            assert "enterprise_ingestion_batches" in tables
            assert "safety_events" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "terminology_mapping_decisions" in tables

            decision_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'terminology_mapping_decisions'"
                    )
                ).all()
            }
            assert "source_system" in decision_columns
            assert "domain" in decision_columns
            assert "context" in decision_columns
            assert "source_term" in decision_columns
            assert "normalized_term" in decision_columns
            assert "mapping_version" in decision_columns
            assert "status" in decision_columns
            assert "proposed_canonical_term" in decision_columns
            assert "reviewer_user_id" in decision_columns
            assert "hse_expert_review_id" in decision_columns
            assert "organization_id" in decision_columns
    finally:
        engine.dispose()


def test_sie_enterprise_ontology_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0014's own downgrade/re-upgrade round trip, isolated from the
    others above: `ontology_concepts` must disappear on downgrade to
    0013 and reappear correctly on re-upgrade, with nothing 0013 or
    earlier disturbed either way -- including `terminology_mapping_decisions`,
    proving 0014 never touches the terminology-calibration tables it sits
    on top of."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0013")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0013"

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "ontology_concepts" not in tables
            # Untouched by 0014's downgrade.
            assert "terminology_mapping_decisions" in tables
            assert "hse_expert_reviews" in tables
            assert "safety_events" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
            assert "ontology_concepts" in tables

            concept_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'ontology_concepts'"
                    )
                ).all()
            }
            assert "layer" in concept_columns
            assert "parent_domain" in concept_columns
            assert "concept_key" in concept_columns
            assert "definition" in concept_columns
            assert "justification" in concept_columns
            assert "status" in concept_columns
            assert "ontology_version" in concept_columns
            assert "proposed_by_user_id" in concept_columns
            assert "reviewer_user_id" in concept_columns
            # SIE Milestone 25A (migration 0017) added a NULLABLE
            # organization_id -- still not OrganizationScopedMixin (that
            # mixin is NOT NULL); NULL remains the GLOBAL, platform-wide
            # scope 0014 originally established. See
            # app/models/ontology_concept.py's own docstring.
            concept_org_id_column = next(
                row
                for row in conn.execute(
                    text(
                        "SELECT column_name, is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'ontology_concepts' "
                        "AND column_name = 'organization_id'"
                    )
                ).all()
            )
            assert concept_org_id_column[1] == "YES"
    finally:
        engine.dispose()


def test_actions_and_intervention_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0015's own downgrade/re-upgrade round trip (SIE Milestone 17:
    Actions & Intervention Foundation v0.1) -- `safety_actions`/
    `safety_action_history` must disappear on downgrade to 0014 and
    reappear correctly on re-upgrade, with nothing 0014 or earlier
    disturbed either way -- including `ontology_concepts`, proving 0015
    never touches the tables it sits on top of. Also exercises the
    native-enum-type downgrade path (0015's own docstring note on why
    that needs an explicit `sa.Enum(...).drop()`, unlike a plain
    `op.drop_table()` alone)."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0014")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0014"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "safety_actions" not in tables
            assert "safety_action_history" not in tables
            # Untouched by 0015's downgrade.
            assert "ontology_concepts" in tables
            assert "safety_events" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "safety_action_status" not in enum_types
            assert "safety_action_priority" not in enum_types
            assert "safety_action_type" not in enum_types
            # Not dropped/redefined by this migration's downgrade.
            assert "knowledge_verification_status" in enum_types

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "safety_actions" in tables
            assert "safety_action_history" in tables

            action_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_actions'"
                    )
                ).all()
            }
            assert "organization_id" in action_columns
            assert "site_id" in action_columns
            assert "source_event_id" in action_columns
            assert "owner_user_id" in action_columns
            assert "status" in action_columns
            assert "priority" in action_columns
            assert "action_type" in action_columns
            assert "completed_at" in action_columns
            assert "cancelled_at" in action_columns

            history_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_action_history'"
                    )
                ).all()
            }
            assert "action_id" in history_columns
            assert "organization_id" in history_columns
            assert "change_type" in history_columns
            assert "from_status" in history_columns
            assert "to_status" in history_columns
    finally:
        engine.dispose()


@requires_postgres
def test_risk_assessment_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """0016's own downgrade/re-upgrade round trip (SIE Milestone 25:
    Enterprise Risk Assessment Foundation v0.1) -- `risk_assessments`/
    `risk_assessment_findings`/`risk_assessment_controls`/
    `risk_assessment_finding_evidence` must disappear on downgrade to
    0015 and reappear correctly on re-upgrade, with nothing 0015 or
    earlier disturbed either way -- including `safety_actions`, proving
    0016 never touches the table it sits alongside. Also exercises the
    native-enum-type downgrade path for all ten new enum types (mirrors
    0015's own precedent -- see 0016's own docstring note)."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")
        command.downgrade(config, "0015")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0015"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessments" not in tables
            assert "risk_assessment_findings" not in tables
            assert "risk_assessment_controls" not in tables
            assert "risk_assessment_finding_evidence" not in tables
            # Untouched by 0016's downgrade.
            assert "safety_actions" in tables
            assert "ontology_concepts" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            for name in (
                "risk_assessment_scope", "risk_assessment_status", "risk_area", "risk_finding_source",
                "risk_finding_status", "risk_candidate_status", "risk_control_type", "risk_control_status",
                "risk_control_effectiveness", "risk_evidence_type",
            ):
                assert name not in enum_types
            # Not dropped/redefined by this migration's downgrade.
            assert "safety_action_status" in enum_types

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessments" in tables
            assert "risk_assessment_findings" in tables
            assert "risk_assessment_controls" in tables
            assert "risk_assessment_finding_evidence" in tables

            assessment_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessments'"
                    )
                ).all()
            }
            assert "organization_id" in assessment_columns
            assert "scope" in assessment_columns
            assert "site_id" in assessment_columns
            assert "status" in assessment_columns
            assert "lineage_id" in assessment_columns
            assert "version" in assessment_columns
            assert "supersedes_id" in assessment_columns
            assert "as_of" in assessment_columns
            assert "methodology_version" in assessment_columns

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "assessment_id" in finding_columns
            # SIE Milestone 25A: risk_area (a closed enum) was replaced by a
            # governed ontology-concept reference -- see
            # test_risk_assessment_ontology_taxonomy_migration_downgrade_then_reupgrade_round_trips_cleanly
            # below for the dedicated 0017 round-trip coverage.
            assert "risk_area" not in finding_columns
            assert "risk_area_concept_id" in finding_columns
            assert "risk_area_ontology_version" in finding_columns
            assert "candidate_status" in finding_columns
            assert "likelihood" in finding_columns
            assert "consequence" in finding_columns
            assert "inherent_risk_score" in finding_columns
            assert "residual_likelihood" in finding_columns
            assert "residual_risk_score" in finding_columns
    finally:
        engine.dispose()


@requires_postgres
def test_risk_assessment_ontology_taxonomy_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 25A: Governed Risk-Area & Organization-Extensible Risk
    Taxonomy v0.1 (migration 0017). Downgrading to 0016 must restore the
    original `risk_area` native enum column on `risk_assessment_findings`
    (correctly backfilled from the concept each existing finding's
    `risk_area_concept_id` referenced) and remove `ontology_concepts.
    organization_id`/`is_risk_area_eligible` -- with `risk_assessments`/
    `safety_actions`/`ontology_concepts` themselves untouched either way.
    Re-upgrading to head must recreate the Milestone 25A columns and
    reseed the 11 governed risk-area concepts identically."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            # A real finding exists at head, referencing a governed concept --
            # proves the downgrade path below actually backfills real data,
            # not merely an empty table.
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'Migration Test Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(text("SELECT id FROM organizations WHERE name = 'Migration Test Org'")).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'Migration Test Assessment', 'BASELINE', "
                    "'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, 'Migration test finding', "
                    "'MANUAL', 'OPEN', now(), now())"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id},
            )
            conn.commit()

        command.downgrade(config, "0016")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0016"

            # Untouched by 0017's downgrade.
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessments" in tables
            assert "ontology_concepts" in tables
            assert "safety_actions" in tables

            concept_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'ontology_concepts'"
                    )
                ).all()
            }
            assert "organization_id" not in concept_columns
            assert "is_risk_area_eligible" not in concept_columns

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "risk_area" in finding_columns
            assert "risk_area_concept_id" not in finding_columns
            assert "risk_area_ontology_version" not in finding_columns

            # The real finding's risk_area was correctly backfilled from
            # the concept it referenced (VEHICLE_INCIDENT -> VEHICLE_SAFETY).
            risk_area = conn.execute(
                text("SELECT risk_area FROM risk_assessment_findings WHERE title = 'Migration test finding'")
            ).scalar_one()
            assert risk_area == "VEHICLE_SAFETY"

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "risk_area" in enum_types

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            concept_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'ontology_concepts'"
                    )
                ).all()
            }
            assert "organization_id" in concept_columns
            assert "is_risk_area_eligible" in concept_columns

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "risk_area" not in finding_columns
            assert "risk_area_concept_id" in finding_columns
            assert "risk_area_ontology_version" in finding_columns

            eligible_count = conn.execute(
                text("SELECT count(*) FROM ontology_concepts WHERE is_risk_area_eligible = TRUE AND organization_id IS NULL")
            ).scalar_one()
            assert eligible_count == 11

            # The finding created before the downgrade correctly resolves
            # back to VEHICLE_INCIDENT after the round trip.
            concept_key = conn.execute(
                text(
                    "SELECT c.concept_key FROM risk_assessment_findings f "
                    "JOIN ontology_concepts c ON c.id = f.risk_area_concept_id "
                    "WHERE f.title = 'Migration test finding'"
                )
            ).scalar_one()
            assert concept_key == "VEHICLE_INCIDENT"
    finally:
        engine.dispose()


@requires_postgres
def test_formal_risk_assessment_engine_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 26: Formal Enterprise Risk Assessment Engine v0.2
    (migration 0018). Downgrading to 0017 must remove `reference`/
    `assessment_type` from `risk_assessments`, remove `linked_action_id`/
    `inherent_risk_methodology_version`/`residual_risk_methodology_version`
    from `risk_assessment_findings`, drop `risk_assessment_history`
    entirely, and rebuild `risk_assessment_status` without `ARCHIVED` --
    with `risk_assessments`/`risk_assessment_findings`/`safety_actions`/
    `ontology_concepts` themselves (and their real data) otherwise
    untouched. Re-upgrading to head must recreate every 0018 column/table,
    backfill `assessment_type='BASELINE'` for the pre-existing row, and
    re-add the `ARCHIVED` enum value."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M26 Migration Test Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE name = 'M26 Migration Test Org'")
            ).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, reference, assessment_type, "
                    "status, lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'M26 Migration Test Assessment', "
                    "'RA-MIGRATION-0001', 'PERIODIC', 'DRAFT', gen_random_uuid(), 1, now(), now(), 30, "
                    "'risk-assessment-v1', now(), now()) RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            action_id = conn.execute(
                text(
                    "INSERT INTO safety_actions (id, organization_id, title, action_type, priority, status, "
                    "attributes, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'M26 Migration Test Action', 'CORRECTIVE', 'MEDIUM', "
                    "'OPEN', '{}'::jsonb, now(), now()) RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, likelihood, consequence, "
                    "inherent_risk_score, inherent_risk_classification, inherent_risk_methodology_version, "
                    "linked_action_id, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, "
                    "'M26 Migration test finding', 'MANUAL', 'OPEN', 4, 4, 16, 'HIGH', 'risk-assessment-v1', "
                    ":action_id, now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id, "action_id": action_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_history (id, organization_id, assessment_id, finding_id, "
                    "change_type, to_status, created_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :finding_id, 'FINDING_CREATED', 'OPEN', now())"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "finding_id": finding_id},
            )
            conn.commit()

        command.downgrade(config, "0017")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0017"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_history" not in tables
            # Untouched by 0018's downgrade.
            assert "risk_assessments" in tables
            assert "risk_assessment_findings" in tables
            assert "safety_actions" in tables
            assert "ontology_concepts" in tables

            assessment_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessments'"
                    )
                ).all()
            }
            assert "reference" not in assessment_columns
            assert "assessment_type" not in assessment_columns

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "linked_action_id" not in finding_columns
            assert "inherent_risk_methodology_version" not in finding_columns
            assert "residual_risk_methodology_version" not in finding_columns
            # 0017-era columns, untouched.
            assert "risk_area_concept_id" in finding_columns

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "risk_assessment_type" not in enum_types
            status_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'risk_assessment_status'"
                    )
                ).all()
            }
            assert "ARCHIVED" not in status_values
            assert status_values == {"DRAFT", "IN_REVIEW", "APPROVED", "SUPERSEDED"}

            # The real assessment/finding survive the downgrade (only the
            # 0018-added columns are gone) -- proving this is a genuine
            # column-level round trip, not a table rebuild.
            title = conn.execute(
                text("SELECT title FROM risk_assessments WHERE id = :id"), {"id": assessment_id}
            ).scalar_one()
            assert title == "M26 Migration Test Assessment"
            inherent_score = conn.execute(
                text("SELECT inherent_risk_score FROM risk_assessment_findings WHERE id = :id"), {"id": finding_id}
            ).scalar_one()
            assert inherent_score == 16

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_history" in tables

            assessment_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessments'"
                    )
                ).all()
            }
            assert "reference" in assessment_columns
            assert "assessment_type" in assessment_columns

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "linked_action_id" in finding_columns
            assert "inherent_risk_methodology_version" in finding_columns
            assert "residual_risk_methodology_version" in finding_columns

            status_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'risk_assessment_status'"
                    )
                ).all()
            }
            assert "ARCHIVED" in status_values

            # Migration 0018's own backfill semantics: a pre-existing row
            # (which could not have declared a type that didn't yet exist)
            # is backfilled to 'BASELINE' regardless of what it had before
            # its own downgrade -- reference is a plain column, so it is
            # simply gone (never backfilled from anywhere, since it was
            # dropped entirely on downgrade).
            assessment_type, reference = conn.execute(
                text("SELECT assessment_type, reference FROM risk_assessments WHERE id = :id"), {"id": assessment_id}
            ).one()
            assert assessment_type == "BASELINE"
            assert reference is None

            # The finding's already-set inherent_risk_score is correctly
            # backfilled to the current methodology version, and its
            # linked_action_id/history are simply gone (the columns/table
            # were dropped and recreated empty) -- expected, not a defect:
            # the downgrade already refuses (see the dedicated guard test
            # below) whenever data would be silently misrepresented, and
            # a dropped-and-recreated nullable FK/append-only-history
            # column is not that.
            inherent_version, linked_action_id = conn.execute(
                text(
                    "SELECT inherent_risk_methodology_version, linked_action_id FROM risk_assessment_findings "
                    "WHERE id = :id"
                ),
                {"id": finding_id},
            ).one()
            assert inherent_version == "risk-assessment-v1"
            assert linked_action_id is None
            history_count = conn.execute(
                text("SELECT count(*) FROM risk_assessment_history WHERE assessment_id = :id"), {"id": assessment_id}
            ).scalar_one()
            assert history_count == 0
    finally:
        engine.dispose()


@requires_postgres
def test_formal_risk_assessment_engine_migration_downgrade_refuses_while_an_archived_assessment_exists(monkeypatch):
    """Migration 0018's own explicit downgrade guard: `ARCHIVED` has no
    meaning in the schema being downgraded to, so the downgrade must
    raise rather than silently mis-cast an `ARCHIVED` row to some other
    status."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M26 Guard Test Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(text("SELECT id FROM organizations WHERE name = 'M26 Guard Test Org'")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'Archived Assessment', 'BASELINE', "
                    "'ARCHIVED', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now())"
                ),
                {"org_id": org_id},
            )
            conn.commit()

        try:
            command.downgrade(config, "0017")
            raised = False
        except RuntimeError:
            raised = True
        assert raised, "downgrade must refuse while an ARCHIVED risk_assessments row exists"

        with engine.connect() as conn:
            # The failed downgrade must not have left the schema
            # half-migrated -- still at head.
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)
    finally:
        engine.dispose()


@requires_postgres
def test_finding_action_relationship_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 27: Risk Assessment & Action Management Integration
    v0.1 (migration 0019). Downgrading to 0018 must drop
    `risk_assessment_finding_actions` entirely while leaving
    `risk_assessment_findings.linked_action_id` (and every other 0018-era
    column) untouched -- the relationship table is purely additive.
    Re-upgrading to head must recreate the table and re-backfill it from
    the (never-modified) `linked_action_id` data, exactly reproducing the
    relationship that existed before the downgrade."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M27 Migration Test Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE name = 'M27 Migration Test Org'")
            ).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'M27 Migration Test Assessment', "
                    "'BASELINE', 'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            action_id = conn.execute(
                text(
                    "INSERT INTO safety_actions (id, organization_id, title, action_type, priority, status, "
                    "attributes, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'M27 Migration Test Action', 'CORRECTIVE', 'MEDIUM', "
                    "'OPEN', '{}'::jsonb, now(), now()) RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, linked_action_id, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, "
                    "'M27 Migration test finding', 'MANUAL', 'OPEN', :action_id, now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id, "action_id": action_id},
            ).scalar_one()
            conn.commit()

        with engine.connect() as conn:
            relationship_count = conn.execute(
                text(
                    "SELECT count(*) FROM risk_assessment_finding_actions "
                    "WHERE finding_id = :finding_id AND action_id = :action_id"
                ),
                {"finding_id": finding_id, "action_id": action_id},
            ).scalar_one()
            assert relationship_count == 0  # not backfilled -- this finding was inserted after 0019 already ran

        command.downgrade(config, "0018")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0018"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_finding_actions" not in tables
            # Untouched by 0019's downgrade.
            assert "risk_assessment_findings" in tables
            assert "safety_actions" in tables

            finding_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_findings'"
                    )
                ).all()
            }
            assert "linked_action_id" in finding_columns

            # linked_action_id itself is completely untouched by 0019's
            # downgrade -- the legacy single-action pointer survives.
            still_linked = conn.execute(
                text("SELECT linked_action_id FROM risk_assessment_findings WHERE id = :id"), {"id": finding_id}
            ).scalar_one()
            assert still_linked == action_id

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_finding_actions" in tables

            # Re-upgrading re-backfills from linked_action_id -- the
            # relationship that existed before the downgrade is restored.
            relationship_count = conn.execute(
                text(
                    "SELECT count(*) FROM risk_assessment_finding_actions "
                    "WHERE finding_id = :finding_id AND action_id = :action_id"
                ),
                {"finding_id": finding_id, "action_id": action_id},
            ).scalar_one()
            assert relationship_count == 1
    finally:
        engine.dispose()


@requires_postgres
def test_finding_action_relationship_migration_preserves_existing_m26_data_on_fresh_upgrade(monkeypatch):
    """SIE Milestone 27's own explicit "existing M26 data preserved"
    requirement: a `linked_action_id` set entirely under the pre-0019
    schema (i.e. real Milestone 26 data, never touched by this
    milestone's own application code) is correctly backfilled into
    `risk_assessment_finding_actions` the first time `alembic upgrade
    head` ever runs migration 0019 against it."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "0018")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M26 Data Preservation Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE name = 'M26 Data Preservation Org'")
            ).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'Pre-0019 Assessment', "
                    "'BASELINE', 'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            action_id = conn.execute(
                text(
                    "INSERT INTO safety_actions (id, organization_id, title, action_type, priority, status, "
                    "attributes, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'Pre-0019 Action', 'CORRECTIVE', 'MEDIUM', "
                    "'OPEN', '{}'::jsonb, now(), now()) RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, linked_action_id, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, "
                    "'Pre-0019 finding', 'MANUAL', 'OPEN', :action_id, now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id, "action_id": action_id},
            ).scalar_one()
            conn.commit()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            relationship = conn.execute(
                text(
                    "SELECT organization_id, finding_id, action_id FROM risk_assessment_finding_actions "
                    "WHERE finding_id = :finding_id"
                ),
                {"finding_id": finding_id},
            ).one()
            assert relationship.organization_id == org_id
            assert relationship.finding_id == finding_id
            assert relationship.action_id == action_id

            # linked_action_id itself is untouched -- still set, exactly
            # as the pre-0019 data had it.
            still_linked = conn.execute(
                text("SELECT linked_action_id FROM risk_assessment_findings WHERE id = :id"), {"id": finding_id}
            ).scalar_one()
            assert still_linked == action_id
    finally:
        engine.dispose()


@requires_postgres
def test_control_effectiveness_evidence_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
    Effectiveness Foundation v0.1 (migration 0020). Downgrading to 0019
    must drop `risk_assessment_control_evidence` entirely, drop the three
    new `risk_assessment_controls` columns, and drop
    `risk_assessment_history.control_id` -- while leaving the control's
    own pre-existing fields (`description`/`control_type`/`status`/
    `effectiveness`) and every 0019-era table/column untouched.
    Re-upgrading to head must recreate every dropped column/table (empty
    -- this migration performs no backfill, unlike 0019's own)."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M29 Migration Test Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE name = 'M29 Migration Test Org'")
            ).scalar_one()
            user_id = conn.execute(
                text(
                    "INSERT INTO users (id, email, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'm29-migration-test@example.com', 'M29 Tester', 'active', now(), now()) "
                    "RETURNING id"
                )
            ).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'M29 Migration Test Assessment', "
                    "'BASELINE', 'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, "
                    "'M29 Migration test finding', 'MANUAL', 'OPEN', now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id},
            ).scalar_one()
            control_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_controls (id, organization_id, finding_id, description, "
                    "control_type, status, effectiveness, effectiveness_rationale, assessed_at, "
                    "assessed_by_user_id, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :finding_id, 'M29 Migration test control', "
                    "'ENGINEERING', 'IN_PLACE', 'EFFECTIVE', 'Verified via inspection.', now(), :user_id, "
                    "now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "finding_id": finding_id, "user_id": user_id},
            ).scalar_one()
            evidence_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_finding_evidence (id, organization_id, finding_id, evidence_type, "
                    "reference_label, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :finding_id, 'OTHER', 'M29 migration test evidence', "
                    "now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "finding_id": finding_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_control_evidence (id, organization_id, control_id, "
                    "finding_evidence_id, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :control_id, :evidence_id, now(), now())"
                ),
                {"org_id": org_id, "control_id": control_id, "evidence_id": evidence_id},
            )
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_history (id, organization_id, assessment_id, finding_id, "
                    "control_id, change_type, created_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :finding_id, :control_id, "
                    "'CONTROL_CREATED', now())"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "finding_id": finding_id, "control_id": control_id},
            )
            conn.commit()

        command.downgrade(config, "0019")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0019"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_control_evidence" not in tables
            assert "risk_assessment_controls" in tables  # untouched table, only columns removed

            control_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_controls'"
                    )
                ).all()
            }
            assert "effectiveness_rationale" not in control_columns
            assert "assessed_at" not in control_columns
            assert "assessed_by_user_id" not in control_columns

            history_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'risk_assessment_history'"
                    )
                ).all()
            }
            assert "control_id" not in history_columns

            # The control row itself, and its pre-existing fields, survive untouched.
            surviving = conn.execute(
                text(
                    "SELECT description, control_type, status, effectiveness FROM risk_assessment_controls "
                    "WHERE id = :id"
                ),
                {"id": control_id},
            ).one()
            assert surviving.description == "M29 Migration test control"
            assert surviving.control_type == "ENGINEERING"
            assert surviving.status == "IN_PLACE"
            assert surviving.effectiveness == "EFFECTIVE"

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "risk_assessment_control_evidence" in tables

            # New columns are back, NULL (this migration performs no backfill).
            reupgraded = conn.execute(
                text(
                    "SELECT effectiveness_rationale, assessed_at, assessed_by_user_id "
                    "FROM risk_assessment_controls WHERE id = :id"
                ),
                {"id": control_id},
            ).one()
            assert reupgraded.effectiveness_rationale is None
            assert reupgraded.assessed_at is None
            assert reupgraded.assessed_by_user_id is None

            # The control-evidence link dropped by the downgrade is gone,
            # not silently restored -- re-upgrading a purely additive
            # migration recreates empty structure, never resurrects rows
            # a downgrade legitimately deleted.
            link_count = conn.execute(
                text("SELECT count(*) FROM risk_assessment_control_evidence WHERE control_id = :id"),
                {"id": control_id},
            ).scalar_one()
            assert link_count == 0

            # The control row's own pre-existing fields are still intact.
            still_there = conn.execute(
                text("SELECT description, control_type, status, effectiveness FROM risk_assessment_controls WHERE id = :id"),
                {"id": control_id},
            ).one()
            assert still_there.description == "M29 Migration test control"
            assert still_there.control_type == "ENGINEERING"
            assert still_there.status == "IN_PLACE"
            assert still_there.effectiveness == "EFFECTIVE"
    finally:
        engine.dispose()


@requires_postgres
def test_control_effectiveness_evidence_migration_downgrade_refuses_with_new_control_type_value(monkeypatch):
    """Migration 0020's own explicit downgrade guard: `control_type =
    'OTHER'` has no meaning in the schema being downgraded to, so the
    downgrade must raise rather than silently mis-cast it."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M29 Type Guard Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(text("SELECT id FROM organizations WHERE name = 'M29 Type Guard Org'")).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'M29 Type Guard Assessment', 'BASELINE', "
                    "'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, 'Guard finding', 'MANUAL', "
                    "'OPEN', now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_controls (id, organization_id, finding_id, description, "
                    "control_type, status, effectiveness, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :finding_id, 'Other-type control', 'OTHER', 'PROPOSED', "
                    "'NOT_ASSESSED', now(), now())"
                ),
                {"org_id": org_id, "finding_id": finding_id},
            )
            conn.commit()

        try:
            command.downgrade(config, "0019")
            raised = False
        except RuntimeError:
            raised = True
        assert raised, "downgrade must refuse while a control_type='OTHER' row exists"

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)
    finally:
        engine.dispose()


@requires_postgres
def test_control_effectiveness_evidence_migration_downgrade_refuses_with_new_status_value(monkeypatch):
    """Migration 0020's own explicit downgrade guard: `status =
    'NOT_VERIFIED'`/`'PARTIALLY_IMPLEMENTED'` have no meaning in the
    schema being downgraded to, so the downgrade must raise rather than
    silently mis-cast either."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'M29 Status Guard Org', 'active', now(), now())"
                )
            )
            org_id = conn.execute(text("SELECT id FROM organizations WHERE name = 'M29 Status Guard Org'")).scalar_one()
            concept_id = conn.execute(
                text("SELECT id FROM ontology_concepts WHERE organization_id IS NULL AND concept_key = 'VEHICLE_INCIDENT'")
            ).scalar_one()
            assessment_id = conn.execute(
                text(
                    "INSERT INTO risk_assessments (id, organization_id, scope, title, assessment_type, status, "
                    "lineage_id, version, assessment_date, as_of, window_days, methodology_version, "
                    "created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, 'ORGANIZATION', 'M29 Status Guard Assessment', 'BASELINE', "
                    "'DRAFT', gen_random_uuid(), 1, now(), now(), 30, 'risk-assessment-v1', now(), now()) "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).scalar_one()
            finding_id = conn.execute(
                text(
                    "INSERT INTO risk_assessment_findings (id, organization_id, assessment_id, risk_area_concept_id, "
                    "risk_area_ontology_version, title, source, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :assessment_id, :concept_id, 1, 'Guard finding', 'MANUAL', "
                    "'OPEN', now(), now()) RETURNING id"
                ),
                {"org_id": org_id, "assessment_id": assessment_id, "concept_id": concept_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO risk_assessment_controls (id, organization_id, finding_id, description, "
                    "control_type, status, effectiveness, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :org_id, :finding_id, 'Not-verified control', 'PPE', 'NOT_VERIFIED', "
                    "'NOT_ASSESSED', now(), now())"
                ),
                {"org_id": org_id, "finding_id": finding_id},
            )
            conn.commit()

        try:
            command.downgrade(config, "0019")
            raised = False
        except RuntimeError:
            raised = True
        assert raised, "downgrade must refuse while a status='NOT_VERIFIED' row exists"

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)
    finally:
        engine.dispose()


@requires_postgres
def test_intelligence_decision_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 34: Human Decision & Intervention Trace (migration
    0021). Downgrading to 0020 must drop `intelligence_decisions`
    entirely, along with its own native `intelligence_decision_type`
    enum type, while leaving every 0020-and-earlier table/type/enum
    value untouched. Re-upgrading to head must recreate the table and
    enum type correctly, with every decision-type value intact."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "intelligence_decisions" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "intelligence_decision_type" in enum_types

            decision_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'intelligence_decision_type'"
                    )
                ).all()
            }
            assert decision_values == {"ACT", "DO_NOT_ACT", "DEFER", "ALREADY_ADDRESSED", "NOT_RELEVANT"}

        command.downgrade(config, "0020")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0020"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "intelligence_decisions" not in tables
            # Untouched by 0021's downgrade.
            assert "risk_assessment_control_evidence" in tables
            assert "risk_assessments" in tables
            assert "safety_actions" in tables
            assert "ontology_concepts" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "intelligence_decision_type" not in enum_types
            # Not dropped/redefined by this migration's downgrade.
            assert "risk_control_effectiveness" in enum_types

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "intelligence_decisions" in tables

            decision_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'intelligence_decisions'"
                    )
                ).all()
            }
            assert "organization_id" in decision_columns
            assert "site_id" in decision_columns
            assert "attention_reference" in decision_columns
            assert "attention_category" in decision_columns
            assert "attention_priority" in decision_columns
            assert "decision" in decision_columns
            assert "rationale" in decision_columns
            assert "linked_action_id" in decision_columns
            assert "decided_by_user_id" in decision_columns
            assert "decided_by_api_client_id" in decision_columns
            assert "decided_at" in decision_columns

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "intelligence_decision_type" in enum_types

            decision_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'intelligence_decision_type'"
                    )
                ).all()
            }
            assert decision_values == {"ACT", "DO_NOT_ACT", "DEFER", "ALREADY_ADDRESSED", "NOT_RELEVANT"}
    finally:
        engine.dispose()


@requires_postgres
def test_project_and_project_site_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 35: Organizational & Operational Scope Foundation
    v0.1 (migration 0022). Downgrading to 0021 must drop `project_sites`
    and `projects` entirely, along with the native `project_status` enum
    type, while leaving every 0021-and-earlier table/type/enum value
    untouched. Re-upgrading to head must recreate both tables and the
    enum type correctly, with every status value intact."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "projects" in tables
            assert "project_sites" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "project_status" in enum_types

            status_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'project_status'"
                    )
                ).all()
            }
            assert status_values == {"ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED"}

        command.downgrade(config, "0021")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0021"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "projects" not in tables
            assert "project_sites" not in tables
            # Untouched by 0022's downgrade.
            assert "intelligence_decisions" in tables
            assert "sites" in tables
            assert "safety_actions" in tables

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "project_status" not in enum_types
            # Not dropped/redefined by this migration's downgrade.
            assert "intelligence_decision_type" in enum_types

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "projects" in tables
            assert "project_sites" in tables

            project_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'projects'"
                    )
                ).all()
            }
            assert "organization_id" in project_columns
            assert "name" in project_columns
            assert "code" in project_columns
            assert "status" in project_columns
            assert "description" in project_columns

            project_site_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'project_sites'"
                    )
                ).all()
            }
            assert "project_id" in project_site_columns
            assert "site_id" in project_site_columns
            assert "organization_id" in project_site_columns

            enum_types = {row[0] for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'")).all()}
            assert "project_status" in enum_types

            status_values = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'project_status'"
                    )
                ).all()
            }
            assert status_values == {"ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED"}
    finally:
        engine.dispose()


@requires_postgres
def test_safety_event_project_attribution_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 35A: Canonical Project Attribution Correction
    (migration 0023). Downgrading to 0022 must remove
    `safety_events.attributed_project_id` and the tenant-integrity
    hardening (composite `project_sites` foreign keys,
    `UNIQUE(id, organization_id)` on `sites`/`projects`) entirely, with
    everything 0022-and-earlier untouched. Re-upgrading to head must
    recreate all of it correctly."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "attributed_project_id" in safety_event_columns

            unique_constraints = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND constraint_type = 'UNIQUE'"
                    )
                ).all()
            }
            assert "uq_sites_id_organization_id" in unique_constraints
            assert "uq_projects_id_organization_id" in unique_constraints

            project_sites_fks = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND table_name = 'project_sites' "
                        "AND constraint_type = 'FOREIGN KEY'"
                    )
                ).all()
            }
            assert "fk_project_sites_project_id_organization_id" in project_sites_fks
            assert "fk_project_sites_site_id_organization_id" in project_sites_fks

        command.downgrade(config, "0022")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0022"

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "attributed_project_id" not in safety_event_columns
            # Untouched by 0023's downgrade.
            assert "site_id" in safety_event_columns
            assert "project" in safety_event_columns  # the pre-existing free-text column, never removed

            unique_constraints = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND constraint_type = 'UNIQUE'"
                    )
                ).all()
            }
            assert "uq_sites_id_organization_id" not in unique_constraints
            assert "uq_projects_id_organization_id" not in unique_constraints

            project_sites_fks = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND table_name = 'project_sites' "
                        "AND constraint_type = 'FOREIGN KEY'"
                    )
                ).all()
            }
            assert "fk_project_sites_project_id_organization_id" not in project_sites_fks
            assert "fk_project_sites_site_id_organization_id" not in project_sites_fks

            # Untouched by 0023's downgrade -- projects/project_sites
            # tables themselves (0022's own) still exist.
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "projects" in tables
            assert "project_sites" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "attributed_project_id" in safety_event_columns

            unique_constraints = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND constraint_type = 'UNIQUE'"
                    )
                ).all()
            }
            assert "uq_sites_id_organization_id" in unique_constraints
            assert "uq_projects_id_organization_id" in unique_constraints
    finally:
        engine.dispose()


@requires_postgres
def test_project_sites_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level(monkeypatch):
    """SIE Milestone 35A: proves the tenant-integrity hardening is a
    genuine, schema-level guarantee -- not merely application-checked.
    Bypasses the service layer entirely (raw SQL `INSERT`) and asserts
    PostgreSQL itself rejects a `project_sites` row whose
    `organization_id` does not match its referenced project's/site's
    own -- exactly the gap SIE Milestone 35's own first cut left open
    (see app/models/project_site.py's own docstring)."""
    import uuid

    import psycopg
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()
        command.upgrade(config, "head")

        with engine.connect() as conn:
            org_a = uuid.uuid4()
            org_b = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (:id, 'Org A', 'active', now(), now())"
                ),
                {"id": org_a},
            )
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (:id, 'Org B', 'active', now(), now())"
                ),
                {"id": org_b},
            )
            project_a = uuid.uuid4()
            site_b = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO projects (id, organization_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :org_id, 'Project Alpha', 'ACTIVE', now(), now())"
                ),
                {"id": project_a, "org_id": org_a},
            )
            conn.execute(
                text(
                    "INSERT INTO sites (id, organization_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :org_id, 'Org B Site', 'active', now(), now())"
                ),
                {"id": site_b, "org_id": org_b},
            )
            conn.commit()

            # The forbidden row: project_a (org_a) linked to site_b
            # (org_b), claiming organization_id=org_a. A plain
            # single-column FK on each of project_id/site_id would
            # happily accept this (both ids individually exist); the
            # composite FK must not.
            with pytest.raises((IntegrityError, psycopg.errors.ForeignKeyViolation)):
                conn.execute(
                    text(
                        "INSERT INTO project_sites (id, organization_id, project_id, site_id, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :org_id, :project_id, :site_id, now(), now())"
                    ),
                    {"org_id": org_a, "project_id": project_a, "site_id": site_b},
                )
                conn.commit()
            # The failed INSERT leaves the connection's transaction
            # aborted (real Postgres semantics) -- roll it back
            # explicitly rather than relying on __exit__ to do the
            # right thing.
            conn.rollback()
    finally:
        engine.dispose()


@requires_postgres
def test_project_attribution_history_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 35B: Project Attribution Temporal Integrity
    (migration 0024). Downgrading to 0023 must remove
    `safety_event_project_attribution_history` entirely, with everything
    0023-and-earlier untouched. Re-upgrading to head must recreate it
    correctly."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "safety_event_project_attribution_history" in tables

            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                        "AND table_name = 'safety_event_project_attribution_history'"
                    )
                ).all()
            }
            assert {"event_id", "project_id", "action", "created_at", "organization_id"} <= columns

        command.downgrade(config, "0023")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0023"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "safety_event_project_attribution_history" not in tables
            # Untouched by 0024's downgrade.
            assert "safety_events" in tables
            assert "project_sites" in tables

            safety_event_columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'safety_events'"
                    )
                ).all()
            }
            assert "attributed_project_id" in safety_event_columns  # 0023's own, not touched by 0024

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "safety_event_project_attribution_history" in tables
    finally:
        engine.dispose()


@requires_postgres
def test_project_attribution_history_migration_backfills_existing_current_state_attributions(monkeypatch):
    """SIE Milestone 35B's own explicit backfill requirement: a
    `safety_events` row with `attributed_project_id` already set (from
    SIE Milestone 35A-era code, before this history table existed) must
    not silently vanish from every project-filtered query the moment
    migration 0024 lands -- it needs a synthesized `ATTRIBUTED` history
    row, using the event's own `updated_at` as the best-available
    "when this was set" signal. Proven by inserting such a row *before*
    running 0024, then asserting the backfilled history row appears with
    exactly that timestamp."""
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.project_enums import ProjectStatus
    from tests.intelligence_test_helpers import make_safety_event

    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "0023")

        with Session(engine) as session:
            org = Organization(name="Backfill Test Org")
            session.add(org)
            session.commit()

            project = Project(organization_id=org.id, name="Backfill Project", status=ProjectStatus.ACTIVE)
            session.add(project)
            session.commit()

            event = make_safety_event(organization_id=org.id, site_id=None, source_record_id="backfill-event")
            event.attributed_project_id = project.id
            session.add(event)
            session.commit()
            event_id = event.id
            project_id = project.id

        # Force a specific, known updated_at -- distinct from created_at
        # -- so the assertion below proves the migration reads
        # updated_at specifically, not merely "some" timestamp.
        forced_updated_at = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE safety_events SET updated_at = :updated_at WHERE id = :id"),
                {"updated_at": forced_updated_at, "id": event_id},
            )

        command.upgrade(config, "head")

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT project_id, action, created_at FROM safety_event_project_attribution_history "
                    "WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            ).all()
            assert len(rows) == 1
            backfilled_project_id, action, created_at = rows[0]
            assert backfilled_project_id == project_id
            assert action == "ATTRIBUTED"
            assert created_at == forced_updated_at
    finally:
        engine.dispose()


@requires_postgres
def test_project_site_history_migration_downgrade_then_reupgrade_round_trips_cleanly(monkeypatch):
    """SIE Milestone 36: Project/Site Temporal Scope Integrity
    (migration 0025). Downgrading to 0024 must remove
    `project_site_history` entirely, with everything 0024-and-earlier
    untouched. Re-upgrading to head must recreate it correctly."""
    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "project_site_history" in tables

            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                        "AND table_name = 'project_site_history'"
                    )
                ).all()
            }
            assert {"project_id", "site_id", "action", "created_at", "organization_id"} <= columns

            fks = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND table_name = 'project_site_history' "
                        "AND constraint_type = 'FOREIGN KEY'"
                    )
                ).all()
            }
            assert "fk_project_site_history_project_id_organization_id" in fks
            assert "fk_project_site_history_site_id_organization_id" in fks

        command.downgrade(config, "0024")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0024"

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "project_site_history" not in tables
            # Untouched by 0025's downgrade.
            assert "project_sites" in tables
            assert "safety_event_project_attribution_history" in tables

        command.upgrade(config, "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == _current_head_revision(config)

            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                ).all()
            }
            assert "project_site_history" in tables
    finally:
        engine.dispose()


@requires_postgres
def test_project_site_history_migration_backfills_existing_project_sites_rows(monkeypatch):
    """SIE Milestone 36's own explicit backfill requirement: an existing
    `project_sites` row must not silently vanish from historical
    reconstruction the moment migration 0025 lands -- it needs a
    synthesized `LINKED` history row. Unlike SIE Milestone 35B's own
    backfill (which had to approximate via `updated_at`), this one uses
    `project_sites.created_at` -- the *actual* link creation timestamp,
    since `ProjectSite` rows are never updated after creation -- proven
    here by asserting exact equality, not merely "close enough"."""
    import uuid

    from sqlalchemy.orm import Session

    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.project_enums import ProjectStatus
    from app.models.project_site import ProjectSite
    from app.models.site import Site

    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()

        command.upgrade(config, "0024")

        with Session(engine) as session:
            org = Organization(name="Backfill Test Org")
            session.add(org)
            session.commit()

            project = Project(organization_id=org.id, name="Backfill Project", status=ProjectStatus.ACTIVE)
            site = Site(organization_id=org.id, name="Backfill Site")
            session.add_all([project, site])
            session.commit()

            link = ProjectSite(organization_id=org.id, project_id=project.id, site_id=site.id)
            session.add(link)
            session.commit()
            project_id, site_id, link_created_at = project.id, site.id, link.created_at

        command.upgrade(config, "head")

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT action, created_at FROM project_site_history "
                    "WHERE project_id = :project_id AND site_id = :site_id"
                ),
                {"project_id": project_id, "site_id": site_id},
            ).all()
            assert len(rows) == 1
            action, created_at = rows[0]
            assert action == "LINKED"
            assert created_at == link_created_at
    finally:
        engine.dispose()


@requires_postgres
def test_project_site_history_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level(monkeypatch):
    """SIE Milestone 36 item 8: tenant integrity is schema-enforced, not
    merely application-checked -- mirrors
    test_project_sites_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level
    (SIE Milestone 35A) exactly, applied to `project_site_history`."""
    import uuid

    import psycopg
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine = _fresh_schema_engine()
    try:
        monkeypatch.setattr("app.core.config.settings.DATABASE_URL", PG_TEST_DATABASE_URL)
        config = _alembic_config()
        command.upgrade(config, "head")

        with engine.connect() as conn:
            org_a = uuid.uuid4()
            org_b = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (:id, 'Org A', 'active', now(), now())"
                ),
                {"id": org_a},
            )
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, status, created_at, updated_at) "
                    "VALUES (:id, 'Org B', 'active', now(), now())"
                ),
                {"id": org_b},
            )
            project_a = uuid.uuid4()
            site_b = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO projects (id, organization_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :org_id, 'Project Alpha', 'ACTIVE', now(), now())"
                ),
                {"id": project_a, "org_id": org_a},
            )
            conn.execute(
                text(
                    "INSERT INTO sites (id, organization_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :org_id, 'Org B Site', 'active', now(), now())"
                ),
                {"id": site_b, "org_id": org_b},
            )
            conn.commit()

            # The forbidden row: project_a (org_a) paired with site_b
            # (org_b), claiming organization_id=org_a.
            with pytest.raises((IntegrityError, psycopg.errors.ForeignKeyViolation)):
                conn.execute(
                    text(
                        "INSERT INTO project_site_history "
                        "(id, organization_id, project_id, site_id, action, created_at) "
                        "VALUES (gen_random_uuid(), :org_id, :project_id, :site_id, 'LINKED', now())"
                    ),
                    {"org_id": org_a, "project_id": project_a, "site_id": site_b},
                )
                conn.commit()
            # The failed INSERT leaves the connection's transaction
            # aborted (real Postgres semantics) -- roll it back
            # explicitly rather than relying on __exit__ to do the
            # right thing.
            conn.rollback()
    finally:
        engine.dispose()
