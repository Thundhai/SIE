"""Shared enumerations for the knowledge domain.

These are used identically by the ORM models (as SQLAlchemy `Enum` columns)
and the Pydantic schemas (as the field type directly), so the set of valid
values only has to be declared once. Kept intentionally small: only the
fields whose values drive real business rules (scope/tenant consistency,
verification workflow, ingestion state machine) are enums. Everything else
in the knowledge domain (source_type, industry_sector, jurisdiction,
authority_level, document_type, language, status) stays a free-form string
per the foundation's "don't over-constrain the domain prematurely"
principle.
"""

from enum import Enum


class ScopeType(str, Enum):
    """Whether a KnowledgeSource is global or owned by one organization."""

    GLOBAL = "GLOBAL"
    ORGANIZATION = "ORGANIZATION"


class VerificationStatus(str, Enum):
    """Governance state of a KnowledgeSource."""

    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class IngestionStatus(str, Enum):
    """Processing state of a KnowledgeDocumentVersion's content."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
