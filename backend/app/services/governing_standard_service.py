"""GoverningStandard / OrganizationGoverningStandard service — SIE
Milestone 43A: Organizational Standards & Governance Foundation. The one
write/read path for `app/api/v1/governing_standards.py`, mirroring
`app/services/organizational_memory_service.py`'s own shape exactly
(transaction-boundary context managers, a `resolve_*_reference()` 404
helper, a `resolve_current_*()` "most recent row wins" function).

    GET  /governing-standards
        -> list_available_governing_standards()     -- AVAILABLE: GLOBAL
                                                         catalogue entries
                                                         plus this org's own
    POST /governing-standards
        -> create_organization_standard()           -- always ORGANIZATION-
                                                         scoped; there is no
                                                         public write path
                                                         for a GLOBAL entry
                                                         (spec §3, §16 --
                                                         see this module's
                                                         own "no GLOBAL write
                                                         path" note below)

    POST /organization-governing-standards
        -> select_governing_standard()               -- SELECTED: idempotent
                                                         by resolved current
                                                         state, never a
                                                         duplicate event
    POST /organization-governing-standards/{id}/retire
        -> retire_governing_standard()                -- RETIRED: a new
                                                         append-only event
    GET  /organization-governing-standards
        -> list_active_governing_standards()          -- the Active
                                                         Governing Set: every
                                                         standard whose
                                                         *resolved current*
                                                         state is SELECTED
    GET  /organization-governing-standards/history
        -> list_selection_history()                   -- the raw append-only
                                                         audit trail (spec
                                                         §12)

**No function in this module ever infers adoption from availability, or
applicability from region/industry match (spec §15, Rules 1/2).**
`list_available_governing_standards()` returns everything *available* to
browse; `select_governing_standard()` is the one place an organization's
explicit choice is recorded. Nothing here reasons about whether a
selected standard actually applies to a given site/activity/hazard --
that is explicitly out of scope (spec §4, §10: "M43A does not need to
build the complete applicability reasoning engine... establish the data
required for that later capability").

**No GLOBAL write path (spec §16: "do not implement... automatic standard
selection").** `create_organization_standard()` always creates an
ORGANIZATION-scoped row for the caller's own authorized organization --
there is no parameter, permission, or code path in this milestone that
lets any organization-scoped caller create or alter a GLOBAL catalogue
entry. GLOBAL reference data (ISO 45001, OSHA, IOGP, ICMM, API, etc.) is
loaded by `seed_global_catalogue()` below -- an idempotent, directly
invoked (not API-exposed) helper, since M43A does not need a
platform-administration surface to satisfy its own acceptance test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard import GoverningStandard, OrganizationGoverningStandard
from app.models.governing_standard_enums import GoverningStandardType, OrganizationGoverningStandardStatus
from app.models.knowledge_source import KnowledgeSource

__all__ = [
    "standard_mutation_transaction",
    "selection_mutation_transaction",
    "resolve_governing_standard_reference",
    "list_available_governing_standards",
    "create_organization_standard",
    "resolve_current_selection",
    "select_governing_standard",
    "retire_governing_standard",
    "list_active_governing_standards",
    "list_selection_history",
    "seed_global_catalogue",
]


@contextmanager
def standard_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `GoverningStandard`
    write -- identical shape to `organizational_memory_service.
    memory_mutation_transaction()`. Commits once on success; rolls back
    once and re-raises, unchanged, on any exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


@contextmanager
def selection_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one selection/retirement
    event write -- kept as its own named function, mirroring
    `organizational_memory_service.memory_governance_mutation_
    transaction()`'s own identical one-context-manager-per-write-kind
    convention."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def resolve_governing_standard_reference(
    db: Session, *, organization_id: uuid.UUID, standard_id: uuid.UUID
) -> GoverningStandard:
    """A catalogue entry is resolvable to `organization_id` when it is
    GLOBAL (available to every organization) or when it is that
    organization's own ORGANIZATION-scoped entry -- never another
    organization's own standard. A nonexistent id, or one belonging to a
    *different* organization, is a 404, never a silent cross-tenant read
    -- identical discipline to `organizational_memory_service.
    resolve_memory_reference()`, applied here at the service layer
    (rather than a database constraint) because a GLOBAL standard has no
    `organization_id` to compose a cross-table foreign key against (see
    `OrganizationGoverningStandard`'s own docstring)."""
    standard = db.get(GoverningStandard, standard_id)
    if standard is None or (
        standard.scope_type != ScopeType.GLOBAL and standard.organization_id != organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="standard_id not found or not available to this organization."
        )
    return standard


def list_available_governing_standards(
    db: Session,
    *,
    organization_id: uuid.UUID,
    region: str | None = None,
    industry: str | None = None,
    standard_type: GoverningStandardType | None = None,
    is_active: bool | None = True,
) -> list[GoverningStandard]:
    """AVAILABLE (spec §4): every GLOBAL catalogue entry, plus this
    organization's own ORGANIZATION-scoped entries -- never another
    organization's own standard. `region`/`industry` filter on whether
    the value appears in that standard's own `regions`/`industry_sectors`
    list (an honest, non-claim empty list never matches any filter --
    spec §15 Rule 2: availability is never stretched into an implied
    applicability match). `is_active` defaults to `True` -- browsing
    "available standards" during onboarding should not surface retired
    catalogue entries unless explicitly asked for."""
    conditions = [
        (GoverningStandard.scope_type == ScopeType.GLOBAL)
        | (
            (GoverningStandard.scope_type == ScopeType.ORGANIZATION)
            & (GoverningStandard.organization_id == organization_id)
        )
    ]
    if standard_type is not None:
        conditions.append(GoverningStandard.standard_type == standard_type)
    if is_active is not None:
        conditions.append(GoverningStandard.is_active == is_active)

    rows = list(
        db.execute(
            select(GoverningStandard).where(*conditions).order_by(GoverningStandard.name.asc())
        ).scalars()
    )
    if region is not None:
        rows = [r for r in rows if region in r.regions]
    if industry is not None:
        rows = [r for r in rows if industry in r.industry_sectors]
    return rows


def create_organization_standard(
    db: Session,
    *,
    organization_id: uuid.UUID,
    name: str,
    short_description: str,
    issuing_organization: str,
    standard_type: GoverningStandardType,
    regions: list[str],
    industry_sectors: list[str],
    version: str | None,
    publication_date: date | None,
    effective_date: date | None,
    knowledge_source_id: uuid.UUID | None,
    created_by_user_id: uuid.UUID | None,
    created_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> GoverningStandard:
    """Introduces one organization-specific standard/framework into the
    catalogue (spec §3, e.g. "ABC Energy HSE Standard 2026") -- always
    ORGANIZATION-scoped to the caller's own authorized organization; see
    module docstring's own "No GLOBAL write path" note.

    `knowledge_source_id`, when given, must already exist and belong to
    this same organization (spec §3's own "an uploaded organizational
    standard must remain organization-scoped... organization knowledge
    must not leak across tenants") -- created via the existing
    `POST /knowledge/sources` (`scope_type=ORGANIZATION`) +
    `POST /knowledge/sources/{id}/documents` ingestion path, never a
    second document system built here. A GLOBAL source, or another
    organization's own source, is rejected with 422 before any catalogue
    row is created.
    """
    if knowledge_source_id is not None:
        source = db.get(KnowledgeSource, knowledge_source_id)
        if source is None or source.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="knowledge_source_id must reference an existing knowledge source owned by this organization.",
            )

    standard = GoverningStandard(
        scope_type=ScopeType.ORGANIZATION,
        organization_id=organization_id,
        name=name,
        short_description=short_description,
        issuing_organization=issuing_organization,
        standard_type=standard_type,
        regions=list(regions),
        industry_sectors=list(industry_sectors),
        version=version,
        publication_date=publication_date,
        effective_date=effective_date,
        verification_status=VerificationStatus.PENDING,
        knowledge_source_id=knowledge_source_id,
        is_active=True,
        created_by_user_id=created_by_user_id,
        created_by_api_client_id=created_by_api_client_id,
        request_id=request_id,
    )
    db.add(standard)
    db.flush()  # populates standard.id/created_at/updated_at, without committing
    return standard


def resolve_current_selection(
    db: Session, *, organization_id: uuid.UUID, standard_id: uuid.UUID, as_of: datetime | None = None
) -> OrganizationGoverningStandard | None:
    """The deterministic "resolved current state" for one (organization,
    standard) pair -- identical rule to `organizational_memory_service.
    resolve_current_memory_governance()`: the single most recent row,
    ordered `decided_at DESC, id DESC`. `None` when this organization has
    never selected (or retired) this standard at all -- the honest
    "not selected" state (never inferred, never defaulted to SELECTED).

    `as_of`, when supplied, restricts to rows with `decided_at <= as_of`
    -- a selection/retirement recorded after `as_of` must not appear in
    a historical reconstruction, mirroring M38/M39/M40's identical
    `as_of` rule."""
    conditions = [
        OrganizationGoverningStandard.organization_id == organization_id,
        OrganizationGoverningStandard.standard_id == standard_id,
    ]
    if as_of is not None:
        conditions.append(OrganizationGoverningStandard.decided_at <= as_of)
    return db.execute(
        select(OrganizationGoverningStandard)
        .where(*conditions)
        .order_by(OrganizationGoverningStandard.decided_at.desc(), OrganizationGoverningStandard.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def select_governing_standard(
    db: Session,
    *,
    organization_id: uuid.UUID,
    standard_id: uuid.UUID,
    effective_date: date | None,
    rationale: str | None,
    configured_by_user_id: uuid.UUID | None,
    configured_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> tuple[OrganizationGoverningStandard, bool]:
    """SELECTED (spec §4): the organization explicitly adopts
    `standard_id` as one of the standards governing its operations.
    Returns `(row, created)` -- `created=False` when the standard is
    already currently SELECTED (spec §13's own "duplicate selection is
    prevented" requirement): the existing current row is returned
    unchanged, never a redundant second SELECTED event. Re-selecting a
    previously RETIRED standard *does* create a new event -- that is a
    genuine, distinct governance action (re-adoption), not a duplicate.

    `standard_id` is resolved against `organization_id` first (404
    before any row is touched) -- an organization may only select a
    GLOBAL standard or its own ORGANIZATION-scoped one, never another
    organization's own standard (spec §8's own tenant-isolation
    requirement)."""
    resolve_governing_standard_reference(db, organization_id=organization_id, standard_id=standard_id)

    current = resolve_current_selection(db, organization_id=organization_id, standard_id=standard_id)
    if current is not None and current.status == OrganizationGoverningStandardStatus.SELECTED:
        return current, False

    selection = OrganizationGoverningStandard(
        organization_id=organization_id,
        standard_id=standard_id,
        status=OrganizationGoverningStandardStatus.SELECTED,
        effective_date=effective_date,
        retirement_date=None,
        rationale=rationale,
        configured_by_user_id=configured_by_user_id,
        configured_by_api_client_id=configured_by_api_client_id,
        request_id=request_id,
    )
    db.add(selection)
    db.flush()  # populates selection.id/decided_at/created_at/updated_at, without committing
    return selection, True


def retire_governing_standard(
    db: Session,
    *,
    organization_id: uuid.UUID,
    standard_id: uuid.UUID,
    retirement_date: date | None,
    rationale: str | None,
    configured_by_user_id: uuid.UUID | None,
    configured_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> OrganizationGoverningStandard:
    """RETIRED: the organization explicitly withdraws a previously
    selected standard -- a new append-only event, never an in-place
    status flip or a `DELETE` (spec §9's own conceptual "RETIRE", not a
    literal row deletion -- mirrors every other governance-decision
    write path in this codebase). 422 if this standard is not currently
    SELECTED (never selected at all, or already RETIRED) -- there is
    nothing to retire."""
    resolve_governing_standard_reference(db, organization_id=organization_id, standard_id=standard_id)

    current = resolve_current_selection(db, organization_id=organization_id, standard_id=standard_id)
    if current is None or current.status != OrganizationGoverningStandardStatus.SELECTED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This standard is not currently selected by this organization; nothing to retire.",
        )

    retirement = OrganizationGoverningStandard(
        organization_id=organization_id,
        standard_id=standard_id,
        status=OrganizationGoverningStandardStatus.RETIRED,
        effective_date=None,
        retirement_date=retirement_date,
        rationale=rationale,
        configured_by_user_id=configured_by_user_id,
        configured_by_api_client_id=configured_by_api_client_id,
        request_id=request_id,
    )
    db.add(retirement)
    db.flush()  # populates retirement.id/decided_at/created_at/updated_at, without committing
    return retirement


def list_active_governing_standards(
    db: Session, *, organization_id: uuid.UUID, as_of: datetime | None = None
) -> list[tuple[GoverningStandard, OrganizationGoverningStandard]]:
    """The Active Governing Set (spec's own "Final architectural
    boundary": "M43A stops at the Active Governing Set") -- every
    standard whose *resolved current* selection state (per
    `resolve_current_selection()`, never a stored "is active" column) is
    SELECTED. This is the one function a later milestone calls to answer
    "what governing standards are active for this organization?" (spec
    §10). An organization with no selections at all returns an empty
    list -- a valid, non-error state (spec §6, §18: "an organization that
    selects no standards can still use SIE... remaining explicit rather
    than silently inferred"), never a fabricated default."""
    distinct_standard_ids = db.execute(
        select(OrganizationGoverningStandard.standard_id)
        .where(OrganizationGoverningStandard.organization_id == organization_id)
        .distinct()
    ).scalars().all()

    active: list[tuple[GoverningStandard, OrganizationGoverningStandard]] = []
    for standard_id in distinct_standard_ids:
        current = resolve_current_selection(db, organization_id=organization_id, standard_id=standard_id, as_of=as_of)
        if current is not None and current.status == OrganizationGoverningStandardStatus.SELECTED:
            standard = db.get(GoverningStandard, standard_id)
            if standard is not None:
                active.append((standard, current))
    active.sort(key=lambda pair: pair[0].name)
    return active


def list_selection_history(
    db: Session, *, organization_id: uuid.UUID, page: int = 1, page_size: int = 25
) -> tuple[list[OrganizationGoverningStandard], int]:
    """The raw, append-only selection/retirement event log for this
    organization, newest first -- *is* the audit trail spec §12 asks
    for ("SIE should be able to determine Organization X selected
    Standard Y at time Z through actor A, and similarly when retired").
    Never filtered down to "current state only" -- that is
    `list_active_governing_standards()`'s job."""
    conditions = [OrganizationGoverningStandard.organization_id == organization_id]
    total = db.execute(
        select(OrganizationGoverningStandard.id).where(*conditions)
    ).scalars().all()
    rows = (
        db.execute(
            select(OrganizationGoverningStandard)
            .where(*conditions)
            .order_by(OrganizationGoverningStandard.decided_at.desc(), OrganizationGoverningStandard.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), len(total)


def seed_global_catalogue(db: Session, entries: list[dict]) -> list[GoverningStandard]:
    """Idempotently load GLOBAL catalogue reference data (spec §1's own
    examples -- ISO 45001, OSHA, IOGP, ICMM, API, etc. -- "do not
    hard-code the examples above as the complete universe": this
    function takes the data as a parameter, it does not hardcode any
    particular standard itself). Matches existing GLOBAL entries by
    `name` (case-sensitive, exact) and skips them -- calling this
    repeatedly with the same data never creates duplicates. Not exposed
    via any API route in M43A (see module docstring's own "No GLOBAL
    write path" note) -- invoked directly (e.g. from a startup/seed
    script) by whoever operates the platform's own knowledge universe,
    never by an organization-scoped caller.
    """
    existing_names = {
        row[0]
        for row in db.execute(
            select(GoverningStandard.name).where(GoverningStandard.scope_type == ScopeType.GLOBAL)
        ).all()
    }
    created: list[GoverningStandard] = []
    for entry in entries:
        if entry["name"] in existing_names:
            continue
        standard = GoverningStandard(
            scope_type=ScopeType.GLOBAL,
            organization_id=None,
            name=entry["name"],
            short_description=entry["short_description"],
            issuing_organization=entry["issuing_organization"],
            standard_type=GoverningStandardType(entry["standard_type"]),
            regions=list(entry.get("regions", [])),
            industry_sectors=list(entry.get("industry_sectors", [])),
            version=entry.get("version"),
            publication_date=entry.get("publication_date"),
            effective_date=entry.get("effective_date"),
            verification_status=VerificationStatus(entry.get("verification_status", "VERIFIED")),
            knowledge_source_id=entry.get("knowledge_source_id"),
            is_active=True,
        )
        db.add(standard)
        created.append(standard)
    if created:
        db.flush()
    return created
