"""SIE Milestone 43A: Organizational Standards & Governance Foundation.

The governance foundation that lets SIE distinguish three separate
concepts, per the milestone spec's own "Core principle": *available does
not mean selected, selected does not automatically mean applicable*.

    GoverningStandard               -- AVAILABLE: SIE's knowledge universe
        (GLOBAL or ORGANIZATION-scoped catalogue entry)
    OrganizationGoverningStandard    -- SELECTED: an organization's own,
        (append-only selection/retirement event log)   explicit governing set
    [a later milestone, M43B]        -- APPLICABLE: evidence-based,
                                         contextual reasoning -- NOT built here

This module builds only the first two. Nothing here infers adoption from
availability, infers applicability from region/industry match, or lets an
LLM decide what standard governs an organization (spec §15, Rules 1/2/7).

**Catalogue scoping mirrors `KnowledgeSource` exactly, not a new pattern
(spec §11: "reuse the existing knowledge architecture").** A
`GoverningStandard` is either GLOBAL (`organization_id IS NULL` -- SIE's
own knowledge of ISO 45001, OSHA, IOGP, ICMM, API, etc., not owned by any
tenant) or ORGANIZATION-scoped (an organization's own standard, e.g. "ABC
Energy HSE Standard 2026", spec §3). The identical GLOBAL/ORGANIZATION
CHECK constraint technique `KnowledgeSource` already uses makes this
structurally enforced at the database level, not just convention. An
organization-specific standard's evidentiary backing --
the actual document(s) -- is not duplicated here: `knowledge_source_id`
points at a real `KnowledgeSource` (created via the existing
`POST /knowledge/sources` + `POST /knowledge/sources/{id}/documents`
ingestion path, spec §3's own "integrate with the existing SIE
knowledge/ingestion architecture rather than creating a completely
separate document system"). It is nullable because a catalogue entry (in
particular a GLOBAL one seeded as reference data) may exist before, or
entirely without, an ingested source document.

**Selection is many-to-many with governance metadata, never a single FK
column (spec §2's own explicit "do not implement
`organization.selected_standard_id`").** `OrganizationGoverningStandard`
is the join table, and it is append-only, mirroring
`OrganizationalMemoryGovernanceDecision`'s (SIE Milestone 40) exact
established shape: one row per selection or retirement *event*, never an
in-place status flip on a single persistent row. This is what makes "SIE
should be able to determine Organization X selected Standard Y at time Z
through actor A, and similarly when retired" (spec §12) a property of the
schema itself, not something bolted on separately. The *current* governing
state for one (organization, standard) pair is always resolved live --
the most recent row by `decided_at DESC, id DESC` -- by
`app.services.governing_standard_service.resolve_current_selection()`,
never stored as its own mutable column.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard_enums import GoverningStandardType, OrganizationGoverningStandardStatus

# Cross-dialect JSON list storage -- identical technique to
# `ApiClient.scopes`/`DatasetVersion.source_systems` (plain JSON on
# SQLite for tests, JSONB on PostgreSQL in production). Used for the two
# genuinely list-shaped catalogue fields (spec §1: "applicable
# regions/jurisdictions", "applicable industry sectors") -- never a
# comma-joined string, which would make filtering unreliable.
_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class GoverningStandard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One catalogue entry in SIE's knowledge universe of standards and
    frameworks -- "available", per the milestone's own vocabulary. See
    module docstring for the GLOBAL/ORGANIZATION scoping rationale.
    """

    __tablename__ = "governing_standards"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND organization_id IS NULL) OR "
            "(scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL)",
            name="ck_governing_standards_scope_org_consistency",
        ),
        Index("ix_governing_standards_scope_type", "scope_type"),
        Index("ix_governing_standards_standard_type", "standard_type"),
        Index("ix_governing_standards_is_active", "is_active"),
        # Enables a future composite FK (e.g. from an M43B applicability
        # record) that must guarantee it references a standard together
        # with its own scoping organization -- added proactively here,
        # mirroring `Site`/`OrganizationalMemory`'s own established
        # precedent of adding this constraint at introduction rather than
        # retrofitting it later.
        UniqueConstraint("id", "organization_id", name="uq_governing_standards_id_organization_id"),
    )

    scope_type: Mapped[ScopeType] = mapped_column(
        SAEnum(ScopeType, name="governing_standard_scope_type", native_enum=True),
        nullable=False,
    )
    # NULL exactly when GLOBAL, required when ORGANIZATION -- enforced by
    # the CHECK constraint above, identical to `KnowledgeSource`.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    issuing_organization: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_type: Mapped[GoverningStandardType] = mapped_column(
        SAEnum(GoverningStandardType, name="governing_standard_type", native_enum=True),
        nullable=False,
    )

    # Applicable regions/jurisdictions and industry sectors -- lists, not
    # a single value, since one standard (e.g. an IOGP guidance document)
    # commonly applies across several. Empty list, never NULL, when
    # genuinely unspecified -- an absent value is honestly "not stated",
    # not silently treated as "applies everywhere" (spec §15 Rule 2: "SIE
    # never assumes applicability merely from regional availability" --
    # an empty list here is exactly that honest non-claim, carried
    # through to any future applicability reasoning that consults it).
    regions: Mapped[list[str]] = mapped_column(_JSONType, nullable=False, default=list)
    industry_sectors: Mapped[list[str]] = mapped_column(_JSONType, nullable=False, default=list)

    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Reuses `KnowledgeSource`'s own governance-maturity vocabulary
    # verbatim (spec §1: "verification/governance status") -- this is not
    # a second, competing governance concept; it describes how
    # authoritative/reviewed *this catalogue entry itself* is, exactly
    # the same question `KnowledgeSource.verification_status` answers for
    # a knowledge source.
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="governing_standard_verification_status", native_enum=True),
        nullable=False,
        default=VerificationStatus.PENDING,
    )

    # Optional reference to the underlying knowledge source (spec §1's
    # own "reference to the underlying knowledge source where
    # applicable"). `ON DELETE SET NULL`: removing the evidentiary
    # document set must not silently delete the catalogue entry's own
    # selection history -- an organization's governance decision to adopt
    # a standard remains a fact about that organization even if the
    # underlying document is later withdrawn.
    knowledge_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    organization: Mapped["Organization | None"] = relationship()  # noqa: F821
    knowledge_source: Mapped["KnowledgeSource | None"] = relationship()  # noqa: F821

    @property
    def is_global(self) -> bool:
        return self.scope_type == ScopeType.GLOBAL

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<GoverningStandard id={self.id!s} scope_type={self.scope_type!s} "
            f"organization_id={self.organization_id!s} name={self.name!r}>"
        )


class OrganizationGoverningStandard(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    """One SELECTED/RETIRED governance event: `organization_id` has
    explicitly adopted (or withdrawn) `standard_id` as one of the
    standards governing its operations. Append-only -- see module
    docstring. No route ever issues an `UPDATE`/`DELETE` against this
    table; a correction is a new row, exactly like
    `OrganizationalMemoryGovernanceDecision`.

    `standard_id` is a plain (not composite) foreign key: unlike
    `OrganizationalMemory`'s reference to a same-tenant
    `IntelligenceLearningCandidate`, the referenced `GoverningStandard`
    is frequently owned by a *different* "tenant" in the sense that a
    GLOBAL standard has no `organization_id` at all to compose against.
    Tenant-safety for *which* standards an organization may select
    (its own ORGANIZATION-scoped standards, plus any GLOBAL one -- never
    another organization's own standard) is therefore enforced at the
    service layer by `app.services.governing_standard_service.
    resolve_governing_standard_reference()`, exactly mirroring how
    `KnowledgeDocument`'s tenant safety is enforced by query-scoping and
    `get_knowledge_source_or_404()` rather than a cross-table database
    constraint.
    """

    __tablename__ = "organization_governing_standards"
    __table_args__ = (
        Index("ix_org_governing_standards_org_standard", "organization_id", "standard_id"),
        Index("ix_org_governing_standards_org_status", "organization_id", "status"),
    )

    standard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("governing_standards.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[OrganizationGoverningStandardStatus] = mapped_column(
        SAEnum(
            OrganizationGoverningStandardStatus,
            name="organization_governing_standard_status",
            native_enum=True,
        ),
        nullable=False,
    )

    #: When the organization considers this standard to take effect
    #: operationally -- distinct from `decided_at` (when the selection
    #: event itself was recorded). Optional (spec §2).
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Only meaningful on a `RETIRED` row -- when the standard stops
    #: governing. Optional (spec §2).
    retirement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Optional human-readable note -- "why this selection/retirement".
    #: Not required (unlike M40's governance-decision rationale): a
    #: routine onboarding selection of a well-known standard does not
    #: need a stated justification the way retracting organizational
    #: memory does.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Server-derived -- a selection/retirement action is made in the
    #: moment of the API call, mirroring
    #: `OrganizationalMemoryGovernanceDecision.decided_at`'s own
    #: identical reasoning.
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    configured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    configured_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    standard: Mapped["GoverningStandard"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OrganizationGoverningStandard id={self.id!s} organization_id={self.organization_id!s} "
            f"standard_id={self.standard_id!s} status={self.status!s}>"
        )


__all__ = ["GoverningStandard", "OrganizationGoverningStandard"]
