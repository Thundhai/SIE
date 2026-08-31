"""SQLAlchemy engine/session configuration.

Provides the declarative Base, the engine, a session factory, and a FastAPI
dependency (`get_db`) that yields a request-scoped session and always closes
it. Table creation in normal operation is handled by Alembic migrations, not
by `Base.metadata.create_all` (that helper is used only by tests and local
bootstrap scripts).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session scoped to one request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
