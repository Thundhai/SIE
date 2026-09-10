"""SIE Milestone 33: Intelligence Attention & Delivery — service-level
tests for `app/intelligence/attention.py`. Mirrors
`tests/test_context_composition_service.py`'s own established shape:
direct calls against `db_session`, no HTTP layer. HTTP-layer coverage
(authorization, tenant isolation over the wire, response contract)
lives in `tests/test_attention_api.py`. Reuses the M32 test module's own
fixture builders (`_make_assessment`/`_make_finding`/`_make_prediction`/
`_risk_area_concept_id`) rather than duplicating them -- an established
pattern in this test suite (e.g. `test_enterprise_anomaly_api.py`
importing from `test_enterprise_intelligence_api.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.intelligence.attention import (
    AttentionCategory,
    _PRIORITY_RANK,
    compose_attention,
)
from app.models.risk_assessment import RiskAssessmentControl
from app.models.risk_assessment_enums import ControlEffectiveness, ControlStatus, ControlType, RiskAssessmentStatus
from app.models.safety_action import SafetyAction
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site, seed_risk_area_ontology_concepts
from tests.test_context_composition_service import (
    _make_assessment,
    _make_finding,
    _make_prediction,
    _risk_area_concept_id,
)

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _seed_events(db_session, org_id, *, site_id=None, count=3, event_time_step_days=1):
    for i in range(count):
        db_session.add(
            make_safety_event(
                organization_id=org_id,
                site_id=site_id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=i * event_time_step_days),
                ingestion_time=AS_OF - timedelta(days=i * event_time_step_days),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session):
    return seed_risk_area_ontology_concepts(db_session)


# --- Empty result ------------------------------------------------------------------------------


def test_empty_organization_produces_no_items_but_full_category_statuses(db_session):
    org = make_org(db_session)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.items == []
    assert len(result.category_statuses) == 8
    assert all(s.status in ("EVALUATED", "NOT_EVALUATED") for s in result.category_statuses)
    categories_seen = {s.category for s in result.category_statuses}
    assert categories_seen == {c.value for c in AttentionCategory}


# --- Typed response contract -------------------------------------------------------------------


def test_result_fields_are_typed_and_complete(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.items, "expected at least one attention item for this fixture"
    for item in result.items:
        assert item.category in {c.value for c in AttentionCategory}
        assert item.priority in _PRIORITY_RANK
        assert item.title
        assert item.explanation
        assert item.scope == "organization"
        assert item.as_of == AS_OF
        assert item.window_days == result.window_days
        assert item.evidence.source
        # evidence is always a real reference, never a copy of content
        assert isinstance(item.evidence.entity_ids, list)
        assert isinstance(item.evidence.event_ids, list)


# --- Deterministic prioritization ---------------------------------------------------------------


def test_items_are_sorted_by_priority_band_descending(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    ranks = [_PRIORITY_RANK[item.priority] for item in result.items]
    assert ranks == sorted(ranks, reverse=True)


def test_prioritization_is_deterministic_across_repeated_calls(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)
    result_a = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    result_b = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert [(i.category, i.priority, i.title) for i in result_a.items] == [
        (i.category, i.priority, i.title) for i in result_b.items
    ]


def test_low_priority_signals_never_become_attention_items(db_session):
    """A single event produces STABLE trend / no anomaly / no recurrence
    / LOW risk -- none of which are attention-worthy (mirrors every
    existing lens's own "LOW/STABLE is the baseline, not a finding"
    convention)."""
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=1)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.items == []


# --- Deteriorating trend / anomaly / recurring pattern --------------------------------------


def test_deteriorating_trend_produces_high_priority_item(db_session):
    org = make_org(db_session)
    # Previous period: few events. Current period: many more -- a
    # worsening period-over-period trend (mirrors
    # test_enterprise_intelligence_service.py's own trend fixtures).
    for i in range(2):
        db_session.add(
            make_safety_event(
                organization_id=org.id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=45 + i),
                ingestion_time=AS_OF - timedelta(days=45 + i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    for i in range(10):
        db_session.add(
            make_safety_event(
                organization_id=org.id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF, window_days=30)
    trend_items = [i for i in result.items if i.category == AttentionCategory.DETERIORATING_TREND.value]
    assert len(trend_items) == 1
    assert trend_items[0].priority == "HIGH"
    assert "incident_count" in trend_items[0].explanation


def test_recurring_pattern_at_a_site_is_surfaced_with_site_label(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id, "Recurrence Site")
    _seed_events(db_session, org.id, site_id=site.id, count=6)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    pattern_items = [i for i in result.items if i.category == AttentionCategory.RECURRING_PATTERN.value]
    assert len(pattern_items) == 1
    assert pattern_items[0].site_label == "Recurrence Site"
    assert pattern_items[0].site_id == site.id
    assert pattern_items[0].evidence.event_ids  # real supporting event ids, not invented


# --- Predictive signal + staleness ------------------------------------------------------------


def test_predictive_risk_item_when_elevated_and_contemporaneous(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF - timedelta(days=1))
    result = compose_attention(db_session, organization_id=org.id, scope="site", site_id=site.id, as_of=AS_OF)
    predictive_items = [i for i in result.items if i.category == AttentionCategory.PREDICTIVE_RISK.value]
    # risk_score=0.42/risk_category="MODERATE" per _make_prediction's own default
    assert len(predictive_items) == 1
    assert predictive_items[0].priority == "MODERATE"
    assert predictive_items[0].evidence.source == "prediction"


def test_predictive_risk_excluded_when_generated_after_as_of(db_session):
    """The staleness rule, inherited unchanged from M32: a prediction
    generated after the requested as_of must never surface as an
    attention item, and the exclusion must be explained, not silent."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF + timedelta(days=1))
    result = compose_attention(db_session, organization_id=org.id, scope="site", site_id=site.id, as_of=AS_OF)
    predictive_items = [i for i in result.items if i.category == AttentionCategory.PREDICTIVE_RISK.value]
    assert predictive_items == []
    status = next(s for s in result.category_statuses if s.category == AttentionCategory.PREDICTIVE_RISK.value)
    assert status.status == "NOT_EVALUATED"
    assert "after the requested as_of" in status.reason


def test_predictive_risk_not_evaluated_for_organization_scope(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF - timedelta(days=1))
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    status = next(s for s in result.category_statuses if s.category == AttentionCategory.PREDICTIVE_RISK.value)
    assert status.status == "EVALUATED"
    assert status.item_count == 0
    assert "site-scoped" in status.reason


# --- Unresolved findings / evidence gaps -------------------------------------------------------


def test_unresolved_finding_item_for_high_risk_open_finding(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    assessment = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    finding = _make_finding(db_session, org.id, assessment.id, concept_id)
    db_session.execute(
        finding.__table__.update().where(finding.__table__.c.id == finding.id).values(
            inherent_risk_classification="HIGH"
        )
    )
    db_session.commit()

    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    finding_items = [i for i in result.items if i.category == AttentionCategory.UNRESOLVED_FINDING.value]
    assert len(finding_items) == 1
    assert finding_items[0].priority == "HIGH"
    assert finding_items[0].evidence.entity_ids == [finding.id]


def test_evidence_gap_item_when_high_risk_finding_has_no_assessed_controls(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    assessment = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    finding = _make_finding(db_session, org.id, assessment.id, concept_id)
    db_session.execute(
        finding.__table__.update().where(finding.__table__.c.id == finding.id).values(
            inherent_risk_classification="CRITICAL"
        )
    )
    db_session.add(
        RiskAssessmentControl(
            organization_id=org.id,
            finding_id=finding.id,
            description="A proposed but unassessed control",
            control_type=ControlType.ADMINISTRATIVE,
            status=ControlStatus.PROPOSED,
            effectiveness=ControlEffectiveness.NOT_ASSESSED,
        )
    )
    db_session.commit()

    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    gap_items = [i for i in result.items if i.category == AttentionCategory.EVIDENCE_GAP.value]
    assert len(gap_items) == 1
    assert gap_items[0].priority == "MODERATE"


def test_no_evidence_gap_when_a_control_has_been_assessed(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    assessment = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    finding = _make_finding(db_session, org.id, assessment.id, concept_id)
    db_session.execute(
        finding.__table__.update().where(finding.__table__.c.id == finding.id).values(
            inherent_risk_classification="CRITICAL"
        )
    )
    db_session.add(
        RiskAssessmentControl(
            organization_id=org.id,
            finding_id=finding.id,
            description="An assessed, effective control",
            control_type=ControlType.ENGINEERING,
            status=ControlStatus.IN_PLACE,
            effectiveness=ControlEffectiveness.EFFECTIVE,
        )
    )
    db_session.commit()

    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    gap_items = [i for i in result.items if i.category == AttentionCategory.EVIDENCE_GAP.value]
    assert gap_items == []


# --- Overdue actions ------------------------------------------------------------------------


def test_overdue_actions_item(db_session):
    org = make_org(db_session)
    db_session.add(
        SafetyAction(
            organization_id=org.id,
            title="An overdue action",
            action_type="CORRECTIVE",
            priority="HIGH",
            status="OPEN",
            attributes={},
            created_at=AS_OF - timedelta(days=30),
            due_date=AS_OF - timedelta(days=5),
        )
    )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    overdue_items = [i for i in result.items if i.category == AttentionCategory.OVERDUE_ACTIONS.value]
    assert len(overdue_items) == 1
    assert overdue_items[0].priority == "HIGH"  # high_priority_action_count > 0
    assert "1 safety action" in overdue_items[0].explanation


def test_no_overdue_actions_item_when_none_overdue(db_session):
    org = make_org(db_session)
    db_session.add(
        SafetyAction(
            organization_id=org.id,
            title="Not yet due",
            action_type="CORRECTIVE",
            priority="LOW",
            status="OPEN",
            attributes={},
            created_at=AS_OF - timedelta(days=1),
            due_date=AS_OF + timedelta(days=30),
        )
    )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert [i for i in result.items if i.category == AttentionCategory.OVERDUE_ACTIONS.value] == []


# --- Temporal correctness (as_of) ---------------------------------------------------------------


def test_events_after_as_of_never_influence_attention(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)
    # An event far in the "future" relative to AS_OF must not affect a
    # historical attention read -- inherited from M32/M22's own
    # events_as_of() point-in-time filter (this module adds no event
    # query of its own); this test guards against a regression where
    # attention.py bypassed that filter (e.g. by reusing `as_of=None`,
    # which defaults to "now").
    future_event = make_safety_event(
        organization_id=org.id,
        event_type="INCIDENT",
        event_time=AS_OF + timedelta(days=10),
        ingestion_time=AS_OF + timedelta(days=10),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(future_event)
    db_session.commit()

    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    for item in result.items:
        assert future_event.id not in item.evidence.event_ids


def test_actions_after_as_of_never_influence_overdue_count(db_session):
    org = make_org(db_session)
    db_session.add(
        SafetyAction(
            organization_id=org.id,
            title="Created after as_of",
            action_type="CORRECTIVE",
            priority="HIGH",
            status="OPEN",
            attributes={},
            created_at=AS_OF + timedelta(days=1),
            due_date=AS_OF - timedelta(days=1),
        )
    )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert [i for i in result.items if i.category == AttentionCategory.OVERDUE_ACTIONS.value] == []


def test_findings_after_as_of_never_influence_unresolved_finding_items(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    assessment = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    finding = _make_finding(db_session, org.id, assessment.id, concept_id, created_at=AS_OF + timedelta(days=1))
    db_session.execute(
        finding.__table__.update().where(finding.__table__.c.id == finding.id).values(
            inherent_risk_classification="CRITICAL"
        )
    )
    db_session.commit()
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert [i for i in result.items if i.category == AttentionCategory.UNRESOLVED_FINDING.value] == []


# --- Failure isolation ---------------------------------------------------------------------------


def test_evidence_gap_failure_does_not_blank_other_categories(db_session, monkeypatch):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated evidence-gap query failure")

    monkeypatch.setattr("app.intelligence.attention._evidence_gap_items", _boom)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)

    gap_status = next(s for s in result.category_statuses if s.category == AttentionCategory.EVIDENCE_GAP.value)
    assert gap_status.status == "UNAVAILABLE"
    assert gap_status.reason == "simulated evidence-gap query failure"
    # Other categories (already computed from the same context) are untouched.
    trend_status = next(s for s in result.category_statuses if s.category == AttentionCategory.DETERIORATING_TREND.value)
    assert trend_status.status == "EVALUATED"
    assert any(i.category == AttentionCategory.DETERIORATING_TREND.value for i in result.items)


def test_anomaly_failure_does_not_blank_trend_or_risk_items(db_session, monkeypatch):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated anomaly failure")

    monkeypatch.setattr("app.intelligence.attention._significant_anomaly_items", _boom)
    result = compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)

    anomaly_status = next(s for s in result.category_statuses if s.category == AttentionCategory.SIGNIFICANT_ANOMALY.value)
    assert anomaly_status.status == "UNAVAILABLE"
    assert any(i.category == AttentionCategory.ELEVATED_RISK.value for i in result.items)


# --- Tenant isolation ---------------------------------------------------------------------------


def test_attention_never_leaks_another_organizations_findings_or_actions(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    concept_id = _risk_area_concept_id(db_session)
    assessment_b = _make_assessment(db_session, org_b.id, status=RiskAssessmentStatus.APPROVED)
    finding_b = _make_finding(db_session, org_b.id, assessment_b.id, concept_id)
    db_session.execute(
        finding_b.__table__.update().where(finding_b.__table__.c.id == finding_b.id).values(
            inherent_risk_classification="CRITICAL"
        )
    )
    db_session.add(
        SafetyAction(
            organization_id=org_b.id, title="Org B's action", action_type="CORRECTIVE", priority="HIGH",
            status="OPEN", attributes={}, created_at=AS_OF - timedelta(days=10), due_date=AS_OF - timedelta(days=1),
        )
    )
    db_session.commit()

    result = compose_attention(db_session, organization_id=org_a.id, scope="organization", as_of=AS_OF)
    assert result.items == []
    assert result.organization_id == org_a.id


# --- No mutation ----------------------------------------------------------------------------------


def test_compose_attention_performs_no_writes(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=8)
    before = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    compose_attention(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    db_session.expire_all()
    after = db_session.execute(select(func.count()).select_from(SafetyAction)).scalar_one()
    assert before == after == 0
    assert not db_session.new
    assert not db_session.dirty
