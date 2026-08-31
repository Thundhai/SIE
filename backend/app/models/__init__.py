"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
required both for Alembic autogenerate and for `Base.metadata.create_all`
in tests.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.data_source import DataSource
from app.models.identity import Identity
from app.models.ingested_file import IngestedFile
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.site import Site
from app.models.user import User

__all__ = [
    "Base",
    "Organization",
    "Site",
    "User",
    "DataSource",
    "KnowledgeSource",
    "KnowledgeDocument",
    "KnowledgeDocumentVersion",
    "KnowledgeChunk",
    "OrganizationMembership",
    "Identity",
    "AuditLog",
    "IngestedFile",
    "IngestionJob",
]
