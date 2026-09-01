"""Deterministic risk signals — milestone items 22, 53. Runs against
`db_session` (SQLite) — plain datetime/aggregation, no pgvector needed.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enums import RiskSignalType
from app.intelligence.signals import risk_signal_service
from app.models.organization import Organization
from tests.intelligence_test_helpers import make_safety_event

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Signals Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _seed(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, ingestion_time=overrides.get("event_time", AS_OF), **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def _seed_baseline(db_session, org_id, *, event_type, count, days_ago, **overrides):
    """Seed `count` events of the same type in the baseline period
    (well before the current 30-day analysis window)."""
    for i in range(count):
        _seed(
            db_session, org_id,
            event_type=event_type,
            event_time=AS_OF - timedelta(days=days_ago, hours=i),
            source_record_id=f"baseline-{event_type}-{days_ago}-{i}",
            **overrides,
        )


def test_high_potential_event_cluster_fires_on_a_genuine_surge(db_session):
    org_id = _make_org(db_session)
    # Sparse baseline: ~1 high-potential event per month for 2 prior months.
    _seed_baseline(db_session, org_id, event_type="INCIDENT", count=1, days_ago=45, potential_severity="HIGH")
    _seed_baseline(db_session, org_id, event_type="INCIDENT", count=1, days_ago=75, potential_severity="HIGH")
    # Current window: a real cluster.
    for i in range(5):
        _seed(
            db_session, org_id, event_type="INCIDENT", potential_severity="HIGH",
            event_time=AS_OF - timedelta(days=i), source_record_id=f"current-{i}",
        )

    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    types = {s.signal_type for s in signals}
    assert RiskSignalType.HIGH_POTENTIAL_EVENT_CLUSTER.value in types


def test_overdue_action_surge_fires_when_overdue_actions_spike(db_session):
    org_id = _make_org(db_session)
    _seed_baseline(db_session, org_id, event_type="CORRECTIVE_ACTION", count=1, days_ago=45, status="OVERDUE")
    for i in range(6):
        _seed(
            db_session, org_id, event_type="CORRECTIVE_ACTION", status="OVERDUE",
            event_time=AS_OF - timedelta(days=i), source_record_id=f"overdue-{i}",
        )
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert any(s.signal_type == RiskSignalType.OVERDUE_ACTION_SURGE.value for s in signals)


def test_equipment_failure_cluster_fires_on_a_surge(db_session):
    org_id = _make_org(db_session)
    _seed_baseline(db_session, org_id, event_type="EQUIPMENT", count=1, days_ago=45, event_subtype="failure")
    for i in range(5):
        _seed(
            db_session, org_id, event_type="EQUIPMENT", event_subtype="failure",
            event_time=AS_OF - timedelta(days=i), source_record_id=f"failure-{i}",
        )
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert any(s.signal_type == RiskSignalType.EQUIPMENT_FAILURE_CLUSTER.value for s in signals)


def test_unsafe_observation_surge_fires_on_a_surge(db_session):
    org_id = _make_org(db_session)
    _seed_baseline(db_session, org_id, event_type="OBSERVATION", count=1, days_ago=45, event_subtype="unsafe_act")
    for i in range(6):
        _seed(
            db_session, org_id, event_type="OBSERVATION", event_subtype="unsafe_act",
            event_time=AS_OF - timedelta(days=i), source_record_id=f"unsafe-{i}",
        )
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert any(s.signal_type == RiskSignalType.UNSAFE_OBSERVATION_SURGE.value for s in signals)


def test_training_compliance_drop_fires_below_the_threshold(db_session):
    org_id = _make_org(db_session)
    for i in range(8):
        status = "COMPLETED" if i < 2 else "OVERDUE"  # 25% completion, well under the 80% default threshold
        _seed(
            db_session, org_id, event_type="TRAINING", status=status,
            event_time=AS_OF - timedelta(days=i), source_record_id=f"training-{i}",
        )
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert any(s.signal_type == RiskSignalType.TRAINING_COMPLIANCE_DROP.value for s in signals)


def test_high_training_completion_never_fires_the_compliance_drop_signal(db_session):
    org_id = _make_org(db_session)
    for i in range(8):
        status = "COMPLETED" if i < 7 else "OVERDUE"
        _seed(
            db_session, org_id, event_type="TRAINING", status=status,
            event_time=AS_OF - timedelta(days=i), source_record_id=f"training-good-{i}",
        )
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert not any(s.signal_type == RiskSignalType.TRAINING_COMPLIANCE_DROP.value for s in signals)


# --- Milestone item 53: insufficient data never produces a strong signal -----------


def test_a_tiny_amount_of_data_never_produces_a_risk_signal(db_session):
    """A site with only one or two events, even if every single one is
    'high potential', must not fire a signal -- see
    app/intelligence/signals.py's own docstring on the data-quality gate."""
    org_id = _make_org(db_session)
    _seed(db_session, org_id, event_type="INCIDENT", potential_severity="CRITICAL", event_time=AS_OF, source_record_id="only-1")

    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert signals == []


def test_signals_carry_full_provenance(db_session):
    """Milestone item 22/28: signal -> supporting_features -> supporting_event_ids."""
    org_id = _make_org(db_session)
    _seed_baseline(db_session, org_id, event_type="INCIDENT", count=1, days_ago=45, potential_severity="HIGH")
    events = [
        _seed(
            db_session, org_id, event_type="INCIDENT", potential_severity="HIGH",
            event_time=AS_OF - timedelta(days=i), source_record_id=f"prov-{i}",
        )
        for i in range(5)
    ]
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    cluster = next(s for s in signals if s.signal_type == RiskSignalType.HIGH_POTENTIAL_EVENT_CLUSTER.value)
    assert cluster.supporting_features
    assert cluster.supporting_event_ids
    assert set(cluster.supporting_event_ids).issubset({e.id for e in events})
    assert cluster.calculation_version == "risk-signal-v1"
    assert cluster.observed_period_start < cluster.observed_period_end


def test_no_surge_no_signal_for_a_quiet_organization(db_session):
    org_id = _make_org(db_session)
    _seed_baseline(db_session, org_id, event_type="INCIDENT", count=2, days_ago=45)
    _seed(db_session, org_id, event_type="INCIDENT", event_time=AS_OF, source_record_id="quiet")
    signals = risk_signal_service.detect_all(db_session, organization_id=org_id, as_of=AS_OF)
    assert not any(s.signal_type == RiskSignalType.HIGH_POTENTIAL_EVENT_CLUSTER.value for s in signals)
