from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base  # noqa: F401  (imports all models onto Base.metadata)

# Alembic Config object, providing access to values in alembic.ini.
config = context.config

# Set the DB URL from application settings (env-driven) rather than a
# hardcoded value in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Database Boundary Separation milestone: some models now declare a real
#: PostgreSQL schema (`commercial_core`, see backend/docs/DATABASE_BOUNDARY.md).
#: `include_schemas=True` is required for Alembic's autogenerate/`check` to
#: reflect and diff against that schema at all -- without it, only the
#: connection's default schema (`public`) is ever reflected from the live
#: database, which would make every `commercial_core`-schema model look
#: entirely absent from the database (spurious "create" diffs) regardless
#: of what actually exists there.
_INCLUDE_SCHEMAS = True

#: `commercial_core.recommendation_candidates` (migration `0033`) is a
#: deliberate exception: this repository provisions its DDL, on Commercial
#: Core's behalf, in the one Alembic chain that exists for the shared
#: database -- but Public SIE has no business reason to ever construct or
#: query a row in it (see that migration's own docstring), so it
#: intentionally has no SQLAlchemy model here. Without this filter,
#: autogenerate would see a table with no metadata counterpart and propose
#: dropping it on every `alembic check`/`--autogenerate` run.
def include_object(object_, name, type_, reflected, compare_to):
    return not (type_ == "table" and name == "recommendation_candidates")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=_INCLUDE_SCHEMAS,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=_INCLUDE_SCHEMAS,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
