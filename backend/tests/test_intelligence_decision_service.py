"""SIE Milestone 34: Human Decision & Intervention Trace — service-level
tests for `app/services/intelligence_decision_service.py`. Mirrors
`tests/test_attention_service.py`'s own established shape: direct calls
against `db_session`, no HTTP layer. HTTP-layer coverage (authorization,
tenant isolation over the wire, idempotency, response contract) lives in
`tests/test_intelligence_decisions_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.intelligence.attention import compose_attention
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.services.intelligence_decision_service import (
    decision_mutation_transaction,
    record_decision,
    resolve_attention_item,
)
from tests.intelligence_test_helpers import make_org, make_safety_event, seed_risk_area_ontology_concepts

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite does not round-trip `tzinfo` through a commit/expire cycle
    -- mirrors the identical, already-established pattern in
    `app/intelligence/enterprise_intelligence_service.py::_as_utc()`."""
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


def _first_attention_item(db_session, org_id, *, as_of=AS_OF, window_days=30):
    result = compose_attention(db_session, organization_id=org_id, scope="organization", as_of=as_of, window_days=window_days)
    assert result.items, "expected at least one attention item for this fixture"
    return result.items[0]


# --- resolve_attention_item: the trust boundary ------------------------------------------------


def test_resolve_attention_item_finds_the_matching_item(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    item = _first_attention_item(db_session, org.id)

    resolved = resolve_attention_item(
        db_session, organization_id=org.id, scope="organization", site_id=None, as_of=AS_OF, window_days=30,
        attention_reference=item.reference,
    )
    assert resolved.reference == item.reference
    assert resolved.category == item.category
    assert resolved.priority == item.priority


def test_resolve_attention_item_404s_for_an_unknown_reference(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    with pytest.raises(HTTPException) as exc_info:
        resolve_attention_item(
            db_session, organization_id=org.id, scope="organization", site_id=None, as_of=AS_OF, window_days=30,
            attention_reference="DETERIORATING_TREND:organization:org:not-a-real-reference",
        )
    assert exc_info.value.status_code == 404


def test_resolve_attention_item_never_leaks_across_organizations(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)  # only org B has data
    item_b = _first_attention_item(db_session, org_b.id)

    # The same reference string, looked up under org A, must not resolve
    # -- org A's own compose_attention() computes over org A's own
    # (empty) data and will never produce a matching item.
    with pytest.raises(HTTPException) as exc_info:
        resolve_attention_item(
            db_session, organization_id=org_a.id, scope="organization", site_id=None, as_of=AS_OF, window_days=30,
            attention_reference=item_b.reference,
        )
    assert exc_info.value.status_code == 404


# --- record_decision: what SIE said vs. what the human decided --------------------------------


def test_record_decision_denormalizes_the_attention_item_verbatim(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    item = _first_attention_item(db_session, org.id)
    user_id = uuid.uuid4()

    with decision_mutation_transaction(db_session):
        record = record_decision(
            db_session, organization_id=org.id, item=item, decision=IntelligenceDecisionType.DO_NOT_ACT,
            rationale="Existing control verified effective.", linked_action_id=None,
            decided_by_user_id=user_id, decided_by_api_client_id=None, request_id="req-1",
        )

    assert record.attention_category == item.category
    assert record.attention_priority == item.priority  # SIE's own priority, untouched
    assert record.decision == IntelligenceDecisionType.DO_NOT_ACT  # the human's own, separate fact
    assert record.attention_title == item.title
    assert _as_utc(record.intelligence_as_of) == item.as_of
    assert record.intelligence_window_days == item.window_days
    assert record.calculation_version == item.evidence.calculation_version
    assert record.decided_by_user_id == user_id
    assert record.decided_by_api_client_id is None
    assert record.rationale == "Existing control verified effective."
    assert record.request_id == "req-1"


def test_record_decision_preserves_high_priority_alongside_do_not_act(db_session):
    """§6's own worked example: SIE priority = HIGH, human decision =
    DO_NOT_ACT -- both facts survive on the same row, neither
    recalculated nor overwritten."""
    org = make_org(db_session)
    # Deteriorating trend fixture -- reliably produces a HIGH item.
    for i in range(2):
        db_session.add(
            make_safety_event(
                organization_id=org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=45 + i),
                ingestion_time=AS_OF - timedelta(days=45 + i), source_record_id=str(uuid.uuid4()),
            )
        )
    for i in range(10):
        db_session.add(
            make_safety_event(
                organization_id=org.id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i), source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)
    trend_item = next(i for i in result.items if i.category == "DETERIORATING_TREND")
    assert trend_item.priority == "HIGH"

    with decision_mutation_transaction(db_session):
        record = record_decision(
            db_session, organization_id=org.id, item=trend_item, decision=IntelligenceDecisionType.DO_NOT_ACT,
            rationale="Existing control verified effective.", linked_action_id=None,
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    assert record.attention_priority == "HIGH"
    assert record.decision == IntelligenceDecisionType.DO_NOT_ACT


def test_record_decision_never_creates_a_safety_action(db_session):
    """§5/§10: decision=ACT must never automatically create an action."""
    from sqlalchemy import func, select

    from app.models.safety_action import SafetyAction

    org = make_org(db_session)
    _seed_events(db_session, org.id)
    item = _first_attention_item(db_session, org.id)
    before = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()

    with decision_mutation_transaction(db_session):
        record_decision(
            db_session, organization_id=org.id, item=item, decision=IntelligenceDecisionType.ACT,
            rationale="Field conditions require immediate intervention.", linked_action_id=None,
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    after = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    assert before == after == 0


def test_every_decision_type_is_recordable(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    item = _first_attention_item(db_session, org.id)
    for decision_type in IntelligenceDecisionType:
        with decision_mutation_transaction(db_session):
            record = record_decision(
                db_session, organization_id=org.id, item=item, decision=decision_type,
                rationale=f"Testing {decision_type.value}.", linked_action_id=None,
                decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
            )
        assert record.decision == decision_type


# --- Temporal integrity ---------------------------------------------------------------------


def test_decision_retains_the_original_intelligence_as_of_not_now(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    historical_as_of = AS_OF - timedelta(days=3)
    item = _first_attention_item(db_session, org.id, as_of=historical_as_of)

    with decision_mutation_transaction(db_session):
        record = record_decision(
            db_session, organization_id=org.id, item=item, decision=IntelligenceDecisionType.DEFER,
            rationale="Will revisit.", linked_action_id=None,
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    assert _as_utc(record.intelligence_as_of) == historical_as_of
    assert _as_utc(record.intelligence_as_of) != _as_utc(record.decided_at)
