"""Shared enumerations for the knowledge and identity domains.

These are used identically by the ORM models (as SQLAlchemy `Enum` columns)
and the Pydantic schemas (as the field type directly), so the set of valid
values only has to be declared once. Kept intentionally small: only the
fields whose values drive real business rules (scope/tenant consistency,
verification workflow, ingestion state machine, membership state machine)
are enums. Everything else in the knowledge domain (source_type,
industry_sector, jurisdiction, authority_level, document_type, language,
status) stays a free-form string per the foundation's "don't over-constrain
the domain prematurely" principle — and, deliberately, so does
`OrganizationMembership.role` (see app/services/permissions.py): roles are
a small, evolving set validated at the service layer, not a hard database
enum, so adding a role later doesn't require a migration.
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


class MembershipStatus(str, Enum):
    """State of one OrganizationMembership row.

    Only ACTIVE membership grants access (see
    app/services/tenant_context.py). SUSPENDED and REVOKED both deny
    access; they are kept distinct because they mean different things
    operationally (SUSPENDED is expected to be temporary and
    reversible — e.g. an admin pausing access — while REVOKED is a
    terminal removal) even though today's authorization check treats
    them identically.
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INVITED = "INVITED"
    REVOKED = "REVOKED"
