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


class IngestionJobStatus(str, Enum):
    """Lifecycle state of one IngestionJob — one attempt to ingest one
    file. Not to be confused with `IngestionStatus` above, which tracks a
    *KnowledgeDocumentVersion's* content-processing state; the two exist
    at different granularities and were named independently before this
    milestone introduced jobs. `IngestedFile.ingestion_status` (see
    app/models/ingested_file.py) reuses this same enum: the file's field
    mirrors its most recent job's status (a "current state" view), while
    each IngestionJob row is an immutable record of one attempt — the
    same current-state/immutable-history split already used between
    KnowledgeDocument.status and KnowledgeDocumentVersion.
    """

    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExtractionStatus(str, Enum):
    """Outcome of *content extraction* specifically — distinct from the
    job's overall pipeline status. A job can COMPLETE while its
    extraction was only PARTIAL (e.g. a PDF with some unreadable pages) —
    see the ingestion engine's "fail safely, never silently pretend
    extraction succeeded" quality principle."""

    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ExtractionMethod(str, Enum):
    """How a file's content was (or would be) extracted. Recorded per
    file for provenance and evidence-quality purposes — an OCR-derived
    chunk is weaker evidence than one extracted directly from a digital
    document's text layer, and callers evaluating evidence later need to
    know which happened."""

    TEXT_EXTRACTION = "TEXT_EXTRACTION"
    STRUCTURED_PARSE = "STRUCTURED_PARSE"
    OCR = "OCR"
    NONE = "NONE"


class ContentType(str, Enum):
    """What kind of thing one piece of content is — not the source file
    format (that's on IngestedFile/KnowledgeChunk.extraction_method), but
    the shape of this particular piece of content within it. Shared by
    `NormalizedContent`, `KnowledgeUnit`, and `KnowledgeChunk` (see
    app/ingestion/normalized_content.py, app/ingestion/knowledge_unit.py)
    so a chunk's content_type is always one of the same values a caller
    already learned to expect from the ingestion response, and is
    directly filterable per the milestone's future-retrieval requirement
    ("content type" — see app/services/chunking_service.py)."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    STRUCTURED_RECORD = "structured_record"


class QualityStatus(str, Enum):
    """A deterministic *extraction/structure* quality indicator — never a
    judgment about whether the underlying safety information itself is
    true, complete, or authoritative (that is `KnowledgeSource.authority_level`
    and `verification_status`, entirely separate concepts — see
    app/ingestion/quality.py's module docstring for the full reasoning
    and why the two are never combined into one score).

    INSUFFICIENT means the content is not usable as evidence at all (e.g.
    empty/near-empty text, an image with no OCR). LOW/MEDIUM/HIGH grade
    how complete and structurally well-formed the extraction was, not how
    good the source material is.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"
