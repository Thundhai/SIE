"""Risk Assessment domain service — SIE Milestone 25: Enterprise Risk
Assessment Foundation v0.1. `app/api/v1/risk_assessments.py`'s one
delegate for tenant-safe reference validation, lifecycle transitions,
audit wiring, and its own mutation transaction boundary — mirrors
`app/services/safety_action_service.py`'s own established shape exactly.

**Transaction boundary.** Every `RiskAssessment`/`RiskAssessmentFinding`
mutation wraps its entire body in `risk_assessment_mutation_transaction()`
below — the identical "one commit, or none of it persists" guarantee
`app/services/safety_action_service.py::action_mutation_transaction()`
already established, applied to this domain's own writes (the
assessment/finding row itself, its `AuditLog` entry, and — for
`open_new_version()` — the previous version's `SUPERSEDED` transition,
all in one transaction).

**Reference validation reuses the existing validators, never a second
implementation.** `validate_site_reference`/`validate_owner_reference`
are imported directly from `safety_action_service` — both are already
fully generic ("does this site/user belong to this organization"), not
Actions-specific despite living in that module; duplicating them here
would be exactly the kind of second, competing implementation this
codebase avoids elsewhere (see e.g. `app/intelligence/enterprise_anomaly.py`
reusing `app/intelligence/enterprise_indicators.py`'s predicates).

**Evidence validation (item 8).** `EVENT`/`ACTION`/`KNOWLEDGE_DOCUMENT`
evidence each get their own tenant-scoped existence check below, mirroring
`validate_site_reference`'s own "404 whether it doesn't exist at all or
belongs to a different organization" pattern exactly (never a
distinguishing signal that would leak a foreign record's existence).
`ANOMALY`/`PATTERN`/`ASSOCIATION`/`OTHER` evidence reference a *computed*,
non-persisted intelligence result — no existence check applies; the
schema layer (`app/schemas/risk_assessment.py`) already forbids a
`reference_id` for those types.

**SIE Milestone 26: Formal Enterprise Risk Assessment Engine v0.2 —
`record_history()`.** Every mutating route now also writes a
`RiskAssessmentHistory` row (`app/models/risk_assessment_history.py`),
in the exact same `assessment_mutation_transaction()` block as the
assessment/finding row itself, its `AuditLog` entry, and (for
`POST /risk-assessments`) the replayable `IdempotencyKey` response --
"Assessment + Finding + History + Audit + Idempotency... a single
transaction boundary" (item 9, "the lesson from Milestone 17"): a
failure anywhere in that block rolls all of it back, never a partially
-written mutation. `record_history()` mirrors
`safety_action_service.record_history()`'s own `commit=False` contract
exactly.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.enterprise_intelligence_service import EnterpriseIntelligenceResult, compute_enterprise_intelligence
from app.models.knowledge_document import KnowledgeDocument
from app.models.risk_assessment import RiskAssessment, RiskAssessmentFinding
from app.models.risk_assessment_enums import (
    ASSESSMENT_EDITABLE_STATUSES,
    FindingStatus,
    RiskAssessmentScope,
    RiskAssessmentStatus,
    RiskCandidateStatus,
    RiskEvidenceType,
    is_allowed_assessment_transition,
    is_allowed_finding_transition,
)
from app.models.risk_assessment_finding_action import RiskAssessmentFindingAction
from app.models.risk_assessment_history import RiskAssessmentHistory, RiskAssessmentHistoryChangeType
from app.models.safety_action import SafetyAction
from app.risk_assessment.risk_matrix import calculate_risk
from app.services.audit_service import AuditAction, audit_service
from app.services.safety_action_service import (
    validate_owner_reference,
    validate_site_reference,
    validate_source_event_reference,
)

__all__ = [
    "AuditAction",
    "MAX_TITLE_LENGTH",
    "RiskAssessmentHistoryChangeType",
    "assessment_mutation_transaction",
    "audit_assessment_event",
    "calculate_and_set_inherent_risk",
    "calculate_and_set_residual_risk",
    "compute_intelligence_context",
    "create_finding_action_relationship",
    "delete_finding_action_relationship",
    "get_finding_action_relationship",
    "is_rated_finding",
    "list_finding_action_relationships",
    "list_findings_linked_to_action",
    "normalize_as_utc",
    "open_new_version",
    "record_history",
    "require_editable",
    "require_finding_closable",
    "require_finding_transition",
    "require_transition",
    "resolve_action_reference",
    "supersede_previous_version_if_any",
    "utcnow",
    "validate_action_reference",
    "validate_event_reference",
    "validate_knowledge_document_reference",
    "validate_owner_reference",
    "validate_site_reference",
]

MAX_TITLE_LENGTH = 255


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_as_utc(value: datetime) -> datetime:
    """Normalize a possibly offset-naive `datetime` (SQLite does not
    round-trip `tzinfo` — a value read back via `db.refresh()` loses it
    even though it was written as UTC-aware) to UTC-aware, mirroring the
    identical, already-established pattern in
    `app/intelligence/enterprise_intelligence_service.py`,
    `app/intelligence/enterprise_anomaly.py`, and others."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@contextmanager
def assessment_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one risk-assessment-domain
    mutation — see module docstring. Identical contract to
    `app.services.safety_action_service.action_mutation_transaction()`:
    every write inside must `flush()`, never commit independently; this
    block commits once on success, or rolls back once (and re-raises) on
    any exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def validate_event_reference(db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID) -> None:
    """Thin, evidence-domain-named wrapper over
    `safety_action_service.validate_source_event_reference()` — the
    identical check (an EVENT evidence reference must belong to this
    organization), reused rather than duplicated."""
    validate_source_event_reference(db, organization_id=organization_id, source_event_id=event_id)


def resolve_action_reference(db: Session, *, organization_id: uuid.UUID, action_id: uuid.UUID) -> SafetyAction:
    """Like `validate_action_reference()` below, but returns the row —
    for the SIE Milestone 27 call sites that need the action itself
    (to read its current `title`/`status` for a response, or to attach
    origin metadata to it), not merely a yes/no existence check. The
    identical 404-whether-missing-or-foreign-organization rule applies."""
    action = db.execute(
        select(SafetyAction).where(SafetyAction.id == action_id, SafetyAction.organization_id == organization_id)
    ).scalar_one_or_none()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action reference not found in this organization.")
    return action


def validate_action_reference(db: Session, *, organization_id: uuid.UUID, action_id: uuid.UUID) -> None:
    resolve_action_reference(db, organization_id=organization_id, action_id=action_id)


def validate_knowledge_document_reference(db: Session, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """A knowledge-document evidence reference may point at this
    organization's own document *or* a GLOBAL one (`organization_id IS
    NULL`) — mirrors `app/api/deps_context.py`'s own "GLOBAL knowledge is
    not organization-scoped at all" precedent (item 16: reuse the
    existing knowledge architecture, never a second access rule for it)."""
    document = db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            (KnowledgeDocument.organization_id == organization_id) | (KnowledgeDocument.organization_id.is_(None)),
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="knowledge document reference not found or not accessible."
        )


def audit_assessment_event(
    db: Session,
    *,
    action_name: str,
    assessment: RiskAssessment,
    user_id: uuid.UUID | None,
    caller_kind: str,
    metadata: dict,
    commit: bool = False,
) -> None:
    audit_service.log(
        db,
        action=action_name,
        resource_type="RiskAssessment",
        resource_id=assessment.id,
        organization_id=assessment.organization_id,
        user_id=user_id,
        metadata={**metadata, "caller_kind": caller_kind, "status": assessment.status.value, "version": assessment.version},
        commit=commit,
    )


def calculate_and_set_inherent_risk(finding: RiskAssessmentFinding, *, likelihood: int, consequence: int) -> None:
    """The one place `inherent_risk_score`/`inherent_risk_classification`
    are ever set — always via `app/risk_assessment/risk_matrix.py`'s
    deterministic calculation, never `enterprise-risk-v1` (item 10).
    Also snapshots `RISK_ASSESSMENT_CALCULATION_VERSION` onto the finding
    (SIE Milestone 26, item 6 -- historical integrity for the
    methodology itself, not just the concept it rates)."""
    rating = calculate_risk(likelihood, consequence)
    finding.likelihood = rating.likelihood
    finding.consequence = rating.consequence
    finding.inherent_risk_score = rating.score
    finding.inherent_risk_classification = rating.classification
    finding.inherent_risk_methodology_version = rating.calculation_version


def calculate_and_set_residual_risk(finding: RiskAssessmentFinding, *, likelihood: int, consequence: int) -> None:
    """Independently assessed — never a percentage reduction mathematically
    derived from `inherent_risk_score` and a control-effectiveness value
    (item 13). The caller supplies its own likelihood/consequence
    judgment, exactly like `calculate_and_set_inherent_risk()` above; the
    two are computed by the identical, but separately invoked,
    `calculate_risk()` function."""
    rating = calculate_risk(likelihood, consequence)
    finding.residual_likelihood = rating.likelihood
    finding.residual_consequence = rating.consequence
    finding.residual_risk_score = rating.score
    finding.residual_risk_classification = rating.classification
    finding.residual_risk_methodology_version = rating.calculation_version


def require_editable(assessment: RiskAssessment) -> None:
    """Item 4/23: `DRAFT`/`IN_REVIEW` are editable, `APPROVED`/
    `SUPERSEDED` are not — enforced here, the one place every mutating
    route calls through (mirrors `is_allowed_action_transition`'s own
    "one source of truth" reasoning, applied to editability rather than
    a status transition)."""
    if assessment.status not in ASSESSMENT_EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Assessment is {assessment.status.value} and is not editable.",
        )


def require_transition(assessment: RiskAssessment, target: RiskAssessmentStatus) -> None:
    if not is_allowed_assessment_transition(assessment.status.value, target.value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition assessment from {assessment.status.value} to {target.value}.",
        )


def require_finding_transition(finding: RiskAssessmentFinding, target: FindingStatus) -> None:
    """SIE Milestone 27. Mirrors `require_transition()` above, applied to
    `FindingStatus` instead of `RiskAssessmentStatus` — the one place
    `FindingStatus.CLOSED`'s own terminal-ness (and `OPEN`/`ADDRESSED`'s
    mutual reachability) is enforced, whether the target is reached via
    the generic `PATCH .../findings/{finding_id}` `status` field or the
    dedicated `close_finding()` route."""
    if not is_allowed_finding_transition(finding.status.value, target.value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition finding from {finding.status.value} to {target.value}.",
        )


def require_finding_closable(finding: RiskAssessmentFinding, *, closure_reason: str) -> None:
    """SIE Milestone 27's own "closure governance" gate — the one place
    `FindingStatus.CLOSED` may ever be reached. Deliberately never keyed
    off a *linked action's* status (the milestone's own explicit "that
    would be unsafe" example: `if action.status == COMPLETED:
    finding.status = CLOSED`) — a completed action is not evidence that
    closing this finding is warranted, only that a response was carried
    out. Two real, checkable conditions instead:

    1. `closure_reason` (required by the schema layer to be non-blank,
       re-checked here defensively) — item 6's own "human-controlled and
       explicitly recorded" requirement; there is no such thing as an
       inferred or default closure reason.
    2. The finding must have actually been rated (`likelihood` is not
       `None`) — closing a finding whose risk was never even assessed
       (an un-rated candidate, or a freshly-created finding nobody has
       looked at yet) is never a legitimate "we decided this is
       resolved," it is simply nothing having happened yet.

    `require_finding_transition()` (above) separately guarantees `CLOSED`
    is actually reachable from the finding's current status at all."""
    if not closure_reason or not closure_reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="closure_reason is required to close a finding -- closure must be explicit and recorded.",
        )
    if finding.likelihood is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A finding must be rated (likelihood/consequence supplied) before it can be closed.",
        )


def open_new_version(
    db: Session,
    *,
    previous: RiskAssessment,
    created_by_user_id: uuid.UUID | None,
    created_by_api_client_id: uuid.UUID | None,
) -> RiskAssessment:
    """Item 18/23: "an approved assessment should require a new version
    for substantive changes." Only an `APPROVED` assessment may be
    superseded (item 4's own linear lifecycle — a `DRAFT`/`IN_REVIEW`
    assessment is simply still editable in place; a `SUPERSEDED` one is
    already historical). The new row starts a fresh `DRAFT` in the same
    `lineage_id`, `version + 1`, `supersedes_id = previous.id` — the
    previous row itself is never edited; only its `status` transitions to
    `SUPERSEDED` (a real, permitted transition per
    `is_allowed_assessment_transition`), inside the same transaction as
    the new row's creation, so either both happen or neither does."""
    if previous.status != RiskAssessmentStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only an APPROVED assessment can be superseded by a new version.",
        )
    new_id = uuid.uuid4()
    new_version = RiskAssessment(
        id=new_id,
        organization_id=previous.organization_id,
        scope=previous.scope,
        site_id=previous.site_id,
        title=previous.title,
        reference=previous.reference,
        assessment_type=previous.assessment_type,
        status=RiskAssessmentStatus.DRAFT,
        lineage_id=previous.lineage_id,
        version=previous.version + 1,
        supersedes_id=previous.id,
        assessment_date=previous.assessment_date,
        as_of=previous.as_of,
        window_days=previous.window_days,
        assessor_user_id=previous.assessor_user_id,
        methodology_version=settings.RISK_ASSESSMENT_METHODOLOGY_VERSION,
        created_by_user_id=created_by_user_id,
        created_by_api_client_id=created_by_api_client_id,
    )
    # Deliberately does NOT mark `previous` SUPERSEDED here -- that would
    # leave a window with zero APPROVED assessments in this lineage while
    # the new version is still being drafted/reviewed. The previous
    # version stays APPROVED (and fully active/queryable) until the new
    # one is *itself* approved -- see
    # `supersede_previous_version_if_any()` below, called only from the
    # approve step.
    db.add(new_version)
    db.flush()
    return new_version


def supersede_previous_version_if_any(
    db: Session,
    assessment: RiskAssessment,
    *,
    changed_by_user_id: uuid.UUID | None = None,
    changed_by_api_client_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> RiskAssessment | None:
    """Called only when `assessment` is being approved (item 18): if it
    was opened via `open_new_version()` (`supersedes_id` set), the
    version it replaces transitions `APPROVED -> SUPERSEDED` at this
    moment, not at creation time -- see `open_new_version()`'s own
    docstring for why. A no-op if `supersedes_id` is unset, or if the
    referenced version is somehow no longer `APPROVED` (defensive; the
    create-time check in `open_new_version()` already guarantees this in
    the normal flow). Records a `RiskAssessmentHistory` entry against the
    *previous* version itself (SIE Milestone 26) -- the row a client
    rendering that older assessment's own history would need to see why
    it stopped being current."""
    if assessment.supersedes_id is None:
        return None
    previous = db.execute(
        select(RiskAssessment).where(
            RiskAssessment.id == assessment.supersedes_id, RiskAssessment.organization_id == assessment.organization_id
        )
    ).scalar_one_or_none()
    if previous is not None and previous.status == RiskAssessmentStatus.APPROVED:
        previous.status = RiskAssessmentStatus.SUPERSEDED
        db.flush()
        record_history(
            db,
            assessment=previous,
            change_type=RiskAssessmentHistoryChangeType.ASSESSMENT_SUPERSEDED,
            from_status=RiskAssessmentStatus.APPROVED.value,
            to_status=RiskAssessmentStatus.SUPERSEDED.value,
            changed_by_user_id=changed_by_user_id,
            changed_by_api_client_id=changed_by_api_client_id,
            request_id=request_id,
            comment=f"Superseded by version {assessment.version} (id={assessment.id}).",
        )
    return previous


def compute_intelligence_context(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: RiskAssessmentScope,
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_days: int,
) -> EnterpriseIntelligenceResult:
    """Item 26: read-only, computed fresh on every read from the
    assessment's own persisted `organization_id`/`site_id`/`as_of` —
    never stored, never mutated merely because an assessment was
    created (an identical `as_of` always reproduces the identical
    result, since every Milestone 22-24 computation is itself
    point-in-time-correct and deterministic — see
    `app/intelligence/enterprise_intelligence_service.py`'s own
    docstring). `LOCATION` scope computes at organization scope (item
    5's own "no first-class Location entity yet" — see
    `RiskAssessmentScope`'s own docstring)."""
    compute_scope = "site" if scope == RiskAssessmentScope.SITE else "organization"
    return compute_enterprise_intelligence(
        db,
        organization_id=organization_id,
        scope=compute_scope,
        site_id=site_id if scope == RiskAssessmentScope.SITE else None,
        as_of=normalize_as_utc(as_of),
        window_days=window_days,
    )


def is_rated_finding(finding: RiskAssessmentFinding) -> bool:
    """A finding may only ever carry a likelihood/consequence rating when
    it is not a pending/rejected candidate (item 15/27's own "candidate ≠
    approved risk" boundary) -- `candidate_status is None` (a manually
    authored finding) or `ACCEPTED` (a reviewed-and-accepted candidate)."""
    return finding.candidate_status is None or finding.candidate_status == RiskCandidateStatus.ACCEPTED


# --- Finding <-> Action relationship (SIE Milestone 27) -------------------------------------
#
# See app/models/risk_assessment_finding_action.py's own docstring for
# the full "why a new table, why it supplements rather than replaces
# linked_action_id" rationale. Every function below is a plain query/
# mutation helper -- the caller (app/api/v1/risk_assessments.py) is
# still the one place that resolves tenant ownership of the finding/
# action first and writes the accompanying RiskAssessmentHistory/
# AuditLog entries, inside its own assessment_mutation_transaction().


def get_finding_action_relationship(
    db: Session, *, finding_id: uuid.UUID, action_id: uuid.UUID
) -> RiskAssessmentFindingAction | None:
    return db.execute(
        select(RiskAssessmentFindingAction).where(
            RiskAssessmentFindingAction.finding_id == finding_id, RiskAssessmentFindingAction.action_id == action_id
        )
    ).scalar_one_or_none()


def create_finding_action_relationship(
    db: Session,
    *,
    finding: RiskAssessmentFinding,
    action_id: uuid.UUID,
    changed_by_user_id: uuid.UUID | None,
    changed_by_api_client_id: uuid.UUID | None,
) -> tuple[RiskAssessmentFindingAction, bool]:
    """Idempotent by construction (item 10's own "safely retryable"
    requirement, and `RiskAssessmentFindingAction`'s own unique
    constraint): linking the same action to the same finding twice
    returns the existing row, `created=False`, rather than raising or
    creating a duplicate. Only `db.add()`s/`flush()`es -- the caller's
    own `assessment_mutation_transaction()` commits."""
    existing = get_finding_action_relationship(db, finding_id=finding.id, action_id=action_id)
    if existing is not None:
        return existing, False
    relationship_row = RiskAssessmentFindingAction(
        organization_id=finding.organization_id,
        finding_id=finding.id,
        action_id=action_id,
        created_by_user_id=changed_by_user_id,
        created_by_api_client_id=changed_by_api_client_id,
    )
    db.add(relationship_row)
    db.flush()
    return relationship_row, True


def delete_finding_action_relationship(db: Session, *, finding_id: uuid.UUID, action_id: uuid.UUID) -> bool:
    """Idempotent: unlinking an action that isn't currently linked is a
    no-op, returning `False` rather than raising -- a retried unlink call
    must never fail merely because an earlier attempt already succeeded."""
    existing = get_finding_action_relationship(db, finding_id=finding_id, action_id=action_id)
    if existing is None:
        return False
    db.delete(existing)
    db.flush()
    return True


def list_finding_action_relationships(db: Session, *, finding_id: uuid.UUID) -> list[RiskAssessmentFindingAction]:
    return list(
        db.execute(
            select(RiskAssessmentFindingAction)
            .where(RiskAssessmentFindingAction.finding_id == finding_id)
            .order_by(RiskAssessmentFindingAction.created_at)
        )
        .scalars()
        .all()
    )


def list_findings_linked_to_action(
    db: Session, *, action_id: uuid.UUID, organization_id: uuid.UUID
) -> list[RiskAssessmentFinding]:
    """SIE Milestone 27's own "view the originating finding from an
    action" / "action -> finding navigation" requirement -- every
    finding *currently* linked to this action (there may be more than
    one, e.g. the same corrective action addresses two related
    findings), tenant-scoped to the caller's own organization exactly
    like every other query in this module."""
    return list(
        db.execute(
            select(RiskAssessmentFinding)
            .join(RiskAssessmentFindingAction, RiskAssessmentFindingAction.finding_id == RiskAssessmentFinding.id)
            .where(
                RiskAssessmentFindingAction.action_id == action_id,
                RiskAssessmentFinding.organization_id == organization_id,
            )
            .order_by(RiskAssessmentFindingAction.created_at)
        )
        .scalars()
        .all()
    )


def record_history(
    db: Session,
    *,
    assessment: RiskAssessment,
    change_type: str,
    finding_id: uuid.UUID | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    changed_by_user_id: uuid.UUID | None,
    changed_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
    comment: str | None = None,
    commit: bool = False,
) -> RiskAssessmentHistory:
    """SIE Milestone 26, items 8-9. Mirrors
    `safety_action_service.record_history()`'s own `commit=False`
    contract exactly: every `app/api/v1/risk_assessments.py` call site
    passes `commit=False` (the default here, unlike that function's own
    `commit=True` default -- chosen because every call site in this
    module's own domain is already inside `assessment_mutation_transaction()`,
    with no call site left over that wants an independent commit), so
    this only `db.add()`s and `db.flush()`s, leaving the enclosing
    transaction to commit it together with the assessment/finding
    mutation and `AuditLog` entry it belongs with."""
    entry = RiskAssessmentHistory(
        organization_id=assessment.organization_id,
        assessment_id=assessment.id,
        finding_id=finding_id,
        change_type=change_type,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=changed_by_user_id,
        changed_by_api_client_id=changed_by_api_client_id,
        request_id=request_id,
        comment=comment,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry
