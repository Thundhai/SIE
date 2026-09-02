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

        command.upgrade(_alembic_config(), "head")

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0013"

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
            assert version == "0013"
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
