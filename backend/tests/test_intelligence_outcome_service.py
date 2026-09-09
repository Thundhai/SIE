"""SIE Milestone 37: Field Outcome Foundation — service-level tests for
`app/services/intelligence_outcome_service.py`. Mirrors
`tests/test_intelligence_decision_service.py`'s own established shape:
direct calls against `db_session`, no HTTP layer. HTTP-layer coverage
(authorization, tenant isolation over the wire, idempotency, response
contract, point-in-time filtering) lives in
`tests/test_intelligence_outcomes_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.intelligence.attention import compose_attention
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.services.intelligence_decision_service import decision_mutation_transaction, record_decision
from app.services.intelligence_outcome_service import (
    outcome_mutation_transaction,
    record_outcome,
    reject_future_outcome_at,
    resolve_decision_reference,
)
from tests.intelligence_test_helpers import make_org, make_safety_event, seed_risk_area_ontology_concepts

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite does not round-trip `tzinfo` through a commit/expire cycle
    -- identical, already-established pattern used throughout this
    codebase (see `test_intelligence_decision_service.py::_as_utc()`)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _seed_events(db_session, org_id, *, count=8):
    for i in range(count):
        db_session.add(
            make_safety_event(
                organization_id=org_id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session):
    return seed_risk_area_ontology_concepts(db_session)


def _make_decision(db_session, org_id, **overrides):
    result = compose_attention(db_session, organization_id=org_id, scope="organization", as_of=AS_OF, window_days=30)
    assert result.items, "expected at least one attention item for this fixture"
    item = result.items[0]
    with decision_mutation_transaction(db_session):
        kwargs = dict(
            organization_id=org_id,
            item=item,
            decision=IntelligenceDecisionType.ACT,
            rationale="Field conditions require immediate intervention.",
            linked_action_id=None,
            decided_by_user_id=uuid.uuid4(),
            decided_by_api_client_id=None,
            request_id=None,
        )
        kwargs.update(overrides)
        decision = record_decision(db_session, **kwargs)
    return decision


# --- resolve_decision_reference: tenant boundary ------------------------------------------------


def test_resolve_decision_reference_finds_the_matching_decision(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)

    resolved = resolve_decision_reference(db_session, organization_id=org.id, decision_id=decision.id)
    assert resolved.id == decision.id


def test_resolve_decision_reference_404s_for_a_nonexistent_id(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        resolve_decision_reference(db_session, organization_id=org.id, decision_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_resolve_decision_reference_rejects_a_cross_tenant_decision(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)
    decision_b = _make_decision(db_session, org_b.id)

    with pytest.raises(HTTPException) as exc_info:
        resolve_decision_reference(db_session, organization_id=org_a.id, decision_id=decision_b.id)
    assert exc_info.value.status_code == 404


# --- reject_future_outcome_at ---------------------------------------------------------------


def test_reject_future_outcome_at_accepts_the_past():
    reject_future_outcome_at(datetime.now(timezone.utc) - timedelta(days=1))  # must not raise


def test_reject_future_outcome_at_accepts_now():
    reject_future_outcome_at(datetime.now(timezone.utc))  # must not raise


def test_reject_future_outcome_at_rejects_the_future():
    with pytest.raises(HTTPException) as exc_info:
        reject_future_outcome_at(datetime.now(timezone.utc) + timedelta(days=1))
    assert exc_info.value.status_code == 422


def test_reject_future_outcome_at_handles_naive_datetimes():
    """A naive datetime is treated as UTC (mirrors `_as_utc()`'s own
    convention throughout this codebase) rather than raising or silently
    comparing incompatible datetimes."""
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    with pytest.raises(HTTPException):
        reject_future_outcome_at(naive_now + timedelta(days=1))
    reject_future_outcome_at(naive_now - timedelta(days=1))  # must not raise


# --- record_outcome: the one write path ------------------------------------------------------


def test_record_outcome_persists_every_field(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with outcome_mutation_transaction(db_session):
        record = record_outcome(
            db_session,
            organization_id=org.id,
            decision_id=decision.id,
            site_id=None,
            linked_action_id=None,
            classification=IntelligenceOutcomeClassification.EFFECTIVE,
            summary="Follow-up inspection confirmed the hazard was corrected.",
            evidence_event_ids=[event_id],
            outcome_at=AS_OF + timedelta(days=3),
            recorded_by_user_id=user_id,
            recorded_by_api_client_id=None,
            request_id="req-outcome-1",
        )

    assert record.decision_id == decision.id
    assert record.classification == IntelligenceOutcomeClassification.EFFECTIVE
    assert record.summary == "Follow-up inspection confirmed the hazard was corrected."
    assert record.evidence_event_ids == [str(event_id)]
    assert _as_utc(record.outcome_at) == AS_OF + timedelta(days=3)
    assert record.recorded_by_user_id == user_id
    assert record.recorded_by_api_client_id is None
    assert record.request_id == "req-outcome-1"
    assert record.id is not None
    assert record.created_at is not None


def test_record_outcome_allows_no_linked_action(db_session):
    """§5 -- Decision -> Outcome with no SafetyAction in between is
    legitimate and never forced."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)

    with outcome_mutation_transaction(db_session):
        record = record_outcome(
            db_session,
            organization_id=org.id,
            decision_id=decision.id,
            site_id=None,
            linked_action_id=None,
            classification=IntelligenceOutcomeClassification.PARTIALLY_EFFECTIVE,
            summary="Verbal correction given; formal action not raised.",
            evidence_event_ids=None,
            outcome_at=AS_OF,
            recorded_by_user_id=uuid.uuid4(),
            recorded_by_api_client_id=None,
            request_id=None,
        )
    assert record.linked_action_id is None


def test_every_outcome_classification_is_recordable(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)

    for classification in IntelligenceOutcomeClassification:
        with outcome_mutation_transaction(db_session):
            record = record_outcome(
                db_session,
                organization_id=org.id,
                decision_id=decision.id,
                site_id=None,
                linked_action_id=None,
                classification=classification,
                summary=f"Testing {classification.value}.",
                evidence_event_ids=None,
                outcome_at=AS_OF,
                recorded_by_user_id=uuid.uuid4(),
                recorded_by_api_client_id=None,
                request_id=None,
            )
        assert record.classification == classification


def test_no_outcome_recorded_is_never_produced_automatically(db_session):
    """§3's own explicit rule: `NO_OUTCOME_RECORDED` is only ever a
    human's own explicit choice via this one write path -- there is no
    mechanism anywhere in this module that produces it (or any other
    classification) without an explicit `record_outcome()` call."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)

    from sqlalchemy import func, select

    from app.models.intelligence_outcome import IntelligenceOutcome

    before = db_session.execute(select(func.count()).select_from(IntelligenceOutcome)).scalar_one()
    # Merely resolving the decision reference -- no outcome call -- must
    # never create a row.
    resolve_decision_reference(db_session, organization_id=org.id, decision_id=decision.id)
    after = db_session.execute(select(func.count()).select_from(IntelligenceOutcome)).scalar_one()
    assert before == after == 0


# --- Temporal integrity: outcome_at vs. created_at --------------------------------------------


def test_outcome_at_is_distinct_from_created_at(db_session):
    """§7 -- an outcome is very often reported well after it actually
    happened; the two timestamps must never be conflated."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    historical_outcome_at = AS_OF - timedelta(days=30)

    with outcome_mutation_transaction(db_session):
        record = record_outcome(
            db_session,
            organization_id=org.id,
            decision_id=decision.id,
            site_id=None,
            linked_action_id=None,
            classification=IntelligenceOutcomeClassification.EFFECTIVE,
            summary="Backdated report -- outcome happened long before this row was written.",
            evidence_event_ids=None,
            outcome_at=historical_outcome_at,
            recorded_by_user_id=uuid.uuid4(),
            recorded_by_api_client_id=None,
            request_id=None,
        )
    assert _as_utc(record.outcome_at) == historical_outcome_at
    assert _as_utc(record.outcome_at) != _as_utc(record.created_at)


# --- Immutability: no update mechanism exists in this module -----------------------------------


def test_outcome_service_exposes_no_update_function():
    """§6 -- append-only by construction: this module deliberately
    exposes no update/correction function at all. A correction is a
    second `record_outcome()` call referencing the same `decision_id`."""
    import app.services.intelligence_outcome_service as module

    assert not any(name.startswith("update") for name in module.__all__)
    assert not any(name.startswith("correct") for name in module.__all__)
