"""SIE Milestone 40: Organizational Memory Architecture — service-level
tests for `app/services/organizational_memory_service.py`. Mirrors
`tests/test_intelligence_learning_candidate_service.py`'s own
established shape: direct calls against `db_session`, no HTTP layer.
HTTP-layer coverage (authorization, tenant isolation over the wire,
idempotency, response contract, point-in-time filtering) lives in
`tests/test_organizational_memory_api.py`.
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
from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus, OrganizationalMemoryType
from app.services.intelligence_decision_service import decision_mutation_transaction, record_decision
from app.services.intelligence_learning_candidate_service import (
    candidate_mutation_transaction,
    create_learning_candidate,
    governance_mutation_transaction,
    record_governance_decision,
)
from app.services.intelligence_outcome_service import outcome_mutation_transaction, record_outcome
from app.services.intelligence_outcome_verification_service import (
    record_verification,
    verification_mutation_transaction,
)
from app.services.organizational_memory_service import (
    create_organizational_memory,
    memory_governance_mutation_transaction,
    memory_mutation_transaction,
    record_memory_governance_decision,
    resolve_current_memory_governance,
    resolve_memory_reference,
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
    good_event = _make_event(db_session, org_id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    outcome = _make_outcome(db_session, org_id, decision_id, evidence_event_ids=[good_event.id])
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org_id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Confirmed on-site.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    return outcome


def _make_candidate(db_session, org_id, outcome_id):
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org_id, outcome_id=outcome_id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    return candidate


def _govern_candidate(db_session, org_id, candidate_id, status):
    with governance_mutation_transaction(db_session):
        return record_governance_decision(
            db_session, organization_id=org_id, candidate_id=candidate_id,
            status=status, rationale="Governance test rationale.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )


def _make_accepted_candidate(db_session, org_id, decision_id):
    outcome = _make_verified_outcome(db_session, org_id, decision_id)
    candidate = _make_candidate(db_session, org_id, outcome.id)
    _govern_candidate(db_session, org_id, candidate.id, IntelligenceLearningCandidateGovernanceStatus.ACCEPTED)
    return candidate


def _memory_kwargs(**overrides):
    kwargs = dict(
        memory_type=OrganizationalMemoryType.LESSON_LEARNED,
        title="Permit checks should precede coordination meetings",
        memory_content=(
            "Repeated permit deviations during simultaneous operations indicate that permit "
            "verification should occur before the coordination meeting."
        ),
        rationale="This pattern recurred across multiple accepted candidates and generalizes well.",
        created_by_user_id=uuid.uuid4(),
        created_by_api_client_id=None,
        request_id=None,
    )
    kwargs.update(overrides)
    return kwargs


# --- create_organizational_memory: the governance gate (M40 spec §5) ----------------------------


def test_create_memory_succeeds_for_an_accepted_candidate(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)

    with memory_mutation_transaction(db_session):
        memory, created = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )
    assert created is True
    assert memory.organization_id == org.id
    assert memory.learning_candidate_id == candidate.id
    assert memory.memory_type == OrganizationalMemoryType.LESSON_LEARNED


def test_create_memory_rejects_a_pending_candidate(db_session):
    """A candidate with no governance decision at all must not become
    memory."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    candidate = _make_candidate(db_session, org.id, outcome.id)

    with pytest.raises(HTTPException) as exc_info:
        with memory_mutation_transaction(db_session):
            create_organizational_memory(
                db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
            )
    assert exc_info.value.status_code == 422


def test_create_memory_rejects_a_rejected_candidate(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    candidate = _make_candidate(db_session, org.id, outcome.id)
    _govern_candidate(db_session, org.id, candidate.id, IntelligenceLearningCandidateGovernanceStatus.REJECTED)

    with pytest.raises(HTTPException) as exc_info:
        with memory_mutation_transaction(db_session):
            create_organizational_memory(
                db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
            )
    assert exc_info.value.status_code == 422


def test_create_memory_requires_a_valid_candidate_id(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        with memory_mutation_transaction(db_session):
            create_organizational_memory(
                db_session, organization_id=org.id, learning_candidate_id=uuid.uuid4(), **_memory_kwargs()
            )
    assert exc_info.value.status_code == 404


def test_create_memory_rejects_a_cross_tenant_candidate(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)
    decision_b = _make_decision(db_session, org_b.id)
    candidate_b = _make_accepted_candidate(db_session, org_b.id, decision_b.id)

    with pytest.raises(HTTPException) as exc_info:
        with memory_mutation_transaction(db_session):
            create_organizational_memory(
                db_session, organization_id=org_a.id, learning_candidate_id=candidate_b.id, **_memory_kwargs()
            )
    assert exc_info.value.status_code == 404


def test_create_memory_uses_the_pinned_governance_reflecting_the_most_recent_decision(db_session):
    """A candidate that was first REJECTED and later ACCEPTED (a
    reviewer changing their mind) must resolve to the newest row and
    therefore succeed."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    outcome = _make_verified_outcome(db_session, org.id, decision.id)
    candidate = _make_candidate(db_session, org.id, outcome.id)
    _govern_candidate(db_session, org.id, candidate.id, IntelligenceLearningCandidateGovernanceStatus.REJECTED)
    _govern_candidate(db_session, org.id, candidate.id, IntelligenceLearningCandidateGovernanceStatus.ACCEPTED)

    with memory_mutation_transaction(db_session):
        memory, created = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )
    assert created is True


# --- Idempotent by construction: UNIQUE(organization_id, learning_candidate_id) ------------------


def test_create_memory_is_idempotent_by_construction(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)

    with memory_mutation_transaction(db_session):
        first, first_created = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )
    with memory_mutation_transaction(db_session):
        second, second_created = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id


# --- resolve_memory_reference: tenant boundary ----------------------------------------------------


def test_resolve_memory_reference_finds_the_matching_memory(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    resolved = resolve_memory_reference(db_session, organization_id=org.id, memory_id=memory.id)
    assert resolved.id == memory.id


def test_resolve_memory_reference_404s_for_a_nonexistent_id(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        resolve_memory_reference(db_session, organization_id=org.id, memory_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_resolve_memory_reference_rejects_a_cross_tenant_memory(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_b.id)
    decision_b = _make_decision(db_session, org_b.id)
    candidate_b = _make_accepted_candidate(db_session, org_b.id, decision_b.id)
    with memory_mutation_transaction(db_session):
        memory_b, _ = create_organizational_memory(
            db_session, organization_id=org_b.id, learning_candidate_id=candidate_b.id, **_memory_kwargs()
        )

    with pytest.raises(HTTPException) as exc_info:
        resolve_memory_reference(db_session, organization_id=org_a.id, memory_id=memory_b.id)
    assert exc_info.value.status_code == 404


# --- Governance: record_memory_governance_decision / resolve_current_memory_governance -----------


def test_record_memory_governance_decision_persists_every_field(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )
    user_id = uuid.uuid4()

    with memory_governance_mutation_transaction(db_session):
        record = record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.RETRACTED,
            rationale="This turned out not to generalize as expected.",
            decided_by_user_id=user_id, decided_by_api_client_id=None, request_id="req-gov-1",
        )

    assert record.memory_id == memory.id
    assert record.status == OrganizationalMemoryGovernanceStatus.RETRACTED
    assert record.decided_by_user_id == user_id
    assert record.decided_by_api_client_id is None
    assert record.request_id == "req-gov-1"
    assert record.decided_at is not None  # server-derived, see model docstring


def test_resolve_current_memory_governance_is_none_when_never_governed(db_session):
    """The implicit ACTIVE state -- see OrganizationalMemoryGovernanceStatus's own docstring."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    current = resolve_current_memory_governance(db_session, organization_id=org.id, memory_id=memory.id)
    assert current is None


def test_resolve_current_memory_governance_returns_the_newest_row(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    with memory_governance_mutation_transaction(db_session):
        first = record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.RETRACTED, rationale="No longer applicable.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    with memory_governance_mutation_transaction(db_session):
        second = record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.ACTIVE, rationale="Reconsidered -- still applies.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    current = resolve_current_memory_governance(db_session, organization_id=org.id, memory_id=memory.id)
    assert current.id == second.id
    assert current.status == OrganizationalMemoryGovernanceStatus.ACTIVE
    assert first.id != second.id  # the first row is never destroyed


def test_resolve_current_memory_governance_as_of_excludes_a_later_row(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    with memory_governance_mutation_transaction(db_session):
        first = record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.RETRACTED, rationale="First pass.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    cutoff = _as_utc(first.created_at)
    with memory_governance_mutation_transaction(db_session):
        record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.ACTIVE, rationale="Later reviewer disagrees.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    current_as_of_cutoff = resolve_current_memory_governance(
        db_session, organization_id=org.id, memory_id=memory.id, as_of=cutoff
    )
    assert current_as_of_cutoff.id == first.id


# --- No automatic learning / no ML dependency / no auto-accept -----------------------------------


def test_no_llm_or_ml_dependency_is_used():
    """§25/T: no LLM, no ML training library, is invoked anywhere in
    this module -- a static check of the module's own imports."""
    import inspect

    import app.services.organizational_memory_service as module

    source = inspect.getsource(module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers", "sklearn", "torch")
    for line in import_lines:
        lowered = line.lower()
        assert not any(name in lowered for name in forbidden), f"unexpected ML/AI-provider import: {line}"


def test_service_exposes_no_update_function():
    """Append-only by construction -- this module deliberately exposes
    no update/correction/auto-accept function for either the memory or a
    governance decision."""
    import app.services.organizational_memory_service as module

    assert not any(name.startswith("update") for name in module.__all__)
    assert not any(name.startswith("correct") for name in module.__all__)
    assert not any(name.startswith("delete") for name in module.__all__)
    assert not any("auto" in name for name in module.__all__)


def test_creating_a_memory_never_mutates_the_originating_candidate_or_its_governance(db_session):
    """§I/§J: provenance cannot be detached -- creating a memory leaves
    the candidate and its governance history completely untouched."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    candidate = _make_accepted_candidate(db_session, org.id, decision.id)
    candidate_updated_at_before = candidate.updated_at

    with memory_mutation_transaction(db_session):
        create_organizational_memory(
            db_session, organization_id=org.id, learning_candidate_id=candidate.id, **_memory_kwargs()
        )

    db_session.refresh(candidate)
    assert candidate.updated_at == candidate_updated_at_before
