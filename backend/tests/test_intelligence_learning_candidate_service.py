"""SIE Milestone 39: Learning Candidate Foundation — service-level tests
for `app/services/intelligence_learning_candidate_service.py`. Mirrors
`tests/test_intelligence_outcome_verification_service.py`'s own
established shape: direct calls against `db_session`, no HTTP layer.
HTTP-layer coverage (authorization, tenant isolation over the wire,
idempotency, response contract, point-in-time filtering) lives in
`tests/test_intelligence_learning_candidates_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.intelligence.attention import compose_attention
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus
from app.services.intelligence_decision_service import decision_mutation_transaction, record_decision
from app.services.intelligence_learning_candidate_service import (
    candidate_mutation_transaction,
    create_learning_candidate,
    governance_mutation_transaction,
    record_governance_decision,
    resolve_candidate_reference,
    resolve_current_governance,
)
from app.services.intelligence_outcome_service import outcome_mutation_transaction, record_outcome
from app.services.intelligence_outcome_verification_service import (
    verification_mutation_transaction,
    record_verification,
)
from tests.intelligence_test_helpers import make_org, make_safety_event, seed_risk_area_ontology_concepts

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite does not round-trip `tzinfo` through a commit/expire cycle
    -- identical, already-established pattern used throughout this
    codebase."""
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


def _make_decision(db_session, org_id):
    result = compose_attention(db_session, organization_id=org_id, scope="organization", as_of=AS_OF, window_days=30)
    assert result.items, "expected at least one attention item for this fixture"
    item = result.items[0]
    with decision_mutation_transaction(db_session):
        decision = record_decision(
            db_session,
            organization_id=org_id,
            item=item,
            decision=IntelligenceDecisionType.ACT,
            rationale="Field conditions require immediate intervention.",
            linked_action_id=None,
            decided_by_user_id=uuid.uuid4(),
            decided_by_api_client_id=None,
            request_id=None,
        )
    return decision


def _make_outcome(db_session, org_id, decision_id, **overrides):
    kwargs = dict(
        organization_id=org_id,
        decision_id=decision_id,
        site_id=None,
        linked_action_id=None,
        classification=IntelligenceOutcomeClassification.EFFECTIVE,
        summary="Follow-up observation confirmed the hazard was corrected.",
        evidence_event_ids=None,
        outcome_at=AS_OF,
        recorded_by_user_id=uuid.uuid4(),
        recorded_by_api_client_id=None,
        request_id=None,
    )
    kwargs.update(overrides)
    with outcome_mutation_transaction(db_session):
        outcome = record_outcome(db_session, **kwargs)
    return outcome


def _make_event(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, source_record_id=str(uuid.uuid4()), **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def _make_verified_outcome(db_session, org_id, decision_id):
    """A fully eligible outcome: a valid evidence event, and a `VERIFIED`
    current verification -- the one precondition `create_learning_
    candidate()` requires (M39 spec §6)."""
    good_event = _make_event(db_session, org_id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org_id, decision_id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org_id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Confirmed on-site.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    return outcome


# --- create_learning_candidate: the eligibility gate ---------------------------------------------


def test_create_candidate_succeeds_for_a_verified_outcome_with_valid_evidence(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)

    with candidate_mutation_transaction(db_session):
        candidate, created = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id="req-1",
        )
    assert created is True
    assert candidate.organization_id == org.id
    assert candidate.outcome_id == outcome.id
    assert candidate.verification_id is not None
    assert candidate.request_id == "req-1"


def test_create_candidate_rejects_a_never_verified_outcome(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    with pytest.raises(HTTPException) as exc_info:
        with candidate_mutation_transaction(db_session):
            create_learning_candidate(
                db_session, organization_id=org.id, outcome_id=outcome.id,
                created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
            )
    assert exc_info.value.status_code == 422


def test_create_candidate_rejects_insufficient_evidence_verification(db_session):
    """§23: INSUFFICIENT_EVIDENCE must not become a learning candidate."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.INSUFFICIENT_EVIDENCE, rationale="No evidence supplied.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        with candidate_mutation_transaction(db_session):
            create_learning_candidate(
                db_session, organization_id=org.id, outcome_id=outcome.id,
                created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
            )
    assert exc_info.value.status_code == 422


def test_create_candidate_rejects_disputed_verification(db_session):
    """§23: DISPUTED must not become a learning candidate."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.DISPUTED, rationale="Reviewer disagrees.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        with candidate_mutation_transaction(db_session):
            create_learning_candidate(
                db_session, organization_id=org.id, outcome_id=outcome.id,
                created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
            )
    assert exc_info.value.status_code == 422


def test_create_candidate_rejects_verified_status_with_invalid_evidence(db_session):
    """Defense-in-depth: even a `VERIFIED` row (bypassing the API
    route's own write-time evidence check, as a direct service-level
    call here does) must not become eligible when the evidence itself is
    not independently valid -- reuses `evaluate_learning_eligibility()`
    verbatim, never forked."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=None)
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Bypassing the route's own check.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        with candidate_mutation_transaction(db_session):
            create_learning_candidate(
                db_session, organization_id=org.id, outcome_id=outcome.id,
                created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
            )
    assert exc_info.value.status_code == 422


def test_create_candidate_pins_the_resolved_current_verification(db_session):
    """M39 spec §5: `verification_id` is pinned to the exact row that
    made the candidate eligible, not merely "some verification"."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.DISPUTED, rationale="First pass, disputed.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    with verification_mutation_transaction(db_session):
        second_verification = record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Reviewed again, confirmed.",
            verified_at=AS_OF + timedelta(days=1), verified_by_user_id=uuid.uuid4(),
            verified_by_api_client_id=None, request_id=None,
        )

    with candidate_mutation_transaction(db_session):
        candidate, created = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    assert created is True
    assert candidate.verification_id == second_verification.id


# --- Idempotent by construction: UNIQUE(organization_id, outcome_id) -----------------------------


def test_create_candidate_is_idempotent_by_construction(db_session):
    """M39 spec §15: a repeat call for the same outcome returns the
    existing row, `created=False`, never a duplicate or an error."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)

    with candidate_mutation_transaction(db_session):
        first, first_created = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    with candidate_mutation_transaction(db_session):
        second, second_created = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id


# --- resolve_candidate_reference: tenant boundary -------------------------------------------------


def test_resolve_candidate_reference_finds_the_matching_candidate(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    resolved = resolve_candidate_reference(db_session, organization_id=org.id, candidate_id=candidate.id)
    assert resolved.id == candidate.id


def test_resolve_candidate_reference_404s_for_a_nonexistent_id(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        resolve_candidate_reference(db_session, organization_id=org.id, candidate_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_resolve_candidate_reference_rejects_a_cross_tenant_candidate(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)
    decision_b = _make_decision(db_session, org_b.id)
    outcome_b = _make_verified_outcome(db_session, org_b.id, decision_b.id)
    with candidate_mutation_transaction(db_session):
        candidate_b, _ = create_learning_candidate(
            db_session, organization_id=org_b.id, outcome_id=outcome_b.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        resolve_candidate_reference(db_session, organization_id=org_a.id, candidate_id=candidate_b.id)
    assert exc_info.value.status_code == 404


# --- Governance: record_governance_decision / resolve_current_governance -------------------------


def test_record_governance_decision_persists_every_field(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    user_id = uuid.uuid4()

    with governance_mutation_transaction(db_session):
        record = record_governance_decision(
            db_session, organization_id=org.id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.ACCEPTED,
            rationale="This experience is representative and worth learning from.",
            decided_by_user_id=user_id, decided_by_api_client_id=None, request_id="req-gov-1",
        )

    assert record.candidate_id == candidate.id
    assert record.status == IntelligenceLearningCandidateGovernanceStatus.ACCEPTED
    assert record.rationale == "This experience is representative and worth learning from."
    assert record.decided_by_user_id == user_id
    assert record.decided_by_api_client_id is None
    assert record.request_id == "req-gov-1"
    assert record.decided_at is not None  # server-derived, see model docstring


def test_resolve_current_governance_is_none_when_never_governed(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    current = resolve_current_governance(db_session, organization_id=org.id, candidate_id=candidate.id)
    assert current is None  # "pending" -- a distinct initial state


def test_resolve_current_governance_returns_the_newest_row(db_session):
    """§10: a reviewer changing their mind is a second row, never an
    in-place edit -- resolves to the single most recent row."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    with governance_mutation_transaction(db_session):
        first = record_governance_decision(
            db_session, organization_id=org.id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.REJECTED, rationale="Not representative enough.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    with governance_mutation_transaction(db_session):
        second = record_governance_decision(
            db_session, organization_id=org.id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.ACCEPTED, rationale="Reconsidered -- worth keeping.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    current = resolve_current_governance(db_session, organization_id=org.id, candidate_id=candidate.id)
    assert current.id == second.id
    assert current.status == IntelligenceLearningCandidateGovernanceStatus.ACCEPTED
    assert first.id != second.id  # the first row is never destroyed


def test_resolve_current_governance_as_of_excludes_a_later_row(db_session):
    """§20 (temporal): a governance decision recorded after as_of must
    not appear in a historical reconstruction."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )

    with governance_mutation_transaction(db_session):
        first = record_governance_decision(
            db_session, organization_id=org.id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.REJECTED, rationale="First pass.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    cutoff = _as_utc(first.created_at)
    with governance_mutation_transaction(db_session):
        record_governance_decision(
            db_session, organization_id=org.id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.ACCEPTED, rationale="Later reviewer disagrees.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    current_as_of_cutoff = resolve_current_governance(
        db_session, organization_id=org.id, candidate_id=candidate.id, as_of=cutoff
    )
    assert current_as_of_cutoff.id == first.id


# --- No automatic learning / no ML dependency ------------------------------------------------


def test_no_llm_or_ml_dependency_is_used():
    """§12/§24: no LLM, no ML training library, is invoked anywhere in
    this module -- a static check of the module's own imports, since a
    dynamic mock-based test cannot prove a negative for a dependency
    that was never wired in the first place."""
    import inspect

    import app.services.intelligence_learning_candidate_service as module

    source = inspect.getsource(module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers", "sklearn", "torch")
    for line in import_lines:
        lowered = line.lower()
        assert not any(name in lowered for name in forbidden), f"unexpected ML/AI-provider import: {line}"


def test_service_exposes_no_update_function():
    """§10/§13: append-only by construction -- this module deliberately
    exposes no update/correction function for either the candidate or a
    governance decision. A correction is a second governance-decision
    row referencing the same candidate_id."""
    import app.services.intelligence_learning_candidate_service as module

    assert not any(name.startswith("update") for name in module.__all__)
    assert not any(name.startswith("correct") for name in module.__all__)
    assert not any(name.startswith("delete") for name in module.__all__)
