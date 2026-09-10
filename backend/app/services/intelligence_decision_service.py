"""IntelligenceDecision service — SIE Milestone 34: Human Decision &
Intervention Trace. The one write path for
`app/api/v1/intelligence_decisions.py`, mirroring
`app/services/safety_action_service.py`'s own "Transaction boundary"
shape exactly: one small transaction-boundary context manager, plus the
handful of functions the route calls inside it.

    POST /intelligence/decisions
        -> resolve_attention_item()   -- re-derive "what SIE said", server-side, from the
                                          exact historical as_of the human was viewing
        -> resolve_action_reference() -- (only if linked_action_id supplied) validate it
                                          belongs to this organization -- reused from
                                          app.services.risk_assessment_service, unchanged
        -> decision_mutation_transaction():
               IntelligenceDecision row + AuditLog entry, one commit

**`resolve_attention_item()` is the trust boundary this whole milestone
turns on.** The client supplies `attention_reference` plus the exact
`scope`/`site_id`/`as_of`/`window_days` it saw when it fetched
`GET /intelligence/attention` — never the category/priority/title/
evidence themselves. This function re-runs `compose_attention()` with
those same parameters (a deterministic, `as_of`-pinned recomputation —
see `app/intelligence/attention.py`'s own point-in-time discipline) and
looks up the item whose own `reference` matches. Every "what SIE said"
field written onto the `IntelligenceDecision` row comes from that
freshly recomputed item, never from client input — a client cannot
fabricate "SIE said CRITICAL" for a signal that was actually LOW, or
that never existed at all. A reference that no longer matches any item
(the underlying data changed, or the reference was simply wrong) is a
404, not a silent guess.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.attention import AttentionItem, compose_attention
from app.models.intelligence_decision import IntelligenceDecision
from app.models.intelligence_decision_enums import IntelligenceDecisionType


@contextmanager
def decision_mutation_transaction(db: Session) -> Iterator[None]:
    """The single transaction boundary for one `IntelligenceDecision`
    write -- identical shape to
    `safety_action_service.action_mutation_transaction()`/
    `risk_assessment_service.assessment_mutation_transaction()`. Commits
    once on success; rolls back once and re-raises, unchanged, on any
    exception."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def resolve_attention_item(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: str,
    site_id: uuid.UUID | None,
    as_of: datetime,
    window_days: int,
    attention_reference: str,
) -> AttentionItem:
    """Re-derive the exact attention item a human decision concerns,
    entirely server-side. See module docstring's "trust boundary"
    section. Raises `HTTPException` (404) when no item in the freshly
    recomputed list matches `attention_reference` -- this is an
    expected, first-class outcome (a stale reference, a typo, or a
    signal that genuinely no longer computes the same way as of that
    historical `as_of`), never a 500."""
    result = compose_attention(db, organization_id=organization_id, scope=scope, site_id=site_id, as_of=as_of, window_days=window_days)
    for item in result.items:
        if item.reference == attention_reference:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            "No attention item matches attention_reference for the given scope/site_id/as_of/window_days. "
            "Re-fetch GET /intelligence/attention (or .../sites/{site_id}/attention) with this exact as_of "
            "and window_days, and use one of its items' own reference values."
        ),
    )


def resolve_decision_reference(
    db: Session, *, organization_id: uuid.UUID, decision_id: uuid.UUID
) -> IntelligenceDecision:
    """SIE Milestone 37 — the identical "does this id belong to this
    organization" shape as
    `app.services.risk_assessment_service.resolve_action_reference()`,
    applied to `IntelligenceDecision`: the one place
    `app/services/intelligence_outcome_service.py::record_outcome()`
    validates a caller-supplied `decision_id` before writing an
    `IntelligenceOutcome` row that references it. A decision from a
    different organization (or a nonexistent id) is a 404, never a
    silent cross-tenant read."""
    decision = db.execute(
        select(IntelligenceDecision).where(
            IntelligenceDecision.id == decision_id, IntelligenceDecision.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="decision_id not found in this organization."
        )
    return decision


def record_decision(
    db: Session,
    *,
    organization_id: uuid.UUID,
    item: AttentionItem,
    decision: IntelligenceDecisionType,
    rationale: str,
    linked_action_id: uuid.UUID | None,
    decided_by_user_id: uuid.UUID | None,
    decided_by_api_client_id: uuid.UUID | None,
    request_id: str | None,
) -> IntelligenceDecision:
    """Builds and `db.add()`s (never commits -- the caller's own
    `decision_mutation_transaction()` block does that) one
    `IntelligenceDecision` row. Every `attention_*`/`intelligence_*`/
    `calculation_version`/`evidence_*` field is copied verbatim from
    `item` (already server-derived by `resolve_attention_item()` above)
    -- this function never re-derives or second-guesses them."""
    record = IntelligenceDecision(
        organization_id=organization_id,
        site_id=item.site_id,
        scope=item.scope,
        attention_reference=item.reference,
        attention_category=item.category,
        attention_priority=item.priority,
        attention_title=item.title,
        attention_explanation=item.explanation,
        intelligence_as_of=item.as_of,
        intelligence_window_days=item.window_days,
        calculation_version=item.evidence.calculation_version,
        evidence_source=item.evidence.source,
        evidence_entity_ids=[str(i) for i in item.evidence.entity_ids] or None,
        evidence_event_ids=[str(i) for i in item.evidence.event_ids] or None,
        decision=decision,
        rationale=rationale,
        linked_action_id=linked_action_id,
        decided_by_user_id=decided_by_user_id,
        decided_by_api_client_id=decided_by_api_client_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()  # populates record.id/decided_at/created_at/updated_at for the response, without committing
    return record


__all__ = [
    "decision_mutation_transaction",
    "resolve_attention_item",
    "resolve_decision_reference",
    "record_decision",
]
