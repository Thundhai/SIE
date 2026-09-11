"""HTTP request/response shapes for `app/api/v1/governing_standards.py` —
SIE Milestone 43A: Organizational Standards & Governance Foundation.
Mirrors `app/schemas/organizational_memory.py`'s own conventions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard_enums import GoverningStandardType, OrganizationGoverningStandardStatus


class GoverningStandardCreate(BaseModel):
    """**Deliberately does not accept `organization_id`, `scope_type`,
    `verification_status`, `is_active`, `created_by_user_id`/
    `created_by_api_client_id`, or `request_id`.** A standard created
    through this endpoint is always ORGANIZATION-scoped to the caller's
    own authorized organization, always starts `PENDING`/active, and its
    actor/provenance fields are server-derived from `RequestContext` —
    there is no public write path for a GLOBAL catalogue entry (see
    `app/services/governing_standard_service.py`'s own module
    docstring)."""

    name: str = Field(..., min_length=1, max_length=255)
    short_description: str = Field(..., min_length=1, max_length=4000)
    issuing_organization: str = Field(..., min_length=1, max_length=255)
    standard_type: GoverningStandardType
    regions: list[str] = Field(default_factory=list, description="Applicable regions/jurisdictions, if known.")
    industry_sectors: list[str] = Field(default_factory=list, description="Applicable industry sectors, if known.")
    version: str | None = Field(default=None, max_length=100)
    publication_date: date | None = None
    effective_date: date | None = None
    knowledge_source_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "An existing KnowledgeSource (scope_type=ORGANIZATION) already owned by this organization, created via "
            "POST /knowledge/sources — the evidentiary document(s) backing this standard. Optional: a catalogue "
            "entry may exist before any document has been ingested."
        ),
    )


class GoverningStandardRead(BaseModel):
    id: uuid.UUID
    scope_type: ScopeType
    organization_id: uuid.UUID | None
    name: str
    short_description: str
    issuing_organization: str
    standard_type: GoverningStandardType
    regions: list[str]
    industry_sectors: list[str]
    version: str | None
    publication_date: date | None
    effective_date: date | None
    verification_status: VerificationStatus
    knowledge_source_id: uuid.UUID | None
    is_active: bool
    created_by_user_id: uuid.UUID | None
    created_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class GoverningStandardListRead(BaseModel):
    items: list[GoverningStandardRead]
    total: int


class OrganizationGoverningStandardCreate(BaseModel):
    """**Deliberately does not accept `organization_id`, `standard_id`
    (query parameter instead), `status` (always SELECTED — this endpoint
    is a "select" action, never a general status-setter), `decided_at`,
    or the actor fields.** SELECTED is always the result of an explicit
    human/machine choice, never an inferred default (spec §15 Rule 1)."""

    standard_id: uuid.UUID
    effective_date: date | None = Field(
        default=None, description="When the organization considers this standard to take effect operationally."
    )
    rationale: str | None = Field(default=None, max_length=4000)


class OrganizationGoverningStandardRetire(BaseModel):
    """**Deliberately does not accept `organization_id`, `standard_id`
    (path parameter instead), `status` (always RETIRED), `decided_at`,
    or the actor fields.**"""

    retirement_date: date | None = None
    rationale: str | None = Field(default=None, max_length=4000)


class OrganizationGoverningStandardRead(BaseModel):
    """One SELECTED/RETIRED event from the append-only selection log —
    never a mutable "current state" row (see `OrganizationGoverningStandard`
    model's own docstring)."""

    id: uuid.UUID
    organization_id: uuid.UUID
    standard_id: uuid.UUID
    status: OrganizationGoverningStandardStatus
    effective_date: date | None
    retirement_date: date | None
    rationale: str | None
    decided_at: datetime
    configured_by_user_id: uuid.UUID | None
    configured_by_api_client_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class OrganizationGoverningStandardListRead(BaseModel):
    items: list[OrganizationGoverningStandardRead]
    total: int
    page: int
    page_size: int


class ActiveGoverningStandardRead(BaseModel):
    """One entry in the organization's Active Governing Set (spec's own
    "Final architectural boundary" — this is where M43A stops): the
    catalogue entry itself, paired with the resolved current selection
    event that makes it active right now. Never implies applicability —
    only that the organization has explicitly SELECTED this standard and
    not since RETIRED it (spec's own "Core principle": selected does not
    automatically mean applicable)."""

    standard: GoverningStandardRead
    selection: OrganizationGoverningStandardRead


class ActiveGoverningStandardListRead(BaseModel):
    items: list[ActiveGoverningStandardRead]
    total: int


__all__ = [
    "GoverningStandardCreate",
    "GoverningStandardRead",
    "GoverningStandardListRead",
    "OrganizationGoverningStandardCreate",
    "OrganizationGoverningStandardRetire",
    "OrganizationGoverningStandardRead",
    "OrganizationGoverningStandardListRead",
    "ActiveGoverningStandardRead",
    "ActiveGoverningStandardListRead",
]
