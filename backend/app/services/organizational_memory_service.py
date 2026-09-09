"""OrganizationalMemory service — SIE Milestone 40: Organizational
Memory Architecture. The one write path for
`app/api/v1/organizational_memory.py`, mirroring `app/services/
intelligence_learning_candidate_service.py`'s own shape exactly, plus
the governance-decision functions this milestone introduces.

    POST /intelligence/organizational-memory
        -> resolve_candidate_reference()        -- reused verbatim from
                                                    intelligence_learning_candidate_service,
                                                    never forked (M40 spec §16)
        -> resolve_current_governance()         -- reused verbatim -- the one
                                                    write-time gate: 422 unless the
                                                    candidate's resolved current
                                                    governance decision is ACCEPTED
        -> memory_mutation_transaction():
               OrganizationalMemory row (or the existing one, idempotent by
               construction -- see that model's own docstring) + AuditLog entry,
               one commit

    POST /intelligence/organizational-memory/{id}/governance-decisions
        -> resolve_memory_reference()
        -> memory_governance_mutation_transaction():
               OrganizationalMemoryGovernanceDecision row + AuditLog entry

No function in this module ever infers organizational memory or governs
it automatically -- every `OrganizationalMemory` is the direct, explicit
result of one `POST /intelligence/organizational-memory` call against an
already-`ACCEPTED` learning candidate, and every governance decision
about a memory is the direct, explicit result of one
`POST .../governance-decisions` call. See
`app/models/organizational_memory.py`'s own docstring for the full
architectural rationale, and `docs/ORGANIZATIONAL_MEMORY_V0_1.md` for
the explicit statement that this milestone stops at the durable-memory
boundary -- it does not yet determine how SIE uses that memory (M41).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.models.organizational_memory import OrganizationalMemory, OrganizationalMemoryGovernanceDecision
from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus, OrganizationalMemoryType
from app.services.intelligence_learning_candidate_service import resolve_candidate_reference, resolve_current_governance

__all__ = [
    "memory_mutation_transaction",
    "memory_governance_mutation_transaction",
    "resolve_memory_reference",
    "create_organizational_memory",
    "resolve_current_memory_governance",
    "record_memory_governance_decision",
]


@contextmanager
def memory_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `OrganizationalMemory`
    write -- identical shape to `intelligence_learning_candidate_
    service.candidate_mutation_transaction()`. Commits once on success;
    rolls back once and re-raises, unchanged, on any exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


@contextmanager
def memory_governance_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one memory governance-decision
    write -- kept as its own named function (rather than reusing
    `memory_mutation_transaction()` under a generic name) so each
    transaction boundary reads as exactly what it protects, mirroring
    `intelligence_learning_candidate_service.governance_mutation_
    transaction()`'s own identical one-context-manager-per-write-kind
    convention."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def resolve_memory_reference(
    db: Session, *, organization_id: uuid.UUID, memory_id: uuid.UUID
) -> OrganizationalMemory:
    """The identical "does this id belong to this organization" shape as
    `intelligence_learning_candidate_service.resolve_candidate_
    reference()`, applied to `OrganizationalMemory`. A nonexistent id or
    one from a different organization is a 404, never a silent
    cross-tenant read."""
    memory = db.execute(
        select(OrganizationalMemory).where(
            OrganizationalMemory.id == memory_id,
            OrganizationalMemory.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory_id not found in this organization.")
    return memory


def create_organizational_memory(
    db: Session,
    *,
    organization_id: uuid.UUID,
    learning_candidate_id: uuid.UUID,
    memory_type: OrganizationalMemoryType,
    title: str,
    memory_content: str,
    rationale: str,
    created_by_user_id: uuid.UUID | None,
    created_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> tuple[OrganizationalMemory, bool]:
    """Create (or return the existing) `OrganizationalMemory` for
    `learning_candidate_id`. Returns `(row, created)` -- `created=False`
    when a memory already existed for this candidate (idempotent by
    construction, mirrors `intelligence_learning_candidate_service.
    create_learning_candidate()`'s own identical "existing row returned,
    no duplicate, no error" precedent -- see `OrganizationalMemory`'s own
    docstring for the full "Idempotent by construction" rationale).

    `learning_candidate_id` is resolved against `organization_id` first
    (404 before any row is touched, tenant isolation structural not
    merely checked after the fact -- identical discipline to
    `create_learning_candidate()`). The governance gate (M40 spec §5) is
    the one write-time check -- reuses `resolve_current_governance()`
    verbatim, never forked: 422 unless the candidate's resolved current
    governance decision exists and is `ACCEPTED`. A never-governed
    (pending) or `REJECTED` candidate is rejected exactly the same way."""
    candidate = resolve_candidate_reference(db, organization_id=organization_id, candidate_id=learning_candidate_id)

    existing = db.execute(
        select(OrganizationalMemory).where(
            OrganizationalMemory.organization_id == organization_id,
            OrganizationalMemory.learning_candidate_id == learning_candidate_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    current_governance = resolve_current_governance(
        db, organization_id=organization_id, candidate_id=learning_candidate_id
    )
    if current_governance is None or current_governance.status != IntelligenceLearningCandidateGovernanceStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Learning candidate is not ACCEPTED (either never governed, or REJECTED); "
                "only an ACCEPTED learning candidate may become organizational memory."
            ),
        )

    memory = OrganizationalMemory(
        organization_id=organization_id,
        learning_candidate_id=candidate.id,
        memory_type=memory_type,
        title=title,
        memory_content=memory_content,
        rationale=rationale,
        created_by_user_id=created_by_user_id,
        created_by_api_client_id=created_by_api_client_id,
        request_id=request_id,
    )
    db.add(memory)
    db.flush()  # populates memory.id/created_at/updated_at, without committing
    return memory, True


def resolve_current_memory_governance(
    db: Session, *, organization_id: uuid.UUID, memory_id: uuid.UUID, as_of: datetime | None = None
) -> OrganizationalMemoryGovernanceDecision | None:
    """The deterministic "resolved current state" for one memory's
    governance history -- identical rule to `intelligence_learning_
    candidate_service.resolve_current_governance()`: the single most
    recent row, ordered `created_at DESC, id DESC`. `None` when no
    governance decision has ever been recorded -- the implicit `ACTIVE`
    state (see `OrganizationalMemoryGovernanceStatus`'s own docstring for
    why this differs from M39's own "absence = pending" convention).

    `as_of`, when supplied, restricts to rows with `created_at <= as_of`
    -- a governance decision recorded after `as_of` must not appear in a
    historical reconstruction, mirroring M38/M39's identical `as_of`
    rule."""
    conditions = [
        OrganizationalMemoryGovernanceDecision.organization_id == organization_id,
        OrganizationalMemoryGovernanceDecision.memory_id == memory_id,
    ]
    if as_of is not None:
        conditions.append(OrganizationalMemoryGovernanceDecision.created_at <= as_of)
    return db.execute(
        select(OrganizationalMemoryGovernanceDecision)
        .where(*conditions)
        .order_by(
            OrganizationalMemoryGovernanceDecision.created_at.desc(),
            OrganizationalMemoryGovernanceDecision.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def record_memory_governance_decision(
    db: Session,
    *,
    organization_id: uuid.UUID,
    memory_id: uuid.UUID,
    status: OrganizationalMemoryGovernanceStatus,
    rationale: str,
    decided_by_user_id: uuid.UUID | None,
    decided_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> OrganizationalMemoryGovernanceDecision:
    """Builds and `db.add()`s (never commits -- the caller's own
    `memory_governance_mutation_transaction()` block does that) one
    `OrganizationalMemoryGovernanceDecision` row. Performs no validation
    itself beyond what the caller (the API route) has already resolved
    (`memory_id` via `resolve_memory_reference()`) -- mirrors
    `intelligence_learning_candidate_service.record_governance_
    decision()`'s own "callers resolve, this function only persists"
    split. `decided_at` is server-derived (`default=utcnow` on the model
    column) -- see that column's own docstring for why no backdating
    discipline is needed for a governance action."""
    record = OrganizationalMemoryGovernanceDecision(
        organization_id=organization_id,
        memory_id=memory_id,
        status=status,
        rationale=rationale,
        decided_by_user_id=decided_by_user_id,
        decided_by_api_client_id=decided_by_api_client_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()  # populates record.id/decided_at/created_at/updated_at, without committing
    return record
