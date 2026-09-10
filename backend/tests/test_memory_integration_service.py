"""SIE Milestone 41: Learning Integration & Intelligence Adaptation
Architecture — service-level tests for
`app/intelligence/memory_integration.py`. Mirrors
`tests/test_organizational_memory_service.py`'s own established shape:
direct calls against `db_session`, no HTTP layer. HTTP-layer coverage
(authorization, tenant isolation over the wire, pagination, decision
traceability) lives in `tests/test_memory_integration_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence.attention import compose_attention
from app.intelligence.memory_integration import (
    MemoryApplicabilityBasis,
    resolve_eligible_organizational_memories,
)
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus
from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus, OrganizationalMemoryType
from app.models.project import Project
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
)
from app.services.project_site_service import link_project_site
from tests.intelligence_test_helpers import make_org, make_safety_event, make_site, seed_risk_area_ontology_concepts

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _as_utc(value: datetime) -> datetime:
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


def _make_event(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, source_record_id=str(uuid.uuid4()), **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def _make_accepted_memory(db_session, org_id, decision_id, *, site_id=None, memory_type=OrganizationalMemoryType.LESSON_LEARNED):
    """Full chain: outcome (optionally site-scoped) -> VERIFIED
    verification -> eligible candidate -> ACCEPTED governance ->
    OrganizationalMemory. Returns (memory, outcome)."""
    good_event = _make_event(db_session, org_id, event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF - timedelta(days=1))
    with outcome_mutation_transaction(db_session):
        outcome = record_outcome(
            db_session,
            organization_id=org_id,
            decision_id=decision_id,
            site_id=site_id,
            linked_action_id=None,
            classification=IntelligenceOutcomeClassification.EFFECTIVE,
            summary="Follow-up observation confirmed the hazard was corrected.",
            evidence_event_ids=[good_event.id],
            outcome_at=AS_OF,
            recorded_by_user_id=uuid.uuid4(),
            recorded_by_api_client_id=None,
            request_id=None,
        )
    with verification_mutation_transaction(db_session):
        record_verification(
            db_session, organization_id=org_id, outcome_id=outcome.id,
            status=IntelligenceOutcomeVerificationStatus.VERIFIED, rationale="Confirmed on-site.",
            verified_at=AS_OF, verified_by_user_id=uuid.uuid4(), verified_by_api_client_id=None, request_id=None,
        )
    with candidate_mutation_transaction(db_session):
        candidate, _ = create_learning_candidate(
            db_session, organization_id=org_id, outcome_id=outcome.id,
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    with governance_mutation_transaction(db_session):
        record_governance_decision(
            db_session, organization_id=org_id, candidate_id=candidate.id,
            status=IntelligenceLearningCandidateGovernanceStatus.ACCEPTED, rationale="Worth remembering.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )
    with memory_mutation_transaction(db_session):
        memory, _ = create_organizational_memory(
            db_session, organization_id=org_id, learning_candidate_id=candidate.id,
            memory_type=memory_type,
            title="Permit checks should precede coordination meetings",
            memory_content=(
                "Repeated permit deviations during simultaneous operations indicate that permit "
                "verification should occur before the coordination meeting."
            ),
            rationale="This pattern recurred across multiple accepted candidates.",
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    return memory, outcome


def _retract(db_session, org_id, memory_id, **overrides):
    kwargs = dict(
        organization_id=org_id, memory_id=memory_id,
        status=OrganizationalMemoryGovernanceStatus.RETRACTED, rationale="No longer applicable.",
        decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
    )
    kwargs.update(overrides)
    with memory_governance_mutation_transaction(db_session):
        return record_memory_governance_decision(db_session, **kwargs)


# --- A/C: ACTIVE (implicit and explicit) integration --------------------------------------------


def test_memory_with_no_governance_is_implicitly_active_and_eligible(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)

    result = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert [m.memory_id for m in result.items] == [memory.id]
    assert result.items[0].governance_status == "ACTIVE"
    assert result.items[0].governance_is_explicit is False


def test_explicitly_active_memory_is_eligible(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    with memory_governance_mutation_transaction(db_session):
        record_memory_governance_decision(
            db_session, organization_id=org.id, memory_id=memory.id,
            status=OrganizationalMemoryGovernanceStatus.ACTIVE, rationale="Confirmed still relevant.",
            decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
        )

    result = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert [m.memory_id for m in result.items] == [memory.id]
    assert result.items[0].governance_is_explicit is True


# --- B: RETRACTED exclusion ----------------------------------------------------------------------


def test_retracted_memory_is_excluded_from_current_integration(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    _retract(db_session, org.id, memory.id)

    result = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert result.items == []


# --- D: as_of correctness (creation time) --------------------------------------------------------


def test_memory_created_after_as_of_is_excluded(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    early_cutoff = _as_utc(memory.created_at) - timedelta(days=1)

    result = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", as_of=early_cutoff
    )
    assert result.items == []


def test_memory_created_before_as_of_is_included(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    future_cutoff = _as_utc(memory.created_at) + timedelta(days=1)

    result = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", as_of=future_cutoff
    )
    assert [m.memory_id for m in result.items] == [memory.id]


# --- E/F: historical governance correctness (the spec's own worked example) ---------------------


def test_memory_active_at_t_but_retracted_later_is_included_at_t(db_session):
    """Memory created, then later retracted. Evaluated at a `T` captured
    strictly between the two events (`OrganizationalMemory.created_at`/
    `OrganizationalMemoryGovernanceDecision.created_at` are both
    server-derived real wall-clock timestamps -- not backdatable like
    `outcome_at`/`verified_at` -- so `T` must be an actual instant
    captured between the two calls, mirroring `tests/test_intelligence_
    outcome_verifications_api.py::test_as_of_excludes_verifications_
    recorded_after_the_cutoff`'s own established pattern, rather than an
    arithmetic offset from either row's own timestamp)."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    mid_point = datetime.now(timezone.utc)
    _retract(db_session, org.id, memory.id)  # retracted strictly after mid_point

    result = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", as_of=mid_point
    )
    assert [m.memory_id for m in result.items] == [memory.id]


def test_memory_retracted_before_t_is_excluded_at_t(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    retraction = _retract(db_session, org.id, memory.id)
    later_cutoff = _as_utc(retraction.created_at) + timedelta(days=1)

    result = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", as_of=later_cutoff
    )
    assert result.items == []


def test_current_reconstruction_does_not_use_todays_governance_for_historical_context(db_session):
    """Explicit anti-regression for the spec's own "do NOT simply use
    current-state governance for historical contexts" warning."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id)
    before_retraction = datetime.now(timezone.utc)
    _retract(db_session, org.id, memory.id)  # current state is now RETRACTED

    # Historical reconstruction at a point before the retraction ever
    # happened must still show ACTIVE -- not "RETRACTED" merely because
    # that is today's current state.
    historical = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", as_of=before_retraction
    )
    current = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert [m.memory_id for m in historical.items] == [memory.id]
    assert current.items == []


# --- G: tenant isolation --------------------------------------------------------------------------


def test_organization_a_memory_never_appears_in_organization_b_context(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_a.id)
    decision_a = _make_decision(db_session, org_a.id)
    _make_accepted_memory(db_session, org_a.id, decision_a.id)

    result_b = resolve_eligible_organizational_memories(db_session, organization_id=org_b.id, scope="organization")
    assert result_b.items == []


# --- H/I: applicability (site/project scope) ------------------------------------------------------


def test_organization_wide_memory_included_at_every_scope(db_session):
    """A memory whose originating outcome has no site_id is
    ORGANIZATION_WIDE -- included at organization scope and at every
    site scope."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id, site_id=None)

    org_scope = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    site_scope = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="site", site_id=site.id
    )
    assert [m.memory_id for m in org_scope.items] == [memory.id]
    assert org_scope.items[0].applicability_basis == MemoryApplicabilityBasis.ORGANIZATION_WIDE.value
    assert [m.memory_id for m in site_scope.items] == [memory.id]
    assert site_scope.items[0].applicability_basis == MemoryApplicabilityBasis.ORGANIZATION_WIDE.value


def test_site_specific_memory_excluded_from_a_different_site(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, "Site A")
    site_b = make_site(db_session, org.id, "Site B")
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id, site_id=site_a.id)

    same_site = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="site", site_id=site_a.id
    )
    other_site = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="site", site_id=site_b.id
    )
    assert [m.memory_id for m in same_site.items] == [memory.id]
    assert same_site.items[0].applicability_basis == MemoryApplicabilityBasis.SITE_MATCH.value
    assert other_site.items == []


def test_site_specific_memory_included_at_organization_scope_rollup(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, _outcome = _make_accepted_memory(db_session, org.id, decision.id, site_id=site.id)

    result = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert [m.memory_id for m in result.items] == [memory.id]
    assert result.items[0].applicability_basis == MemoryApplicabilityBasis.ORGANIZATION_SCOPE_ROLLUP.value


def test_project_scope_includes_memory_from_an_associated_site_only(db_session):
    org = make_org(db_session)
    site_in_project = make_site(db_session, org.id, "In-Project Site")
    site_outside_project = make_site(db_session, org.id, "Outside Site")
    project = Project(organization_id=org.id, name="Test Project")
    db_session.add(project)
    db_session.commit()
    link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site_in_project.id,
        created_by_user_id=uuid.uuid4(), created_by_api_client_id=None,
    )
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory_in, _ = _make_accepted_memory(db_session, org.id, decision.id, site_id=site_in_project.id)
    memory_out, _ = _make_accepted_memory(db_session, org.id, decision.id, site_id=site_outside_project.id)

    result = resolve_eligible_organizational_memories(
        db_session, organization_id=org.id, scope="organization", project_id=project.id
    )
    memory_ids = {m.memory_id for m in result.items}
    assert memory_ids == {memory_in.id}
    included = next(m for m in result.items if m.memory_id == memory_in.id)
    assert included.applicability_basis == MemoryApplicabilityBasis.PROJECT_SITE_MATCH.value


# --- J: provenance ----------------------------------------------------------------------------


def test_integrated_memory_carries_full_provenance_chain(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory, outcome = _make_accepted_memory(db_session, org.id, decision.id)

    result = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    item = result.items[0]
    assert item.memory_id == memory.id
    assert item.learning_candidate_id == memory.learning_candidate_id
    assert item.outcome_id == outcome.id
    assert item.verification_id is not None


# --- L: no content duplication / read-only, by construction --------------------------------------


def test_resolving_memories_never_writes_to_the_database(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    _make_accepted_memory(db_session, org.id, decision.id)
    db_session.commit()  # flush any pending state from setup before the assertion

    resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    assert len(db_session.new) == 0
    assert len(db_session.dirty) == 0


# --- M/N/P: no autonomous learning / no rule mutation / no auto-creation -------------------------


def test_no_llm_or_ml_dependency_is_used():
    import inspect

    import app.intelligence.memory_integration as module

    source = inspect.getsource(module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers", "sklearn", "torch")
    for line in import_lines:
        lowered = line.lower()
        assert not any(name in lowered for name in forbidden), f"unexpected ML/AI-provider import: {line}"


def test_module_never_imports_a_memory_or_governance_creation_function():
    """§P/§13 -- this module must never be able to create a memory,
    accept/reject a learning candidate, or record memory governance --
    it only ever resolves/reads existing, already-governed state."""
    import inspect

    import app.intelligence.memory_integration as module

    source = inspect.getsource(module)
    forbidden_symbols = (
        "create_organizational_memory",
        "record_memory_governance_decision",
        "create_learning_candidate",
        "record_governance_decision",
        "record_outcome",
        "record_verification",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source, f"memory_integration.py must never reference {symbol}"


def test_module_never_writes_to_the_database():
    """AST-based check: no `db.add(...)`/`db.flush(...)`/`db.commit(...)`
    call anywhere in this module's actual code -- read-only, by
    construction (module docstring). Parses the AST rather than
    grepping source text, since the module's own docstring legitimately
    *mentions* these calls in prose while explaining why they never
    happen."""
    import ast
    import inspect

    import app.intelligence.memory_integration as module

    tree = ast.parse(inspect.getsource(module))
    forbidden_methods = {"add", "flush", "commit"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_methods and isinstance(node.func.value, ast.Name) and node.func.value.id == "db":
                pytest.fail(f"memory_integration.py must never call db.{node.func.attr}(...)")


def test_module_does_not_reference_model_threshold_or_ontology_mutation():
    """§M/§N -- confirm no reference anywhere in this module to the
    machinery that would mutate a predictive model, threshold, risk
    formula, ontology, or terminology mapping."""
    import inspect

    import app.intelligence.memory_integration as module

    source = inspect.getsource(module)
    forbidden_symbols = (
        "ModelRegistry", "train_model", "retrain", "OntologyConcept", "TerminologyMappingDecision",
        "propose_concept", "approve_concept",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source, f"memory_integration.py must never reference {symbol}"


# --- U: deterministic ordering --------------------------------------------------------------------


def test_repeated_evaluation_produces_identical_ordering(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory_1, _ = _make_accepted_memory(db_session, org.id, decision.id)
    memory_2, _ = _make_accepted_memory(db_session, org.id, decision.id)
    memory_3, _ = _make_accepted_memory(db_session, org.id, decision.id)

    first = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    second = resolve_eligible_organizational_memories(db_session, organization_id=org.id, scope="organization")
    first_ids = [m.memory_id for m in first.items]
    second_ids = [m.memory_id for m in second.items]
    assert first_ids == second_ids
    assert len(first_ids) == 3
    # Newest-first, mirrors every other M37-M40 list read in this codebase.
    assert first_ids == [memory_3.id, memory_2.id, memory_1.id]
