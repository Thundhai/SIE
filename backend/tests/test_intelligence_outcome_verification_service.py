"""SIE Milestone 38: Outcome Verification & Evidence — service-level
tests for `app/services/intelligence_outcome_verification_service.py`.
Mirrors `tests/test_intelligence_outcome_service.py`'s own established
shape: direct calls against `db_session`, no HTTP layer. HTTP-layer
coverage (authorization, tenant isolation over the wire, idempotency,
response contract, point-in-time filtering) lives in
`tests/test_intelligence_outcome_verifications_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.intelligence.attention import compose_attention
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification_enums import (
    EvidenceStatus,
    IntelligenceOutcomeVerificationStatus,
)
from app.services.intelligence_decision_service import decision_mutation_transaction, record_decision
from app.services.intelligence_outcome_service import outcome_mutation_transaction, record_outcome
from app.services.intelligence_outcome_verification_service import (
    evaluate_learning_eligibility,
    evaluate_outcome_evidence,
    record_verification,
    reject_future_verified_at,
    resolve_current_verification,
    resolve_outcome_reference,
    verification_mutation_transaction,
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


# --- resolve_outcome_reference: tenant boundary -----------------------------------------------


def test_resolve_outcome_reference_finds_the_matching_outcome(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    resolved = resolve_outcome_reference(db_session, organization_id=org.id, outcome_id=outcome.id)
    assert resolved.id == outcome.id


def test_resolve_outcome_reference_404s_for_a_nonexistent_id(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        resolve_outcome_reference(db_session, organization_id=org.id, outcome_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_resolve_outcome_reference_rejects_a_cross_tenant_outcome(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)
    decision_b = _make_decision(db_session, org_b.id)
    outcome_b = _make_outcome(db_session, org_b.id, decision_b.id)

    with pytest.raises(HTTPException) as exc_info:
        resolve_outcome_reference(db_session, organization_id=org_a.id, outcome_id=outcome_b.id)
    assert exc_info.value.status_code == 404


# --- reject_future_verified_at ------------------------------------------------------------------


def test_reject_future_verified_at_accepts_the_past():
    reject_future_verified_at(datetime.now(timezone.utc) - timedelta(days=1))  # must not raise


def test_reject_future_verified_at_rejects_the_future():
    with pytest.raises(HTTPException) as exc_info:
        reject_future_verified_at(datetime.now(timezone.utc) + timedelta(days=1))
    assert exc_info.value.status_code == 422


# --- evaluate_outcome_evidence: deterministic evidence checks -----------------------------------


def test_evidence_evaluation_with_no_evidence_is_no_evidence_status(db_session):
    """§2: an outcome with no evidence must never be falsely treated as
    evidence-backed."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=None)

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.evidence_count == 0
    assert evaluation.evidence_status == EvidenceStatus.NO_EVIDENCE
    assert evaluation.evidence_eligible_for_verification is False


def test_evidence_evaluation_rejects_a_nonexistent_evidence_event(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    fake_event_id = uuid.uuid4()
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[fake_event_id])

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.evidence_count == 1
    assert evaluation.invalid_evidence_count == 1
    assert evaluation.valid_evidence_count == 0
    assert evaluation.evidence_status == EvidenceStatus.INVALID_EVIDENCE
    assert evaluation.evidence_eligible_for_verification is False
    assert any(str(fake_event_id) in reason for reason in evaluation.reasons)


def test_evidence_evaluation_rejects_a_cross_tenant_evidence_event(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_a.id)
    decision_a = _make_decision(db_session, org_a.id)
    event_b = _make_event(db_session, org_b.id, event_time=AS_OF, ingestion_time=AS_OF)
    outcome = _make_outcome(db_session, org_a.id, decision_a.id, evidence_event_ids=[event_b.id])

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.invalid_evidence_count == 1
    assert evaluation.evidence_status == EvidenceStatus.INVALID_EVIDENCE


def test_evidence_evaluation_rejects_a_future_evidence_event(db_session):
    """§5: evidence must not be from the future relative to the
    outcome's own outcome_at."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    future_event = _make_event(
        db_session, org.id, event_time=AS_OF + timedelta(days=5), ingestion_time=AS_OF + timedelta(days=5)
    )
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[future_event.id])

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.future_evidence_count == 1
    assert evaluation.valid_evidence_count == 0
    assert evaluation.evidence_status == EvidenceStatus.INVALID_EVIDENCE


def test_evidence_evaluation_rejects_an_event_ingested_after_outcome_was_recorded(db_session):
    """§6: an evidence event whose event_time predates outcome_at but
    whose own ingestion_time postdates the outcome's created_at must not
    silently become valid historical evidence -- mirrors
    `events_as_of()`'s own dual-timestamp discipline."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    # event_time predates outcome_at (AS_OF) -- looks legitimate on that
    # axis alone -- but ingestion_time is set to a moment after the
    # outcome will be recorded (created_at, effectively "now" for this
    # test run, which is always after AS_OF, a fixed 2026-06-01 fixture
    # date already in the past relative to whenever this suite runs).
    late_ingested_event = _make_event(
        db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=datetime.now(timezone.utc) + timedelta(days=1)
    )
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[late_ingested_event.id])

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.valid_evidence_count == 0
    assert evaluation.invalid_evidence_count == 1
    assert evaluation.evidence_status == EvidenceStatus.INVALID_EVIDENCE
    assert any("ingested after this outcome was recorded" in reason for reason in evaluation.reasons)


def test_evidence_evaluation_with_valid_evidence_is_valid_status(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.evidence_count == 1
    assert evaluation.valid_evidence_count == 1
    assert evaluation.evidence_status == EvidenceStatus.VALID_EVIDENCE
    assert evaluation.evidence_eligible_for_verification is True


def test_evidence_evaluation_mixed_valid_and_invalid_is_insufficient(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(
        db_session, org.id, decision.id, evidence_event_ids=[good_event.id, uuid.uuid4()]
    )

    evaluation = evaluate_outcome_evidence(db_session, outcome)
    assert evaluation.evidence_count == 2
    assert evaluation.valid_evidence_count == 1
    assert evaluation.invalid_evidence_count == 1
    assert evaluation.evidence_status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert evaluation.evidence_eligible_for_verification is False


def test_evidence_evaluation_is_deterministic(db_session):
    """§23: repeated evaluation of the same outcome yields identical
    results -- no randomness, no LLM, no fuzzy matching."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])

    first = evaluate_outcome_evidence(db_session, outcome)
    second = evaluate_outcome_evidence(db_session, outcome)
    assert first == second


def test_no_llm_or_external_ai_dependency_is_used():
    """§24: no LLM is invoked anywhere in the verification/evidence
    evaluation path -- a static check of the module's own imports,
    since a dynamic mock-based test cannot prove a negative for a
    dependency that was never wired in the first place."""
    import inspect

    import app.services.intelligence_outcome_verification_service as module

    source = inspect.getsource(module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers")
    for line in import_lines:
        lowered = line.lower()
        assert not any(name in lowered for name in forbidden), f"unexpected AI-provider import: {line}"


# --- record_verification ---------------------------------------------------------------------


def test_record_verification_persists_every_field(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)
    user_id = uuid.uuid4()

    with verification_mutation_transaction(db_session):
        record = record_verification(
            db_session,
            organization_id=org.id,
            outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.INSUFFICIENT_EVIDENCE,
            rationale="No follow-up evidence was supplied.",
            verified_at=AS_OF,
            verified_by_user_id=user_id,
            verified_by_api_client_id=None,
            request_id="req-verify-1",
        )

    assert record.outcome_id == outcome.id
    assert record.status == IntelligenceOutcomeVerificationStatus.INSUFFICIENT_EVIDENCE
    assert record.rationale == "No follow-up evidence was supplied."
    assert _as_utc(record.verified_at) == AS_OF
    assert record.verified_by_user_id == user_id
    assert record.verified_by_api_client_id is None
    assert record.request_id == "req-verify-1"
    assert record.id is not None


def test_every_verification_status_is_recordable(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    for verification_status in IntelligenceOutcomeVerificationStatus:
        with verification_mutation_transaction(db_session):
            record = record_verification(
                db_session,
                organization_id=org.id,
                outcome_id=outcome.id,
                status=verification_status,
                rationale=f"Testing {verification_status.value}.",
                verified_at=AS_OF,
                verified_by_user_id=uuid.uuid4(),
                verified_by_api_client_id=None,
                request_id=None,
            )
        assert record.status == verification_status


# --- resolve_current_verification: deterministic latest-wins ------------------------------------


def test_resolve_current_verification_is_none_when_never_recorded(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    current = resolve_current_verification(db_session, organization_id=org.id, outcome_id=outcome.id)
    assert current is None


def test_resolve_current_verification_returns_the_newest_row(db_session):
    """§11: latest verification state resolves deterministically --
    newest by created_at, never an aggregate or vote."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    with verification_mutation_transaction(db_session):
        first = record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.INSUFFICIENT_EVIDENCE, rationale="First pass.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    with verification_mutation_transaction(db_session):
        second = record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.DISPUTED, rationale="Second reviewer disagrees.",
            verified_at=AS_OF + timedelta(days=1), verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None,
            request_id=None,
        )

    current = resolve_current_verification(db_session, organization_id=org.id, outcome_id=outcome.id)
    assert current.id == second.id
    assert current.status == IntelligenceOutcomeVerificationStatus.DISPUTED
    assert first.id != second.id  # the first row is never destroyed


def test_resolve_current_verification_as_of_excludes_a_later_row(db_session):
    """§20: a verification created after as_of must not appear."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    with verification_mutation_transaction(db_session):
        first = record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.INSUFFICIENT_EVIDENCE, rationale="First pass.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    cutoff = _as_utc(first.created_at)
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.DISPUTED, rationale="Later reviewer disagrees.",
            verified_at=AS_OF + timedelta(days=1), verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None,
            request_id=None,
        )

    current_as_of_cutoff = resolve_current_verification(
        db_session, organization_id=org.id, outcome_id=outcome.id, as_of=cutoff
    )
    assert current_as_of_cutoff.id == first.id


# --- evaluate_learning_eligibility: the gate --------------------------------------------------


def test_learning_eligibility_false_when_never_verified(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_outcome(db_session, org.id, decision.id)

    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert eligibility.eligible is False


def test_learning_eligibility_false_for_insufficient_evidence_status(db_session):
    """§9: INSUFFICIENT_EVIDENCE blocks learning eligibility."""
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

    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert eligibility.eligible is False


def test_learning_eligibility_false_for_disputed_status(db_session):
    """§10: DISPUTED blocks learning eligibility."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.DISPUTED, rationale="Reviewer disagrees with the report.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert eligibility.eligible is False


def test_learning_eligibility_true_when_verified_with_valid_evidence(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Evidence confirmed on-site.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert eligibility.eligible is True
    assert eligibility.reasons == []


def test_learning_eligibility_false_when_verified_status_but_evidence_is_not_actually_valid(db_session):
    """Defense-in-depth (see `evaluate_learning_eligibility()`'s own
    docstring item 4): even if a `VERIFIED` row exists (bypassing the
    API route's own write-time evidence check, as a direct service-level
    call here does), the eligibility gate independently re-checks
    evidence and still refuses eligibility when it is not valid."""
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

    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert eligibility.eligible is False


def test_learning_eligibility_excludes_outcome_not_yet_visible_as_of(db_session):
    """A verification/learning-eligibility read at a historical as_of
    before the outcome's own outcome_at/created_at must not treat the
    outcome as eligible -- mirrors M37's own list-read as_of filter."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Confirmed.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    early_cutoff = AS_OF - timedelta(days=100)
    eligibility = evaluate_learning_eligibility(db_session, outcome=outcome, as_of=early_cutoff)
    assert eligibility.eligible is False


def test_learning_eligibility_is_deterministic(db_session):
    """§25: repeated evaluation yields identical results."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    good_event = _make_event(db_session, org.id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org.id, decision.id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org.id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Confirmed.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )

    first = evaluate_learning_eligibility(db_session, outcome=outcome)
    second = evaluate_learning_eligibility(db_session, outcome=outcome)
    assert first == second


# --- Immutability: no update mechanism exists in this module -----------------------------------


def test_verification_service_exposes_no_update_function():
    """§12/§13: append-only by construction -- this module deliberately
    exposes no update/correction function at all. A correction is a
    second `record_verification()` call referencing the same
    `outcome_id`."""
    import app.services.intelligence_outcome_verification_service as module

    assert not any(name.startswith("update") for name in module.__all__)
    assert not any(name.startswith("correct") for name in module.__all__)
