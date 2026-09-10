"""Organizational Memory Architecture API — SIE Milestone 40.

    POST /intelligence/learning-candidates/{id}/governance-decisions (M39, unchanged) -> ACCEPTED
    POST /intelligence/organizational-memory      -> a durable OrganizationalMemory row (this router)
    GET  /intelligence/organizational-memory
    GET  /intelligence/organizational-memory/{memory_id}
    POST /intelligence/organizational-memory/{memory_id}/governance-decisions
    GET  /intelligence/organizational-memory/{memory_id}/governance-decisions
    GET  /intelligence/organizational-memory/{memory_id}/state

**Durable, governed organizational knowledge — still not the mechanism
that changes SIE's intelligence.** See
`app/models/organizational_memory.py`'s own docstring and
`docs/ORGANIZATIONAL_MEMORY_V0_1.md` for the full design rationale,
including the explicit statement that learning integration (M41) --
*how* SIE actually uses this remembered knowledge -- is out of scope.
No `PUT`/`PATCH`/`DELETE` route exists or is planned for either
`OrganizationalMemory` or its governance decisions — a correction is a
new governance-decision row referencing the same `memory_id` (M40
spec §11).

**The governance boundary is enforced here, not merely documented (M40
spec §5).** `POST /organizational-memory` succeeds only when the
referenced learning candidate's resolved current governance decision
(reuses M39's own `resolve_current_governance()` verbatim — see
`app/services/organizational_memory_service.py::
create_organizational_memory()`) is `ACCEPTED`. A pending or `REJECTED`
candidate, or one that does not exist/belongs to another organization,
is rejected before any memory row is ever created.

**Authorization — reuses M39's own decision-governance permission, not
a new role (M40 spec §14).** Creating a memory or recording a
governance decision about one is the same trusted-authority tier as
accepting the learning candidate that made it possible — so
`Permission.INTELLIGENCE_DECISION_WRITE` gates every write in this
router (granted to the same `HSE_MANAGER`/`HSE_ANALYST` roles), rather
than inventing a new permission. Every read reuses `Permission.
INTELLIGENCE_READ`.

**Tenant resolution — reuses the M38/M39 architecture verbatim, never
redesigned (M40 spec §13).** Every handler resolves its operative
`organization_id` through `app.api.deps_context.
resolve_authorized_organization_id()` — the identical function
`app/api/v1/intelligence_outcomes.py` and `app/api/v1/intelligence_
learning_candidates.py` already use.

**Idempotency (M40 spec §15) — two independent guarantees, not one.**
`POST /organizational-memory` is idempotent *by construction*:
`OrganizationalMemory` carries a DB-level `UNIQUE(organization_id,
learning_candidate_id)` constraint, so a repeat call for the same
candidate always returns the existing row (`created=False`), never a
duplicate or an error — this holds even without any `Idempotency-Key`
header. Both write routes additionally support the `Idempotency-Key`
header exactly like every other write route in this codebase,
guaranteeing exact response replay on a retried request.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission, resolve_authorized_organization_id
from app.api.deps_rate_limit import RateLimitClass, require_rate_limit
from app.core.idempotency import check_and_replay, compute_request_hash, store_response
from app.core.request_id import get_request_id
from app.models.intelligence_learning_candidate import IntelligenceLearningCandidate
from app.models.intelligence_outcome import IntelligenceOutcome
from app.models.intelligence_outcome_verification import IntelligenceOutcomeVerification
from app.models.organizational_memory import OrganizationalMemory, OrganizationalMemoryGovernanceDecision
from app.schemas.intelligence_learning_candidate import (
    IntelligenceLearningCandidateOutcomeRead,
    IntelligenceLearningCandidateVerificationRead,
)
from app.schemas.organizational_memory import (
    OrganizationalMemoryCandidateRead,
    OrganizationalMemoryCreate,
    OrganizationalMemoryGovernanceDecisionCreate,
    OrganizationalMemoryGovernanceDecisionListRead,
    OrganizationalMemoryGovernanceDecisionRead,
    OrganizationalMemoryListRead,
    OrganizationalMemoryRead,
    OrganizationalMemoryStateRead,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.organizational_memory_service import (
    create_organizational_memory,
    memory_governance_mutation_transaction,
    memory_mutation_transaction,
    record_memory_governance_decision,
    resolve_current_memory_governance,
    resolve_memory_reference,
)
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["organizational-memory"])

_ENDPOINT_CREATE_MEMORY = "POST /intelligence/organizational-memory"
_ENDPOINT_CREATE_GOVERNANCE_DECISION = "POST /intelligence/organizational-memory/{memory_id}/governance-decisions"


def _memory_to_read(db: Session, record: OrganizationalMemory) -> OrganizationalMemoryRead:
    candidate_read = None
    candidate = db.get(IntelligenceLearningCandidate, record.learning_candidate_id)
    if candidate is not None:
        outcome_read = None
        outcome = db.get(IntelligenceOutcome, candidate.outcome_id)
        if outcome is not None:
            outcome_read = IntelligenceLearningCandidateOutcomeRead(
                id=outcome.id,
                decision_id=outcome.decision_id,
                classification=outcome.classification,
                outcome_at=outcome.outcome_at,
                site_id=outcome.site_id,
                linked_action_id=outcome.linked_action_id,
            )

        verification_read = None
        verification = db.get(IntelligenceOutcomeVerification, candidate.verification_id)
        if verification is not None:
            verification_read = IntelligenceLearningCandidateVerificationRead(
                id=verification.id, status=verification.status, verified_at=verification.verified_at
            )

        candidate_read = OrganizationalMemoryCandidateRead(
            id=candidate.id,
            outcome_id=candidate.outcome_id,
            verification_id=candidate.verification_id,
            outcome=outcome_read,
            verification=verification_read,
        )

    return OrganizationalMemoryRead(
        id=record.id,
        organization_id=record.organization_id,
        learning_candidate_id=record.learning_candidate_id,
        memory_type=record.memory_type,
        title=record.title,
        memory_content=record.memory_content,
        rationale=record.rationale,
        learning_candidate=candidate_read,
        created_by_user_id=record.created_by_user_id,
        created_by_api_client_id=record.created_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _governance_to_read(
    record: OrganizationalMemoryGovernanceDecision,
) -> OrganizationalMemoryGovernanceDecisionRead:
    return OrganizationalMemoryGovernanceDecisionRead(
        id=record.id,
        organization_id=record.organization_id,
        memory_id=record.memory_id,
        status=record.status,
        rationale=record.rationale,
        decided_at=record.decided_at,
        decided_by_user_id=record.decided_by_user_id,
        decided_by_api_client_id=record.decided_by_api_client_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/organizational-memory",
    response_model=OrganizationalMemoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_intelligence_organizational_memory(
    body: OrganizationalMemoryCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryRead:
    """Creates (or returns the existing) organizational memory for
    `body.learning_candidate_id`. Never mutates the candidate or its
    governance history — the one write this route performs is the new
    `OrganizationalMemory` row itself, and only when one does not
    already exist for this candidate."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    request_hash = compute_request_hash(body.model_dump_json().encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_MEMORY,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return OrganizationalMemoryRead.model_validate(lookup.response_body)

    with memory_mutation_transaction(db):
        memory, created = create_organizational_memory(
            db,
            organization_id=organization_id,
            learning_candidate_id=body.learning_candidate_id,
            memory_type=body.memory_type,
            title=body.title,
            memory_content=body.memory_content,
            rationale=body.rationale,
            created_by_user_id=context.user_id,
            created_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        if created:
            audit_service.log(
                db,
                action=AuditAction.ORGANIZATIONAL_MEMORY_CREATED,
                resource_type="OrganizationalMemory",
                resource_id=memory.id,
                organization_id=organization_id,
                user_id=context.user_id,
                metadata={
                    "learning_candidate_id": str(memory.learning_candidate_id),
                    "memory_type": memory.memory_type.value,
                    "caller_kind": context.kind,
                },
                request_id=request_id,
                commit=False,
            )
        result = _memory_to_read(db, memory)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_MEMORY,
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
    "/organizational-memory",
    response_model=OrganizationalMemoryListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_intelligence_organizational_memory(
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    learning_candidate_id: uuid.UUID | None = Query(default=None),
    memory_type: str | None = Query(default=None, description="Filter to one OrganizationalMemoryType value."),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: only memories with created_at <= as_of are returned."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryListRead:
    """No memory is ever mutated after creation -- at most one exists
    per `learning_candidate_id` (the `UNIQUE(organization_id,
    learning_candidate_id)` constraint), so this list is simply every
    memory this organization currently has, newest first."""
    organization_id = resolve_authorized_organization_id(context, organization_id)

    conditions = [OrganizationalMemory.organization_id == organization_id]
    if learning_candidate_id:
        conditions.append(OrganizationalMemory.learning_candidate_id == learning_candidate_id)
    if memory_type:
        conditions.append(OrganizationalMemory.memory_type == memory_type)
    if as_of is not None:
        conditions.append(OrganizationalMemory.created_at <= as_of)

    total = db.execute(select(func.count()).select_from(OrganizationalMemory).where(*conditions)).scalar_one()
    rows = (
        db.execute(
            select(OrganizationalMemory)
            .where(*conditions)
            .order_by(OrganizationalMemory.created_at.desc(), OrganizationalMemory.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return OrganizationalMemoryListRead(
        items=[_memory_to_read(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/organizational-memory/{memory_id}",
    response_model=OrganizationalMemoryRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_intelligence_organizational_memory(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryRead:
    """A memory from a different organization (or a nonexistent id) is a
    404, never a 403 -- mirrors every other single-resource GET in this
    codebase."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    memory = resolve_memory_reference(db, organization_id=organization_id, memory_id=memory_id)
    return _memory_to_read(db, memory)


@router.post(
    "/organizational-memory/{memory_id}/governance-decisions",
    response_model=OrganizationalMemoryGovernanceDecisionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_rate_limit(RateLimitClass.WRITE))],
)
def create_organizational_memory_governance_decision(
    memory_id: uuid.UUID,
    body: OrganizationalMemoryGovernanceDecisionCreate,
    organization_id: uuid.UUID = Query(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    request_id: str | None = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryGovernanceDecisionRead:
    """Records one human governance judgment (`ACTIVE`/`RETRACTED`)
    about one existing organizational memory. Never mutates the memory
    itself, its originating candidate, outcome, or verification -- the
    one write this route performs is the new `OrganizationalMemory
    GovernanceDecision` row. Unlike memory creation, this is **not**
    idempotent by a natural key: a second call is a legitimate new
    governance event (e.g. later retracting, or later reinstating, a
    memory) and creates a second row, preserving history -- only the
    `Idempotency-Key` header protects against an accidental duplicate
    submission of the *same* request."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    resolve_memory_reference(db, organization_id=organization_id, memory_id=memory_id)

    request_hash = compute_request_hash(f"{memory_id}:{body.model_dump_json()}".encode("utf-8"))
    lookup = check_and_replay(
        db,
        endpoint=_ENDPOINT_CREATE_GOVERNANCE_DECISION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        organization_id=organization_id,
        api_client_id=context.api_client_id,
        user_id=context.user_id,
    )
    if lookup.is_replay:
        return OrganizationalMemoryGovernanceDecisionRead.model_validate(lookup.response_body)

    with memory_governance_mutation_transaction(db):
        record = record_memory_governance_decision(
            db,
            organization_id=organization_id,
            memory_id=memory_id,
            status=body.status,
            rationale=body.rationale,
            decided_by_user_id=context.user_id,
            decided_by_api_client_id=context.api_client_id,
            request_id=request_id,
        )
        audit_service.log(
            db,
            action=AuditAction.ORGANIZATIONAL_MEMORY_GOVERNANCE_DECISION_RECORDED,
            resource_type="OrganizationalMemoryGovernanceDecision",
            resource_id=record.id,
            organization_id=organization_id,
            user_id=context.user_id,
            metadata={
                "memory_id": str(memory_id),
                "status": record.status.value,
                "caller_kind": context.kind,
            },
            request_id=request_id,
            commit=False,
        )
        result = _governance_to_read(record)
        store_response(
            db,
            endpoint=_ENDPOINT_CREATE_GOVERNANCE_DECISION,
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
    "/organizational-memory/{memory_id}/governance-decisions",
    response_model=OrganizationalMemoryGovernanceDecisionListRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def list_organizational_memory_governance_decisions(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    as_of: datetime | None = Query(
        default=None, description="Point-in-time cutoff: only decisions with created_at <= as_of are returned."
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryGovernanceDecisionListRead:
    """No governance decision is ever mutated after creation -- this
    list, ordered newest-first, *is* the correction/audit history for
    this memory's governance. 404s (rather than an empty list) if
    `memory_id` itself does not belong to this organization."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    resolve_memory_reference(db, organization_id=organization_id, memory_id=memory_id)

    conditions = [
        OrganizationalMemoryGovernanceDecision.organization_id == organization_id,
        OrganizationalMemoryGovernanceDecision.memory_id == memory_id,
    ]
    if as_of is not None:
        conditions.append(OrganizationalMemoryGovernanceDecision.created_at <= as_of)

    total = db.execute(
        select(func.count()).select_from(OrganizationalMemoryGovernanceDecision).where(*conditions)
    ).scalar_one()
    rows = (
        db.execute(
            select(OrganizationalMemoryGovernanceDecision)
            .where(*conditions)
            .order_by(
                OrganizationalMemoryGovernanceDecision.created_at.desc(),
                OrganizationalMemoryGovernanceDecision.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return OrganizationalMemoryGovernanceDecisionListRead(
        items=[_governance_to_read(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/organizational-memory/{memory_id}/state",
    response_model=OrganizationalMemoryStateRead,
    dependencies=[Depends(require_rate_limit(RateLimitClass.READ))],
)
def get_organizational_memory_state(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID = Query(...),
    as_of: datetime | None = Query(
        default=None,
        description="Point-in-time cutoff applied to the resolved governance decision. Omit for the current, unfiltered view.",
    ),
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
) -> OrganizationalMemoryStateRead:
    """Combines the memory and its resolved current governance decision
    (or `None` if never governed -- the implicit `ACTIVE` state) into
    one response -- mirrors `IntelligenceLearningCandidateStateRead`'s
    own identical shape. Nothing here is persisted; every field is
    recomputed live on each call."""
    organization_id = resolve_authorized_organization_id(context, organization_id)
    memory = resolve_memory_reference(db, organization_id=organization_id, memory_id=memory_id)

    current_governance = resolve_current_memory_governance(
        db, organization_id=organization_id, memory_id=memory_id, as_of=as_of
    )

    return OrganizationalMemoryStateRead(
        memory=_memory_to_read(db, memory),
        current_governance=_governance_to_read(current_governance) if current_governance is not None else None,
    )


__all__ = ["router"]
