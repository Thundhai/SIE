"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
required both for Alembic autogenerate and for `Base.metadata.create_all`
in tests.
"""

from app.models.base import Base
from app.models.data_source import DataSource
from app.models.organization import Organization
from app.models.site import Site
from app.models.user import User

__all__ = [
    "Base",
    "Organization",
    "Site",
    "User",
    "DataSource",
]
