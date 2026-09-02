"""Terminology calibration service — the one read/write path for
`TerminologyMappingDecision` rows (see that model's own docstring for the
full lifecycle, scoping, and versioning rationale). SIE Real Enterprise
Terminology & Ontology Calibration v0.1.

    terminology_review.build_terminology_review()   [UNCHANGED, reused]
        -> create_review_candidates()                 REVIEW_CANDIDATE rows
        -> propose_mapping()                           -> PROPOSED (explicit human/admin input;
                                                            suggest_candidates() is a read-only hint,
                                                            never auto-applied)
        -> approve_mapping() / reject_mapping()        -> APPROVED / REJECTED (explicit,
                                                            authorized, audited)
        -> get_active_mapping() / build_active_mapping_index()
                                                        consulted by the ingestion-time resolver
                                                        (app/intelligence/terminology_calibration_adapter.py)

**Authorization is enforced here, not only at a future API boundary.**
Every mutating function below takes an `acting_user_id` and calls
`authorization_service.require(..., Permission.GOVERNANCE_MANAGE, ...)`
itself, unlike `app/predictions/model_registry.py::approve()` (which
trusts its caller because every caller today is the API router's own
`_authorize()` check). This milestone has no required API router yet, and
"unauthorized users cannot approve" (item 9) must hold regardless of how
this service is called — from a future router, a script, or a test —
so the guarantee lives on the operation itself. `GOVERNANCE_MANAGE` is
reused, not a new permission invented for this milestone: deciding what
enters the canonical ontology is the same kind of administrative,
governed decision `Permission.GOVERNANCE_MANAGE` already gates for model
approval (`app/api/v1/model_governance.py`), and `ROLE_PERMISSIONS`
already withholds it from `VIEWER`/`HSE_USER`/`HSE_ANALYST` — see
`app/services/permissions.py`.

**A term is never resolved into a canonical classification anywhere in
this module.** `suggest_candidates()` surfaces what the existing,
unmodified `terminology_mapping.py` alias table itself would say (a
`MAPPED` hit, or the candidate list for an `AMBIGUOUS` term) purely as a
read-only hint for whoever calls `propose_mapping()` — it never sets
`proposed_canonical_term` itself. Every `propose_mapping()` call requires
an explicit, caller-supplied term (or `None` — "preferable to guessing",
item 6's own words).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.terminology_mapping import MappingResult, _normalize_key
from app.intelligence.terminology_review import (
    TerminologyReviewEntry,
)
from app.models.terminology_mapping_decision import (
    TerminologyMappingDecision,
    TerminologyMappingDecisionStatus,
)
from app.services import hse_review_service
from app.services.audit_service import AuditAction, audit_service
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

_APPROVAL_PERMISSION = Permission.GOVERNANCE_MANAGE


class TerminologyMappingDecisionNotFoundError(ValueError):
    """Raised when `decision_id` does not exist or does not belong to
    `organization_id` — never distinguished from "not found" in the
    error itself, the same tenant-isolation-preserving non-disclosure
    every other resource in this codebase already practices."""


class TerminologyMappingDecisionStateError(ValueError):
    """Raised when an operation is attempted against a row in the wrong
    lifecycle state — e.g. approving a `REVIEW_CANDIDATE` that was never
    proposed, or mutating an already-terminal (`APPROVED`/`REJECTED`)
    row. A terminal row is frozen forever (see the model's own
    docstring); the only way to change an already-decided mapping is
    `open_new_version()`."""


def _require_owned_decision(db: Session, *, organization_id: uuid.UUID, decision_id: uuid.UUID) -> TerminologyMappingDecision:
    decision = db.execute(
        select(TerminologyMappingDecision).where(
            TerminologyMappingDecision.id == decision_id,
            TerminologyMappingDecision.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if decision is None:
        raise TerminologyMappingDecisionNotFoundError(
            f"No terminology mapping decision {decision_id} in organization {organization_id}."
        )
    return decision


# --- Item 6: read-only, informational suggestion (never auto-applied) ---------------------------


def suggest_candidates(domain: str, context: str | None, source_term: str) -> MappingResult:
    """What the existing, unmodified static alias table itself would say
    about `source_term` right now -- purely informational for a human
    calling `propose_mapping()` (e.g. surfacing an `AMBIGUOUS` term's own
    candidate list so a reviewer doesn't have to guess what the
    ambiguity even is). Never writes anything, never itself decides a
    `proposed_canonical_term`."""
    from app.intelligence.terminology_review import (
        _resolve,  # local import: private, review-module-internal helper
    )

    return _resolve(domain, context, source_term)


# --- Item 4: REVIEW_CANDIDATE — surfacing newly observed unresolved terms -----------------------


def create_review_candidates(
    db: Session,
    *,
    organization_id: uuid.UUID,
    source_system: str,
    entries: list[TerminologyReviewEntry],
    provenance: dict[str, Any] | None = None,
) -> list[TerminologyMappingDecision]:
    """One `REVIEW_CANDIDATE` row per unique `(domain, context,
    source_term)` among `entries` that `requires_review`
    (`UNKNOWN`/`AMBIGUOUS`) and does not already have a decision row in
    this scope -- an existing row (at any status, any version) is left
    completely untouched; this function only ever *adds* new candidates,
    never mutates a decision already in flight or already decided. Each
    new candidate is also queued in the existing HSE expert review queue
    (`hse_expert_review_service.queue_for_review`, `TERMINOLOGY_MAPPING`)
    for visibility -- reused, not duplicated (item 10)."""
    created: list[TerminologyMappingDecision] = []

    for entry in entries:
        if not entry.requires_review:
            continue

        existing = db.execute(
            select(TerminologyMappingDecision).where(
                TerminologyMappingDecision.organization_id == organization_id,
                TerminologyMappingDecision.source_system == source_system,
                TerminologyMappingDecision.domain == entry.domain,
                TerminologyMappingDecision.context == entry.context,
                TerminologyMappingDecision.source_term == entry.source_term,
            )
        ).scalars().first()
        if existing is not None:
            continue

        review = hse_review_service.queue_for_review(
            db, organization_id=organization_id, target_type="TERMINOLOGY_MAPPING",
            target_reference=f"{source_system}:{entry.domain}:{entry.context or ''}:{entry.source_term}",
            provenance={
                "domain": entry.domain, "context": entry.context, "source_term": entry.source_term,
                "review_status": entry.status, "occurrence_count": entry.occurrence_count,
            },
        )

        decision = TerminologyMappingDecision(
            organization_id=organization_id,
            source_system=source_system,
            domain=entry.domain,
            context=entry.context,
            source_term=entry.source_term,
            normalized_term=_normalize_key(entry.source_term),
            mapping_version=1,
            status=TerminologyMappingDecisionStatus.REVIEW_CANDIDATE,
            occurrence_count=entry.occurrence_count,
            example_source_record_ids=list(entry.example_source_record_ids),
            hse_expert_review_id=review.id,
            provenance=provenance or {},
        )
        db.add(decision)
        db.flush()
        audit_service.log(
            db, action=AuditAction.TERMINOLOGY_MAPPING_CANDIDATE_CREATED, resource_type="TerminologyMappingDecision",
            resource_id=decision.id, organization_id=organization_id,
            metadata={
                "source_system": source_system, "domain": entry.domain, "context": entry.context,
                "source_term": entry.source_term, "review_status": entry.status,
                "occurrence_count": entry.occurrence_count,
            },
        )
        created.append(decision)

    db.commit()
    for decision in created:
        db.refresh(decision)
    return created


# --- Item 6: PROPOSED — a candidate canonical term, not yet approved ----------------------------


def propose_mapping(
    db: Session,
    *,
    organization_id: uuid.UUID,
    decision_id: uuid.UUID,
    proposed_canonical_term: str | None,
    rationale: str,
    acting_user_id: uuid.UUID,
) -> TerminologyMappingDecision:
    """Moves a `REVIEW_CANDIDATE` (or an already-`PROPOSED` row, to
    revise the proposal before it's decided) to `PROPOSED`.
    `proposed_canonical_term=None` is explicitly allowed and expected
    when there is insufficient confidence to propose anything (item 6:
    "this is preferable to guessing") -- such a row can still be
    explicitly `REJECTED`, but `approve_mapping()` refuses to approve a
    proposal with no term. Requires `GOVERNANCE_MANAGE` -- proposing is
    still a deliberate administrative act, not automatic."""
    authorization_service.require(db, user_id=acting_user_id, permission=_APPROVAL_PERMISSION, organization_id=organization_id)

    decision = _require_owned_decision(db, organization_id=organization_id, decision_id=decision_id)
    if decision.is_terminal:
        raise TerminologyMappingDecisionStateError(
            f"Decision {decision_id} is already {decision.status} -- terminal decisions are frozen; "
            "use open_new_version() to propose a different mapping."
        )

    decision.status = TerminologyMappingDecisionStatus.PROPOSED
    decision.proposed_canonical_term = proposed_canonical_term
    decision.rationale = rationale
    decision.proposed_by_user_id = acting_user_id
    decision.proposed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(decision)

    audit_service.log(
        db, action=AuditAction.TERMINOLOGY_MAPPING_PROPOSED, resource_type="TerminologyMappingDecision",
        resource_id=decision.id, organization_id=organization_id, user_id=acting_user_id,
        metadata={
            "source_system": decision.source_system, "domain": decision.domain, "context": decision.context,
            "source_term": decision.source_term, "proposed_canonical_term": proposed_canonical_term,
            "mapping_version": decision.mapping_version,
        },
    )
    return decision


# --- Item 9: explicit, authorized, audited approval / rejection ---------------------------------


def approve_mapping(
    db: Session,
    *,
    organization_id: uuid.UUID,
    decision_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    notes: str | None = None,
) -> TerminologyMappingDecision:
    """The one operation in this whole milestone that makes a term
    eligible for canonical classification (see
    `TerminologyMappingDecision.is_eligible_for_canonical_classification`).
    Requires `GOVERNANCE_MANAGE` in `organization_id` -- an unauthorized
    caller, a viewer, or a caller acting against another organization's
    decision all fail here, before anything is written (item 9's own
    acceptance criteria, verified directly by
    tests/test_terminology_calibration.py)."""
    authorization_service.require(db, user_id=acting_user_id, permission=_APPROVAL_PERMISSION, organization_id=organization_id)

    decision = _require_owned_decision(db, organization_id=organization_id, decision_id=decision_id)
    if decision.status != TerminologyMappingDecisionStatus.PROPOSED:
        raise TerminologyMappingDecisionStateError(
            f"Decision {decision_id} is {decision.status}, not PROPOSED -- only a proposed mapping can be approved."
        )
    if not decision.proposed_canonical_term:
        raise TerminologyMappingDecisionStateError(
            f"Decision {decision_id} has no proposed_canonical_term -- refusing to approve nothing."
        )

    decision.status = TerminologyMappingDecisionStatus.APPROVED
    decision.reviewer_user_id = acting_user_id
    decision.decided_at = datetime.now(timezone.utc)
    if notes:
        decision.rationale = f"{decision.rationale or ''}\n[APPROVED] {notes}".strip()
    db.commit()
    db.refresh(decision)

    audit_service.log(
        db, action=AuditAction.TERMINOLOGY_MAPPING_APPROVED, resource_type="TerminologyMappingDecision",
        resource_id=decision.id, organization_id=organization_id, user_id=acting_user_id,
        metadata={
            "source_system": decision.source_system, "domain": decision.domain, "context": decision.context,
            "source_term": decision.source_term, "approved_canonical_term": decision.proposed_canonical_term,
            "mapping_version": decision.mapping_version,
        },
    )
    _close_linked_hse_review(db, decision, organization_id=organization_id, outcome="CORRECT", comment=notes)
    return decision


def reject_mapping(
    db: Session,
    *,
    organization_id: uuid.UUID,
    decision_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    reason: str,
) -> TerminologyMappingDecision:
    """Rejects a `REVIEW_CANDIDATE` or `PROPOSED` row -- the term
    remains permanently unresolved *for this version* (still
    `QUARANTINED` by ingestion, exactly like `UNKNOWN`; see item 11's own
    rule table). Requires `GOVERNANCE_MANAGE`, same as `approve_mapping()`."""
    authorization_service.require(db, user_id=acting_user_id, permission=_APPROVAL_PERMISSION, organization_id=organization_id)

    decision = _require_owned_decision(db, organization_id=organization_id, decision_id=decision_id)
    if decision.is_terminal:
        raise TerminologyMappingDecisionStateError(
            f"Decision {decision_id} is already {decision.status} -- terminal decisions are frozen."
        )

    decision.status = TerminologyMappingDecisionStatus.REJECTED
    decision.reviewer_user_id = acting_user_id
    decision.decided_at = datetime.now(timezone.utc)
    decision.rationale = f"{decision.rationale or ''}\n[REJECTED] {reason}".strip()
    db.commit()
    db.refresh(decision)

    audit_service.log(
        db, action=AuditAction.TERMINOLOGY_MAPPING_REJECTED, resource_type="TerminologyMappingDecision",
        resource_id=decision.id, organization_id=organization_id, user_id=acting_user_id,
        metadata={
            "source_system": decision.source_system, "domain": decision.domain, "context": decision.context,
            "source_term": decision.source_term, "reason": reason, "mapping_version": decision.mapping_version,
        },
    )
    _close_linked_hse_review(db, decision, organization_id=organization_id, outcome="INCORRECT", comment=reason)
    return decision


def _close_linked_hse_review(
    db: Session, decision: TerminologyMappingDecision, *, organization_id: uuid.UUID, outcome: str, comment: str | None
) -> None:
    """Closes out the `HseExpertReview` queue entry this candidate was
    created with, if any -- keeps the existing review queue's own
    `pending_only` view accurate (item 10) without conflating the two
    models' different vocabularies (see this module's own docstring)."""
    if decision.hse_expert_review_id is None:
        return
    hse_review_service.submit_review(
        db, organization_id=organization_id, review_id=decision.hse_expert_review_id, outcome=outcome,
        reviewer_comment=comment or f"Terminology mapping decision {decision.id} {decision.status.lower()}.",
        reviewer_user_id=decision.reviewer_user_id,
    )


# --- Item 8: versioning — changing an already-decided mapping without overwriting it ------------


def open_new_version(
    db: Session,
    *,
    organization_id: uuid.UUID,
    prior_decision_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> TerminologyMappingDecision:
    """Starts a fresh `REVIEW_CANDIDATE` at the next `mapping_version`
    for the same scope key as `prior_decision_id` -- the prior row (must
    already be terminal) is left completely untouched, only its
    `superseded_at` bookkeeping column is stamped. This is the *only*
    sanctioned way to change what an already-decided term maps to: the
    old decision's full history (who approved/rejected what, when, and
    why) is permanently preserved (item 8's own requirement)."""
    authorization_service.require(db, user_id=acting_user_id, permission=_APPROVAL_PERMISSION, organization_id=organization_id)

    prior = _require_owned_decision(db, organization_id=organization_id, decision_id=prior_decision_id)
    if not prior.is_terminal:
        raise TerminologyMappingDecisionStateError(
            f"Decision {prior_decision_id} is {prior.status}, not terminal -- mutate it directly "
            "(propose_mapping/approve_mapping/reject_mapping) instead of opening a new version."
        )

    max_version = db.execute(
        select(TerminologyMappingDecision.mapping_version).where(
            TerminologyMappingDecision.organization_id == organization_id,
            TerminologyMappingDecision.source_system == prior.source_system,
            TerminologyMappingDecision.domain == prior.domain,
            TerminologyMappingDecision.context == prior.context,
            TerminologyMappingDecision.source_term == prior.source_term,
        ).order_by(TerminologyMappingDecision.mapping_version.desc())
    ).scalars().first()
    next_version = (max_version or prior.mapping_version) + 1

    now = datetime.now(timezone.utc)
    prior.superseded_at = now

    new_decision = TerminologyMappingDecision(
        organization_id=organization_id,
        source_system=prior.source_system,
        domain=prior.domain,
        context=prior.context,
        source_term=prior.source_term,
        normalized_term=prior.normalized_term,
        mapping_version=next_version,
        status=TerminologyMappingDecisionStatus.REVIEW_CANDIDATE,
        occurrence_count=prior.occurrence_count,
        example_source_record_ids=list(prior.example_source_record_ids),
        provenance={"superseded_decision_id": str(prior.id), "superseded_version": prior.mapping_version},
    )
    db.add(new_decision)
    db.commit()
    db.refresh(new_decision)
    db.refresh(prior)

    audit_service.log(
        db, action=AuditAction.TERMINOLOGY_MAPPING_NEW_VERSION_OPENED, resource_type="TerminologyMappingDecision",
        resource_id=new_decision.id, organization_id=organization_id, user_id=acting_user_id,
        metadata={
            "source_system": prior.source_system, "domain": prior.domain, "context": prior.context,
            "source_term": prior.source_term, "prior_decision_id": str(prior.id),
            "prior_version": prior.mapping_version, "new_version": next_version,
        },
    )
    return new_decision


# --- Item 16: what's active right now, for the ingestion-time resolver --------------------------


def get_active_mapping(
    db: Session, *, organization_id: uuid.UUID, source_system: str, domain: str, context: str | None, source_term: str,
) -> TerminologyMappingDecision | None:
    """The highest-version `APPROVED` decision for this exact scope key,
    or `None` if none exists -- the one query the ingestion-time resolver
    needs. Never falls back to a different `source_system` or
    `organization_id` (item 7's own tenant/source isolation rule)."""
    normalized = _normalize_key(source_term)
    return db.execute(
        select(TerminologyMappingDecision).where(
            TerminologyMappingDecision.organization_id == organization_id,
            TerminologyMappingDecision.source_system == source_system,
            TerminologyMappingDecision.domain == domain,
            TerminologyMappingDecision.context == context,
            TerminologyMappingDecision.normalized_term == normalized,
            TerminologyMappingDecision.status == TerminologyMappingDecisionStatus.APPROVED,
        ).order_by(TerminologyMappingDecision.mapping_version.desc())
    ).scalars().first()


def build_active_mapping_index(
    db: Session, *, organization_id: uuid.UUID, source_system: str,
) -> dict[tuple[str, str | None, str], str]:
    """Every currently-active (highest-version `APPROVED`) mapping for
    `(organization_id, source_system)`, as a `{(domain, context,
    normalized_term): canonical_term}` dict -- fetched **once** per
    ingestion batch/evaluation run, not per record, so the calibration-
    aware adapter never queries the database inside its own
    `validate()`/`normalize()` (which the `DataSourceAdapter` Protocol
    itself does not pass a session into -- see
    `app/intelligence/terminology_calibration_adapter.py`'s own
    docstring)."""
    rows = db.execute(
        select(TerminologyMappingDecision).where(
            TerminologyMappingDecision.organization_id == organization_id,
            TerminologyMappingDecision.source_system == source_system,
            TerminologyMappingDecision.status == TerminologyMappingDecisionStatus.APPROVED,
        ).order_by(TerminologyMappingDecision.mapping_version.asc())
    ).scalars().all()

    index: dict[tuple[str, str | None, str], str] = {}
    for row in rows:
        # Ascending version order means a later, higher-version row for
        # the same key simply overwrites an earlier one in the dict --
        # the highest version always wins, with no extra sorting needed.
        if row.proposed_canonical_term:
            index[(row.domain, row.context, row.normalized_term)] = row.proposed_canonical_term
    return index


# --- Reporting / listing -------------------------------------------------------------------------


def list_decisions(
    db: Session,
    *,
    organization_id: uuid.UUID,
    status: str | None = None,
    domain: str | None = None,
    source_system: str | None = None,
) -> list[TerminologyMappingDecision]:
    query = select(TerminologyMappingDecision).where(TerminologyMappingDecision.organization_id == organization_id)
    if status is not None:
        query = query.where(TerminologyMappingDecision.status == status)
    if domain is not None:
        query = query.where(TerminologyMappingDecision.domain == domain)
    if source_system is not None:
        query = query.where(TerminologyMappingDecision.source_system == source_system)
    query = query.order_by(TerminologyMappingDecision.created_at)
    return list(db.execute(query).scalars().all())


__all__ = [
    "TerminologyMappingDecisionNotFoundError",
    "TerminologyMappingDecisionStateError",
    "approve_mapping",
    "build_active_mapping_index",
    "create_review_candidates",
    "get_active_mapping",
    "list_decisions",
    "open_new_version",
    "propose_mapping",
    "reject_mapping",
    "suggest_candidates",
]
