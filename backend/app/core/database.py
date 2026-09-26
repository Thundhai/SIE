"""SQLAlchemy engine/session configuration.

Provides the declarative Base, the engine, a session factory, and a FastAPI
dependency (`get_db`) that yields a request-scoped session and always closes
it. Table creation in normal operation is handled by Alembic migrations, not
by `Base.metadata.create_all` (that helper is used only by tests and local
bootstrap scripts).
"""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

#: Database Boundary Separation milestone: SQLAlchemy's zero-config
#: auto-naming for a `Column(index=True)`/unnamed `Index(...)` embeds the
#: table's *schema* into the generated name for any table that declares
#: one (e.g. `ix_commercial_core_dataset_versions_dataset_id`) --
#: verified directly against a schema-qualified `Table` in a standalone
#: script before relying on this. Every one of those tables' indexes was
#: created by an earlier migration, before this milestone existed, using
#: the *unqualified* name (`ix_dataset_versions_dataset_id`) -- moving a
#: table with `ALTER TABLE ... SET SCHEMA` (migrations 0032/0034/0035)
#: never renames its indexes, so the physical name never changed. This
#: naming convention pins the "ix" key to the same schema-independent
#: pattern SQLAlchemy already used for every non-schema-qualified table,
#: so a `commercial_core`-schema model's implicit index name keeps
#: matching what is actually in the database instead of drifting the
#: moment `schema="commercial_core"` is added to a model -- confirmed to
#: be a no-op for every pre-existing, non-schema-qualified table's index
#: name (same convention, same result, since `table_name` and
#: `column_0_label` only diverge when a schema is present).
_NAMING_CONVENTION = {"ix": "ix_%(table_name)s_%(column_0_name)s"}


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session scoped to one request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
