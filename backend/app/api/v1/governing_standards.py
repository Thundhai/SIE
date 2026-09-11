"""Organizational Standards & Governance Foundation API — SIE Milestone
43A.

    GET  /governing-standards                                  -- AVAILABLE
    POST /governing-standards                                  -- add an
                                                                   organization
                                                                   -specific
                                                                   standard
    GET  /governing-standards/{standard_id}
    GET  /organization-governing-standards                      -- SELECTED:
                                                                   the Active
                                                                   Governing
                                                                   Set
    POST /organization-governing-standards                      -- select
    POST /organization-governing-standards/{standard_id}/retire -- retire
    GET  /organization-governing-standards/history               -- the raw
                                                                   append-only
                                                                   audit trail

**Core principle, enforced here, not merely documented (spec's own
"Core principle"): available does not mean selected, selected does not
automatically mean applicable.** Nothing in this router infers a
selection from mere catalogue availability, or reasons about whether a
selected standard is *applicable* to any particular region, industry,
site, activity, or hazard — that is explicitly out of scope (spec §4,
§10, §16): this milestone establishes the data a later milestone's
applicability-reasoning layer will consume.

**Authorization — two new permissions, not a reuse of `GOVERNANCE_*`
(spec §8).** `STANDARDS_READ` gates every read; `STANDARDS_MANAGE` gates
every write (creating an organization-specific standard, selecting, and
retiring). See `app/services/permissions.py`'s own docstring for why
`GOVERNANCE_READ`/`GOVERNANCE_MANAGE` (the ML *model* governance
permissions) were not reused.

**Tenant resolution — reuses the M38/M39/M40 architecture verbatim,
never redesigned (spec §8's own "do not introduce a second tenancy
mechanism").** Every handler resolves its operative `organization_id`
through `app.api.deps_context.resolve_authorized_organization_id()`, the
identical function every other M32+ router uses.

**No PUT/PATCH/DELETE on the selection log.** Retiring a standard is a
`POST .../retire` — a new append-only event — never a literal row
deletion, mirroring every other governance-decision write path in this
codebase (M40's `POST .../governance-decisions`, M39's own equivalent).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission, resolve_authorized_organization_id
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.governing_standard import GoverningStandard, OrganizationGoverningStandard
from app.models.governing_standard_enums import GoverningStandardType
from app.schemas.governing_standard import (
    ActiveGoverningStandardListRead,
    ActiveGoverningStandardRead,
    GoverningStandardCreate,
    GoverningStandardListRead,
    GoverningStandardRead,
    OrganizationGoverningStandardCreate,
    OrganizationGoverningStandardListRead,
    OrganizationGoverningStandardRead,
    OrganizationGoverningStandardRetire,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.governing_standard_service import (
    create_organization_standard,
    list_active_governing_standards,
    list_available_governing_standards,
    list_selection_history,
    resolve_governing_standard_reference,
    retire_governing_standard,
    select_governing_standard,
    selection_mutation_transaction,
    standard_mutation_transaction,
)
from app.services.permissions import Permission

router = APIRouter(tags=["governing-standards"])

_ENDPOINT_CREATE_STANDARD = "POST /governing-standards"
_ENDPOINT_SELECT_STANDARD = "POST /organization-governing-standards"
_ENDPOINT_RETIRE_STANDARD = "POST /organization-governing-standards/{standard_id}/retire"


def _standard_to_read(record: GoverningStandard) -> GoverningStandardRead:
    return GoverningStandardRead(
        id=record.id,
        scope_type=record.scope_type,
        organization_id=record.organization_id,
        name=record.name,
        short_description=record.short_description,
        issuing_organization=record.issuing_organization,
        standard_type=record.standard_type,
        regions=list(record.regions),
        industry_sectors=list(record.industry_sectors),
        version=record.version,
        publication_date=record.publication_date,
        effective_date=record.effective_date,
        verification_status=record.verification_status,
        knowledge_source_id=record.knowledge_source_id,
        is_active=record.is_active,
        created_by_user_id=record.created_by_user_id,
        created_by_api_client_id=record.created_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _selection_to_read(record: OrganizationGoverningStandard) -> OrganizationGoverningStandardRead:
    return OrganizationGoverningStandardRead(
        id=record.id,
        organization_id=record.organization_id,
        standard_id=record.standard_id,
        status=record.status,
        effective_date=record.effective_date,
        retirement_date=record.retirement_date,
        rationale=record.rationale,
        decided_at=record.decided_at,
        configured_by_user_id=record.configured_by_user_id,
        configured_by_api_client_id=record.configured_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# --- Catalogue (AVAILABLE) -------------------------------------------------------------------


@router.get(
    "/governing-standards",
    response_model=GoverningStandardListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_governing_standards(
    organization_id: uuid.UUID = Query(...),
    region: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    standard_type: GoverningStandardType | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_READ)),
    db: Session = Depends(get_db),
) -> GoverningStandardListRead:
    """AVAILABLE — every GLOBAL catalogue entry, plus this organization's
    own ORGANIZATION-scoped entries. Never implies any of them is
    selected or applicable (spec's own "Core principle")."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    rows = list_available_governing_standards(
        db,
        organization_id=organization_id,
        region=region,
        industry=industry,
        standard_type=standard_type,
        is_active=is_active,
    )
    return GoverningStandardListRead(items=[_standard_to_read(r) for r in rows], total=len(rows))


@router.post(
    "/governing-standards",
    response_model=GoverningStandardRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_governing_standard(
    body: GoverningStandardCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> GoverningStandardRead:
    """Introduces one organization-specific standard/framework into the
    catalogue (spec §3, e.g. "ABC Energy HSE Standard 2026"). Always
    ORGANIZATION-scoped — there is no way to create a GLOBAL entry
    through this endpoint (see `governing_standard_service`'s own module
    docstring)."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_STANDARD,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return GoverningStandardRead.model_validate(lookup.response_body)

    with standard_mutation_transaction(db):
        standard = create_organization_standard(
            db,
            organization_id=organization_id,
            name=body.name,
            short_description=body.short_description,
            issuing_organization=body.issuing_organization,
            standard_type=body.standard_type,
            regions=body.regions,
            industry_sectors=body.industry_sectors,
            version=body.version,
            publication_date=body.publication_date,
            effective_date=body.effective_date,
            knowledge_source_id=body.knowledge_source_id,
            created_by_user_id=context.user_id,
            created_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.GOVERNING_STANDARD_CREATED,
            resource_type="GoverningStandard",
            resource_id=standard.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={"name": standard.name, "standard_type": standard.standard_type.value, "caller_kind": context.kind},
            request_id=request_id,
            commit=False,
        )
        result = _standard_to_read(standard)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_STANDARD,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.get(
    "/governing-standards/{standard_id}",
    response_model=GoverningStandardRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_governing_standard(
    standard_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_READ)),
    db: Session = Depends(get_db),
) -> GoverningStandardRead:
    """A standard not available to this organization (nonexistent, or
    another organization's own) is a 404, never a 403 — mirrors every
    other single-resource GET in this codebase."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    standard = resolve_governing_standard_reference(db, organization_id=organization_id, standard_id=standard_id)
    return _standard_to_read(standard)


# --- Organization selection (SELECTED / the Active Governing Set) ---------------------------


@router.get(
    "/organization-governing-standards",
    response_model=ActiveGoverningStandardListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_organization_governing_standards(
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: resolve the active set as it stood at this instant."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_READ)),
    db: Session = Depends(get_db),
) -> ActiveGoverningStandardListRead:
    """The Active Governing Set (spec's own "Final architectural
    boundary" — this milestone stops here): every standard this
    organization has explicitly SELECTED and not since RETIRED. An empty
    list is a valid, honest state — never an error, and never silently
    defaulted (spec §6, §18: "an organization that selects no standards
    can still use SIE")."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    pairs = list_active_governing_standards(db, organization_id=organization_id, as_of=as_of)
    return ActiveGoverningStandardListRead(
        items=[
            ActiveGoverningStandardRead(standard=_standard_to_read(standard), selection=_selection_to_read(selection))
            for standard, selection in pairs
        ],
        total=len(pairs),
    )


@router.post(
    "/organization-governing-standards",
    response_model=OrganizationGoverningStandardRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_organization_governing_standard(
    body: OrganizationGoverningStandardCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> OrganizationGoverningStandardRead:
    """SELECTED — the organization explicitly adopts `body.standard_id`.
    Idempotent by resolved current state (spec §13's own "duplicate
    selection is prevented"): a repeat call while already SELECTED
    returns the existing current event unchanged, `201` either way (this
    mirrors `POST /intelligence/organizational-memory`'s own "idempotent
    by construction" precedent, not an error)."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_SELECT_STANDARD,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return OrganizationGoverningStandardRead.model_validate(lookup.response_body)

    with selection_mutation_transaction(db):
        selection, created = select_governing_standard(
            db,
            organization_id=organization_id,
            standard_id=body.standard_id,
            effective_date=body.effective_date,
            rationale=body.rationale,
            configured_by_user_id=context.user_id,
            configured_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        if created:
            audit_service.log(
                db,
                action=AuditAction.GOVERNING_STANDARD_SELECTED,
                resource_type="OrganizationGoverningStandard",
                resource_id=selection.id,
                organization_id=organization_id,
                user_id=context.user_id,
                metadata={"standard_id": str(body.standard_id), "caller_kind": context.kind},
                request_id=request_id,
                commit=False,
            )
        result = _selection_to_read(selection)
        store_response(
            db,
            endpoint=_ENDPOINT_SELECT_STANDARD,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.post(
    "/organization-governing-standards/{standard_id}/retire",
    response_model=OrganizationGoverningStandardRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def retire_organization_governing_standard(
    standard_id: uuid.UUID,
    body: OrganizationGoverningStandardRetire,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_MANAGE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> OrganizationGoverningStandardRead:
    """RETIRED — a new append-only event, never a `DELETE`. 422 if this
    standard is not currently SELECTED by this organization."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    request_hash = compute_request_hash(f"{standard_id}:{body.model_dump_json()}".encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_RETIRE_STANDARD,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return OrganizationGoverningStandardRead.model_validate(lookup.response_body)

    with selection_mutation_transaction(db):
        retirement = retire_governing_standard(
            db,
            organization_id=organization_id,
            standard_id=standard_id,
            retirement_date=body.retirement_date,
            rationale=body.rationale,
            configured_by_user_id=context.user_id,
            configured_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.GOVERNING_STANDARD_RETIRED,
            resource_type="OrganizationGoverningStandard",
            resource_id=retirement.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={"standard_id": str(standard_id), "caller_kind": context.kind},
            request_id=request_id,
            commit=False,
        )
        result = _selection_to_read(retirement)
        store_response(
            db,
            endpoint=_ENDPOINT_RETIRE_STANDARD,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
            organization_id=organization_id,
            api_client_id=context.api_client_id,
            user_id=context.user_id,
            commit=False,
        )
    return result


@router.get(
    "/organization-governing-standards/history",
    response_model=OrganizationGoverningStandardListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_organization_governing_standards_history(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    context: RequestContext = Depends(require_context_permission(Permission.STANDARDS_READ)),
    db: Session = Depends(get_db),
) -> OrganizationGoverningStandardListRead:
    """The raw, append-only selection/retirement event log, newest
    first — *is* the audit trail spec §12 asks for. No path-ordering
    hazard against `POST .../{standard_id}/retire`: that route requires
    a second literal `retire` segment, so a plain GET to `.../history`
    can never be captured by it."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    rows, total = list_selection_history(db, organization_id=organization_id, page=page, page_size=page_size)
    return OrganizationGoverningStandardListRead(
        items=[_selection_to_read(r) for r in rows], total=total, page=page, page_size=page_size
    )


__all__ = ["router"]
