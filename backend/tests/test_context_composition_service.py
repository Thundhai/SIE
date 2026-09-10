"""SIE Milestone 32: Field Intelligence Context Composition v0.1 —
service-level tests for `app/intelligence/context_composition.py`.
Mirrors `tests/test_enterprise_intelligence_service.py`'s own established
shape: direct calls against `db_session`, no HTTP layer. HTTP-layer
coverage (authorization, tenant isolation over the wire, response
contract) lives in `tests/test_field_intelligence_context_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.intelligence.context_composition import (
    KnowledgeEvidenceOutcome,
    ObservedFactOutcome,
    PredictiveSignalOutcome,
    compose_field_intelligence_context,
)
from app.models.ontology_concept import OntologyConcept
from app.models.prediction import Prediction
from app.models.risk_assessment import RiskAssessment, RiskAssessmentFinding
from app.models.risk_assessment_enums import (
    AssessmentType,
    FindingSource,
    FindingStatus,
    RiskAssessmentScope,
    RiskAssessmentStatus,
    RiskCandidateStatus,
)
from app.models.safety_action import SafetyAction
from app.predictions.enums import PredictionOutcome
from app.predictions.spec import PREDICTION_ENTITY_TYPE
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site, seed_risk_area_ontology_concepts

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _seed_events(db_session, org_id, *, site_id=None, count=3):
    for i in range(count):
        db_session.add(
            make_safety_event(
                organization_id=org_id,
                site_id=site_id,
                event_type="INCIDENT",
                event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()


def _make_assessment(db_session, org_id, *, site_id=None, status=RiskAssessmentStatus.APPROVED, approved_at=None, created_at=None) -> RiskAssessment:
    approved_at = approved_at if approved_at is not None else (AS_OF - timedelta(days=10))
    assessment = RiskAssessment(
        organization_id=org_id,
        scope=RiskAssessmentScope.SITE if site_id else RiskAssessmentScope.ORGANIZATION,
        site_id=site_id,
        title="Composition test assessment",
        assessment_type=AssessmentType.BASELINE,
        status=status,
        lineage_id=uuid.uuid4(),
        version=1,
        assessment_date=AS_OF - timedelta(days=10),
        as_of=AS_OF - timedelta(days=10),
        window_days=30,
        methodology_version="risk-matrix-v1",
        approved_at=approved_at if status == RiskAssessmentStatus.APPROVED else None,
    )
    db_session.add(assessment)
    db_session.commit()
    if created_at is not None:
        db_session.execute(
            RiskAssessment.__table__.update().where(RiskAssessment.id == assessment.id).values(created_at=created_at)
        )
        db_session.commit()
        db_session.refresh(assessment)
    return assessment


def _make_finding(
    db_session, org_id, assessment_id, risk_area_concept_id, *, status=FindingStatus.OPEN,
    candidate_status=None, created_at=None,
) -> RiskAssessmentFinding:
    # Defaults to well before AS_OF -- the sandbox's real wall-clock date
    # is well after AS_OF (2026-06-01), so TimestampMixin's own
    # `default=utcnow` would otherwise stamp `created_at` in what this
    # test suite treats as "the future" relative to AS_OF, and the
    # point-in-time filter this milestone requires would (correctly)
    # exclude it -- explicit here so each test controls that
    # relationship on purpose rather than by accident.
    created_at = created_at if created_at is not None else AS_OF - timedelta(days=5)
    finding = RiskAssessmentFinding(
        organization_id=org_id,
        assessment_id=assessment_id,
        risk_area_concept_id=risk_area_concept_id,
        risk_area_ontology_version=1,
        title="A composition-test finding",
        status=status,
        candidate_status=candidate_status,
        source=FindingSource.MANUAL,
    )
    db_session.add(finding)
    db_session.commit()
    db_session.execute(
        RiskAssessmentFinding.__table__.update()
        .where(RiskAssessmentFinding.id == finding.id)
        .values(created_at=created_at)
    )
    db_session.commit()
    db_session.refresh(finding)
    return finding


def _risk_area_concept_id(db_session) -> uuid.UUID:
    return db_session.execute(
        select(OntologyConcept.id).where(
            OntologyConcept.concept_key == "VEHICLE_INCIDENT", OntologyConcept.organization_id.is_(None)
        )
    ).scalar_one()


def _make_prediction(db_session, org_id, site_id, *, created_at, prediction_time=None) -> Prediction:
    prediction = Prediction(
        organization_id=org_id,
        entity_type=PREDICTION_ENTITY_TYPE,
        entity_id=site_id,
        prediction_time=prediction_time or AS_OF,
        horizon_days=30,
        outcome=PredictionOutcome.PREDICTED.value,
        risk_score=0.42,
        probability=None,
        risk_category="MODERATE",
        model_version="v1",
        data_quality="VALID",
    )
    db_session.add(prediction)
    db_session.commit()
    db_session.execute(Prediction.__table__.update().where(Prediction.id == prediction.id).values(created_at=created_at))
    db_session.commit()
    db_session.refresh(prediction)
    return prediction


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session):
    return seed_risk_area_ontology_concepts(db_session)


# --- Category separation --------------------------------------------------------------------


def test_result_has_four_separate_categories(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)

    assert result.observed is not None
    assert result.deterministic is not None
    assert result.predictive is not None
    assert result.knowledge is not None
    # Never collapsed into one number/shape: deterministic_risk and the
    # predictive signal are reachable only via their own, separate fields.
    assert hasattr(result.deterministic, "risk")
    assert hasattr(result.predictive, "value")
    assert result.deterministic.risk is not result.predictive.value


def test_observed_reuses_enterprise_event_count_without_recomputation(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=5)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.event_count == result.deterministic.event_count == 5
    assert result.observed.evidence_sample_event_ids == result.deterministic.provenance.evidence_sample_event_ids


def test_observed_reuses_enterprise_actions_context_without_recomputation(db_session):
    org = make_org(db_session)
    action = SafetyAction(
        organization_id=org.id, title="An open action", action_type="CORRECTIVE", priority="MEDIUM",
        status="OPEN", attributes={}, created_at=AS_OF - timedelta(days=1),
    )
    db_session.add(action)
    db_session.commit()
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.actions is result.deterministic.actions_context
    assert result.observed.actions.open_action_count == 1
    assert len(result.observed.open_action_sample) == 1
    assert result.observed.open_action_sample[0].action_id == action.id


# --- Predictive staleness rule ----------------------------------------------------------------


def test_predictive_signal_not_available_without_a_recorded_prediction(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="site", site_id=site.id, as_of=AS_OF
    )
    assert result.predictive.outcome == PredictiveSignalOutcome.NOT_AVAILABLE.value
    assert result.predictive.value is None


def test_predictive_signal_available_when_generated_before_as_of(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF - timedelta(days=1))
    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="site", site_id=site.id, as_of=AS_OF
    )
    assert result.predictive.outcome == PredictiveSignalOutcome.AVAILABLE.value
    assert result.predictive.value is not None
    assert result.predictive.value.risk_score == 0.42


def test_predictive_signal_excluded_when_generated_after_as_of(db_session):
    """The staleness rule: a prediction whose row was actually created
    *after* the requested `as_of` must never be presented as if it were
    contemporaneous knowledge, even though it is the latest prediction
    on file and `compute_enterprise_intelligence()` would happily return
    it."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF + timedelta(days=1))
    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="site", site_id=site.id, as_of=AS_OF
    )
    assert result.predictive.outcome == PredictiveSignalOutcome.EXCLUDED_GENERATED_AFTER_AS_OF.value
    assert result.predictive.value is None
    # And the raw, un-filtered orchestrator result still has it -- proof
    # this is a composition-layer decision, not a change to
    # compute_enterprise_intelligence()'s own behavior.
    assert result.deterministic.predictive_context is not None


def test_predictive_signal_is_none_for_organization_scope(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _make_prediction(db_session, org.id, site.id, created_at=AS_OF - timedelta(days=1))
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.predictive.outcome == PredictiveSignalOutcome.NOT_AVAILABLE.value


# --- Observed: findings/controls governance filters -------------------------------------------


def test_open_findings_only_counts_approved_assessments(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    draft = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.DRAFT)
    _make_finding(db_session, org.id, draft.id, concept_id)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0

    approved = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org.id, approved.id, concept_id)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 1
    assert result.observed.open_finding_sample[0].risk_area_label == "VEHICLE_INCIDENT"


def test_open_findings_excludes_closed(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    approved = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org.id, approved.id, concept_id, status=FindingStatus.CLOSED)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0


def test_open_findings_excludes_unreviewed_candidates(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    approved = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org.id, approved.id, concept_id, candidate_status=RiskCandidateStatus.IDENTIFIED)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0

    _make_finding(db_session, org.id, approved.id, concept_id, candidate_status=RiskCandidateStatus.ACCEPTED)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 1


def test_open_findings_excludes_findings_created_after_as_of(db_session):
    """Point-in-time correctness for the Observed category, mirroring
    `events_as_of()`'s own discipline applied to a different table: a
    finding created after the requested `as_of` must not appear in a
    historical context."""
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    approved = _make_assessment(db_session, org.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org.id, approved.id, concept_id, created_at=AS_OF + timedelta(days=1))

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0


def test_open_findings_excludes_assessments_approved_after_as_of(db_session):
    org = make_org(db_session)
    concept_id = _risk_area_concept_id(db_session)
    approved = _make_assessment(
        db_session, org.id, status=RiskAssessmentStatus.APPROVED, approved_at=AS_OF + timedelta(days=1)
    )
    _make_finding(db_session, org.id, approved.id, concept_id)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0


def test_site_scope_filters_findings_to_that_site(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, "Site A")
    site_b = make_site(db_session, org.id, "Site B")
    concept_id = _risk_area_concept_id(db_session)
    assessment_a = _make_assessment(db_session, org.id, site_id=site_a.id, status=RiskAssessmentStatus.APPROVED)
    assessment_b = _make_assessment(db_session, org.id, site_id=site_b.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org.id, assessment_a.id, concept_id)
    _make_finding(db_session, org.id, assessment_b.id, concept_id)

    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="site", site_id=site_a.id, as_of=AS_OF
    )
    assert result.observed.open_finding_count == 1
    assert result.observed.open_finding_sample[0].site_id == site_a.id


# --- Tenant isolation -------------------------------------------------------------------------


def test_findings_never_leak_across_organizations(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    concept_id = _risk_area_concept_id(db_session)
    assessment_b = _make_assessment(db_session, org_b.id, status=RiskAssessmentStatus.APPROVED)
    _make_finding(db_session, org_b.id, assessment_b.id, concept_id)

    result = compose_field_intelligence_context(db_session, organization_id=org_a.id, scope="organization", as_of=AS_OF)
    assert result.observed.open_finding_count == 0
    assert result.organization_id == org_a.id


def test_actions_never_leak_across_organizations(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    db_session.add(
        SafetyAction(
            organization_id=org_b.id, title="Other org's action", action_type="CORRECTIVE", priority="HIGH",
            status="OPEN", attributes={},
        )
    )
    db_session.commit()

    result = compose_field_intelligence_context(db_session, organization_id=org_a.id, scope="organization", as_of=AS_OF)
    assert result.observed.actions.open_action_count == 0
    assert result.observed.open_action_sample == []


# --- Knowledge / Evidence: not queried by default --------------------------------------------


def test_knowledge_not_queried_when_no_query_supplied(db_session):
    org = make_org(db_session)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.knowledge.outcome == KnowledgeEvidenceOutcome.NOT_QUERIED.value
    assert result.knowledge.response is None


def test_knowledge_failure_is_isolated_from_the_rest_of_the_response(db_session):
    """SQLite (the test DB) has no pgvector support, so a supplied query
    makes the retrieval call itself fail -- exactly the failure-isolation
    path this milestone requires: Observed/Deterministic/Predictive must
    still be fully populated even though Knowledge/Evidence could not be
    answered."""
    org = make_org(db_session)
    _seed_events(db_session, org.id, count=2)
    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="organization", as_of=AS_OF, knowledge_query="working at height"
    )
    assert result.knowledge.outcome == KnowledgeEvidenceOutcome.UNAVAILABLE.value
    assert result.knowledge.unavailable_reason is not None
    # The rest of the response is untouched by the Knowledge failure.
    assert result.observed.outcome == ObservedFactOutcome.OK.value
    assert result.observed.event_count == 2
    assert result.deterministic is not None


# --- Calculation versions provenance -----------------------------------------------------------


def test_calculation_versions_include_context_composition_and_enterprise_versions(db_session):
    org = make_org(db_session)
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert "context_composition" in result.calculation_versions
    assert "risk_score" in result.calculation_versions  # inherited from the enterprise orchestrator, unchanged
