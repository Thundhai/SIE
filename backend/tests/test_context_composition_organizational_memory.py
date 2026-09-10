"""SIE Milestone 41A: Learning Integration Corrective — tests for the
new `organizational_memory` category on `compose_field_intelligence_
context()` (`app/intelligence/context_composition.py`). Mirrors
`tests/test_memory_integration_service.py`'s own established shape:
direct calls against `db_session`, reusing the identical full-chain
fixture helper (`_make_accepted_memory`) that established suite already
proved correct.

This file does **not** re-derive M41's own eligibility/applicability/
temporal logic — every scenario here calls `compose_field_intelligence_
context()`, which internally calls M41's `resolve_eligible_
organizational_memories()` verbatim (see `_organizational_memory_
context()`'s own docstring). What this file proves is the *seam*:
that the exact same eligible/applicable/temporal/governance behavior
already established by `tests/test_memory_integration_service.py`
is now reachable from the one composition function that also produces
Observed/Deterministic/Predictive/Knowledge — and that adding it there
changes nothing about those four existing categories.

Numbered comments below correspond to the M41A spec's own 26-item test
checklist. Items 21/22 (machine credential organization binding /
human authorized organization selection) and 23 (decision memory
context traceability) are HTTP-layer concerns already covered by
`tests/test_field_intelligence_context_api.py` (unchanged tenant-
isolation gating, reused as-is) and `tests/test_memory_integration_api.py`
(the decision-context endpoint, untouched by M41A) respectively —
re-asserted here at the composition layer only where a new code path
(the new `organizational_memory` field) is actually involved. Item 26
(full regression remains green) is verified by running the whole suite,
not a single test in this file.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence.context_composition import (
    OrganizationalMemoryOutcome,
    compose_field_intelligence_context,
)
from app.intelligence.memory_integration import MemoryApplicabilityBasis
from app.models.intelligence_decision_enums import IntelligenceDecisionType
from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus
from app.models.organizational_memory import OrganizationalMemory, OrganizationalMemoryGovernanceDecision
from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus
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


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session):
    return seed_risk_area_ontology_concepts(db_session)


def _seed_events(db_session, org_id, *, site_id=None, count=5, anchor=AS_OF):
    for i in range(count):
        db_session.add(
            make_safety_event(
                organization_id=org_id,
                site_id=site_id,
                event_type="INCIDENT",
                event_time=anchor - timedelta(days=i),
                ingestion_time=anchor - timedelta(days=i),
                source_record_id=str(uuid.uuid4()),
            )
        )
    db_session.commit()


def _make_event(db_session, org_id, **overrides):
    event = make_safety_event(organization_id=org_id, source_record_id=str(uuid.uuid4()), **overrides)
    db_session.add(event)
    db_session.commit()
    return event


def _make_decision(db_session, org_id, *, anchor=AS_OF):
    from app.intelligence.attention import compose_attention

    result = compose_attention(db_session, organization_id=org_id, scope="organization", as_of=anchor, window_days=30)
    assert result.items, "expected at least one attention item for this fixture"
    with decision_mutation_transaction(db_session):
        decision = record_decision(
            db_session,
            organization_id=org_id,
            item=result.items[0],
            decision=IntelligenceDecisionType.ACT,
            rationale="Field conditions require immediate intervention.",
            linked_action_id=None,
            decided_by_user_id=uuid.uuid4(),
            decided_by_api_client_id=None,
            request_id=None,
        )
    return decision


def _make_accepted_memory(db_session, org_id, decision_id, *, site_id=None, memory_created_at=None):
    """Full chain: outcome (optionally site-scoped) -> VERIFIED
    verification -> eligible candidate -> ACCEPTED governance ->
    OrganizationalMemory. Mirrors `tests/test_memory_integration_
    service.py::_make_accepted_memory` exactly (never a second,
    divergent fixture). Returns the memory."""
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
            memory_type="LESSON_LEARNED",
            title="Permit checks should precede coordination meetings",
            memory_content=(
                "Repeated permit deviations during simultaneous operations indicate that permit "
                "verification should occur before the coordination meeting."
            ),
            rationale="This pattern recurred across multiple accepted candidates.",
            created_by_user_id=uuid.uuid4(), created_by_api_client_id=None, request_id=None,
        )
    if memory_created_at is not None:
        db_session.execute(
            OrganizationalMemory.__table__.update().where(OrganizationalMemory.id == memory.id).values(created_at=memory_created_at)
        )
        db_session.commit()
        db_session.refresh(memory)
    return memory


def _retract(db_session, org_id, memory_id, *, decision_created_at=None, **overrides):
    """`decision_created_at`, when given, directly backdates the
    resulting row's (server-derived) `created_at` via a raw UPDATE --
    mirrors `_make_accepted_memory`'s own `memory_created_at` override.
    `record_memory_governance_decision()` itself has no such parameter
    (`decided_at` is deliberately always "now", see the model's own
    docstring), so this is the only way to place a governance decision
    at an exact, controlled point in time for a test."""
    kwargs = dict(
        organization_id=org_id, memory_id=memory_id,
        status=OrganizationalMemoryGovernanceStatus.RETRACTED, rationale="No longer applicable.",
        decided_by_user_id=uuid.uuid4(), decided_by_api_client_id=None, request_id=None,
    )
    kwargs.update(overrides)
    with memory_governance_mutation_transaction(db_session):
        decision = record_memory_governance_decision(db_session, **kwargs)
    if decision_created_at is not None:
        db_session.execute(
            OrganizationalMemoryGovernanceDecision.__table__.update()
            .where(OrganizationalMemoryGovernanceDecision.id == decision.id)
            .values(created_at=decision_created_at)
        )
        db_session.commit()
        db_session.refresh(decision)
    return decision


# --- 1: organizational memory appears in normal field intelligence context -----------------------


def test_organizational_memory_appears_in_normal_field_intelligence_context(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id)

    # `as_of` intentionally omitted -- defaults to `utcnow()` at call time,
    # which is guaranteed to be at or after `OrganizationalMemory.created_at`
    # (server-derived to the real wall clock at creation, a moment ago).
    # Observed/deterministic/predictive are not asserted on here (see the
    # dedicated invariance tests below) -- only that memory is reachable.
    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")

    assert result.organizational_memory.outcome == OrganizationalMemoryOutcome.OK.value
    assert [m.memory_id for m in result.organizational_memory.items] == [memory.id]
    assert result.calculation_versions["organizational_memory"] == result.organizational_memory.calculation_version


# --- 2: organization-wide memory appears where applicable ------------------------------------------


def test_organization_wide_memory_appears_at_organization_and_site_context(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id, site_id=None)

    org_context = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    site_context = compose_field_intelligence_context(db_session, organization_id=org.id, scope="site", site_id=site.id)
    assert [m.memory_id for m in org_context.organizational_memory.items] == [memory.id]
    assert org_context.organizational_memory.items[0].applicability_basis == MemoryApplicabilityBasis.ORGANIZATION_WIDE.value
    assert [m.memory_id for m in site_context.organizational_memory.items] == [memory.id]


# --- 3: site-specific memory appears only for matching site context --------------------------------


def test_site_specific_memory_appears_only_for_matching_site_context(db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, "Site A")
    site_b = make_site(db_session, org.id, "Site B")
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id, site_id=site_a.id)

    matching = compose_field_intelligence_context(db_session, organization_id=org.id, scope="site", site_id=site_a.id)
    other = compose_field_intelligence_context(db_session, organization_id=org.id, scope="site", site_id=site_b.id)
    assert [m.memory_id for m in matching.organizational_memory.items] == [memory.id]
    assert matching.organizational_memory.items[0].applicability_basis == MemoryApplicabilityBasis.SITE_MATCH.value
    assert other.organizational_memory.items == []


# --- 4: project/site applicability respects M35B/M36 temporal association --------------------------


def test_project_scope_context_includes_memory_from_an_associated_site_only(db_session):
    org = make_org(db_session)
    site_in = make_site(db_session, org.id, "In-Project Site")
    site_out = make_site(db_session, org.id, "Outside Site")
    project = Project(organization_id=org.id, name="Test Project")
    db_session.add(project)
    db_session.commit()
    link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site_in.id,
        created_by_user_id=uuid.uuid4(), created_by_api_client_id=None,
    )
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory_in = _make_accepted_memory(db_session, org.id, decision.id, site_id=site_in.id)
    _make_accepted_memory(db_session, org.id, decision.id, site_id=site_out.id)

    result = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="organization", project_id=project.id
    )
    memory_ids = {m.memory_id for m in result.organizational_memory.items}
    assert memory_ids == {memory_in.id}
    included = next(m for m in result.organizational_memory.items if m.memory_id == memory_in.id)
    assert included.applicability_basis == MemoryApplicabilityBasis.PROJECT_SITE_MATCH.value


# --- 5: RETRACTED memory excluded -------------------------------------------------------------------


def test_retracted_memory_is_excluded_from_context(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id)
    _retract(db_session, org.id, memory.id)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    assert result.organizational_memory.items == []


# --- 6/7/8: historical as_of, memory created after as_of, no substitution of today's governance -----


def test_historical_as_of_restores_memory_active_at_that_time(db_session):
    """Worked example from the M41/M41A spec: a memory ACTIVE at `T` but
    retracted later is still included when the context is evaluated
    `as_of=T`. Mirrors `tests/test_memory_integration_service.py::
    test_memory_active_at_t_but_retracted_later_is_included_at_t`'s own
    established pattern -- `OrganizationalMemoryGovernanceDecision.
    created_at` is server-derived (not backdatable like `outcome_at`),
    so `T` is a real wall-clock instant captured strictly between the
    two calls, never an arithmetic offset. Proven here through
    `compose_field_intelligence_context()` itself, not only through
    M41's own function directly."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id)
    mid_point = datetime.now(timezone.utc)
    _retract(db_session, org.id, memory.id)  # retracted strictly after mid_point

    at_mid_point = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="organization", as_of=mid_point
    )
    assert [m.memory_id for m in at_mid_point.organizational_memory.items] == [memory.id]


def test_memory_created_after_as_of_is_excluded_from_context(db_session):
    org = make_org(db_session)
    early = AS_OF - timedelta(days=30)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    _make_accepted_memory(db_session, org.id, decision.id, memory_created_at=AS_OF + timedelta(days=1))

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=early)
    assert result.organizational_memory.items == []


def test_current_governance_is_never_substituted_for_historical_context(db_session):
    """Explicit anti-regression for the spec's own "do NOT simply use
    current-state governance for historical contexts" warning, proven
    through `compose_field_intelligence_context()`: a memory retracted
    since a historical instant must still show as included when the
    context is evaluated `as_of` a point before that retraction ever
    happened -- never today's current (now-RETRACTED) state."""
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id)
    before_retraction = datetime.now(timezone.utc)
    _retract(db_session, org.id, memory.id)  # current state is now RETRACTED

    historical = compose_field_intelligence_context(
        db_session, organization_id=org.id, scope="organization", as_of=before_retraction
    )
    current = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    assert [m.memory_id for m in historical.organizational_memory.items] == [memory.id]
    assert current.organizational_memory.items == []


# --- 9/10: provenance chain + applicability basis present -------------------------------------------


def test_context_memory_item_carries_full_provenance_and_applicability(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory = _make_accepted_memory(db_session, org.id, decision.id)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    item = result.organizational_memory.items[0]
    assert item.memory_id == memory.id
    assert item.learning_candidate_id is not None
    assert item.outcome_id is not None
    assert item.verification_id is not None
    # `site_id=None` on the fixture's own outcome -- this memory is
    # ORGANIZATION_WIDE (applicable everywhere), not a site-scoped one
    # rolling up into organization scope (`test_site_specific_memory_
    # included_at_organization_scope_rollup`, mirrored from M41's own
    # suite, covers `ORGANIZATION_SCOPE_ROLLUP` specifically).
    assert item.applicability_basis == MemoryApplicabilityBasis.ORGANIZATION_WIDE.value
    assert item.governance_status == "ACTIVE"


# --- 11-15: existing categories/calculations unchanged (the invariance requirement) ------------------


def _deterministic_content(det):
    """The substantive, computed content of an `EnterpriseIntelligenceResult`
    -- every field the M41A spec's invariance requirement actually cares
    about (indicators/trend/patterns/concentrations/anomalies/
    associations/risk/explanations/event_count/data_sufficiency).
    Deliberately excludes `provenance`/`as_of` themselves: `provenance.
    generated_at` is a real wall-clock "when was this computed" stamp
    that legitimately differs between two calls a few milliseconds
    apart, never a calculation result, so comparing it would make this
    test flaky for a reason that has nothing to do with organizational
    memory."""
    return (
        det.data_sufficiency, det.event_count, det.indicators, det.trend, det.patterns,
        det.concentrations, det.anomalies, det.associations, det.risk, det.explanations,
    )


def test_existing_categories_are_byte_identical_with_and_without_organizational_memory(db_session):
    """The M41A spec's own explicit instruction: 'Add regression tests
    demonstrating this invariant.' Composes the identical context twice
    -- once before any organizational memory exists, once after an
    ACTIVE memory is created -- and asserts observed/deterministic/
    predictive/knowledge (including deterministic.risk, trend, anomaly,
    and every other enterprise-intelligence field) are unchanged, while
    only `organizational_memory` differs."""
    org = make_org(db_session)
    anchor = datetime.now(timezone.utc)
    _seed_events(db_session, org.id, count=8, anchor=anchor)
    decision = _make_decision(db_session, org.id, anchor=anchor)

    before = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=anchor)
    assert before.organizational_memory.items == []

    # Backdated to strictly before `anchor` (rather than relying on the
    # server-derived, real-wall-clock default) so that the *same*
    # `as_of=anchor` value can be passed to both calls below -- an
    # identical `as_of` is what makes `deterministic`/`observed` (whose
    # own window boundaries are themselves computed from `as_of`)
    # genuinely byte-comparable between the two calls, not merely
    # equal-by-coincidence.
    _make_accepted_memory(db_session, org.id, decision.id, memory_created_at=anchor - timedelta(minutes=1))

    after = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=anchor)
    assert len(after.organizational_memory.items) == 1

    # 11: observed context unchanged.
    assert before.observed == after.observed
    # 12: deterministic intelligence unchanged (indicators/trend/anomaly/
    # concentration/recurrence/risk all live under `.deterministic`,
    # itself a reused `EnterpriseIntelligenceResult`).
    assert _deterministic_content(before.deterministic) == _deterministic_content(after.deterministic)
    # 13: predictive intelligence unchanged.
    assert before.predictive == after.predictive
    # 14/15: risk/trend/anomaly/signals specifically, spelled out even
    # though already covered by the content comparison above.
    assert before.deterministic.risk == after.deterministic.risk
    assert before.deterministic.trend == after.deterministic.trend
    assert before.deterministic.anomalies == after.deterministic.anomalies
    # Knowledge is independently queried (no query supplied here means
    # NOT_QUERIED either way) -- still asserted for completeness.
    assert before.knowledge == after.knowledge


def test_removing_an_organizational_memory_does_not_alter_existing_categories(db_session):
    """The reverse direction of the invariance requirement: retracting
    (removing eligibility of) a memory must not alter existing
    intelligence categories either. Both the memory's own `created_at`
    and the retraction decision's own `created_at` are explicitly
    backdated to strictly before `anchor` (mirroring `_make_accepted_
    memory`'s own `memory_created_at` override) so that the *same*
    `as_of=anchor` value can be passed to both calls below -- an
    identical `as_of` is what makes `deterministic`/`observed` (whose
    own window boundaries are themselves computed from `as_of`)
    genuinely byte-comparable between the two calls, not merely
    equal-by-coincidence."""
    org = make_org(db_session)
    anchor = datetime.now(timezone.utc)
    _seed_events(db_session, org.id, count=6, anchor=anchor)
    decision = _make_decision(db_session, org.id, anchor=anchor)
    memory = _make_accepted_memory(db_session, org.id, decision.id, memory_created_at=anchor - timedelta(minutes=2))

    with_memory = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=anchor)
    assert with_memory.organizational_memory.items

    _retract(db_session, org.id, memory.id, decision_created_at=anchor - timedelta(minutes=1))

    without_memory = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=anchor)
    assert without_memory.organizational_memory.items == []
    assert with_memory.observed == without_memory.observed
    assert _deterministic_content(with_memory.deterministic) == _deterministic_content(without_memory.deterministic)
    assert with_memory.predictive == without_memory.predictive


# --- 16: no duplicate memory integration architecture exists -----------------------------------------


def test_context_composition_reuses_m41_resolver_and_defines_no_second_one():
    """AST/source-level check: `context_composition.py`'s new
    `_organizational_memory_context()` must call `resolve_eligible_
    organizational_memories()` (M41's own function) and must not itself
    query `OrganizationalMemory`/`OrganizationalMemoryGovernanceDecision`
    directly, nor define any function whose name resembles a second
    eligibility/applicability resolver."""
    import inspect

    import app.intelligence.context_composition as module

    source = inspect.getsource(module._organizational_memory_context)
    assert "resolve_eligible_organizational_memories(" in source
    forbidden_symbols = (
        "OrganizationalMemory.",
        "OrganizationalMemoryGovernanceDecision",
        "resolve_current_memory_governance",
        "is_project_site_associated_as_of",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source, f"context_composition.py must not re-implement M41 logic ({symbol} found)"


# --- 17: no database write occurs during context composition -----------------------------------------


def test_composing_context_with_organizational_memory_never_writes_to_the_database(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    _make_accepted_memory(db_session, org.id, decision.id)

    before_count = db_session.query(OrganizationalMemory).count()
    compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    after_count = db_session.query(OrganizationalMemory).count()
    assert before_count == after_count == 1


# --- 18: no LLM/vector/embedding path exists ----------------------------------------------------------


def test_organizational_memory_section_has_no_llm_or_ml_dependency():
    import inspect

    import app.intelligence.context_composition as module

    source = inspect.getsource(module._organizational_memory_context)
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers", "sklearn", "torch", "embed")
    lowered = source.lower()
    for name in forbidden:
        assert name not in lowered, f"unexpected ML/AI-provider reference in _organizational_memory_context: {name}"


# --- 19: no automatic memory creation/acceptance/governance occurs during composition ------------------


def test_organizational_memory_section_never_references_a_mutation_function():
    import inspect

    import app.intelligence.context_composition as module

    source = inspect.getsource(module._organizational_memory_context)
    forbidden_symbols = (
        "create_organizational_memory",
        "record_memory_governance_decision",
        "create_learning_candidate",
        "record_governance_decision",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source, f"_organizational_memory_context must never reference {symbol}"


# --- 20: cross-tenant memory leakage impossible ---------------------------------------------------------


def test_context_never_leaks_another_organizations_memory(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _seed_events(db_session, org_a.id)
    _seed_events(db_session, org_b.id)
    decision_a = _make_decision(db_session, org_a.id)
    _make_accepted_memory(db_session, org_a.id, decision_a.id)

    result_b = compose_field_intelligence_context(db_session, organization_id=org_b.id, scope="organization", as_of=AS_OF)
    assert result_b.organizational_memory.items == []


# --- 25: deterministic ordering remains stable -----------------------------------------------------------


def test_context_organizational_memory_ordering_is_deterministic(db_session):
    org = make_org(db_session)
    _seed_events(db_session, org.id)
    decision = _make_decision(db_session, org.id)
    memory_1 = _make_accepted_memory(db_session, org.id, decision.id)
    memory_2 = _make_accepted_memory(db_session, org.id, decision.id)
    memory_3 = _make_accepted_memory(db_session, org.id, decision.id)

    first = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    second = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization")
    first_ids = [m.memory_id for m in first.organizational_memory.items]
    second_ids = [m.memory_id for m in second.organizational_memory.items]
    assert first_ids == second_ids == [memory_3.id, memory_2.id, memory_1.id]


# --- Failure isolation (M32's own established pattern, extended to the fifth category) -----------------


def test_organizational_memory_failure_is_isolated_and_never_blanks_other_categories(db_session, monkeypatch):
    org = make_org(db_session)
    _seed_events(db_session, org.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated organizational memory failure")

    import app.intelligence.context_composition as module

    monkeypatch.setattr(module, "resolve_eligible_organizational_memories", _boom)

    result = compose_field_intelligence_context(db_session, organization_id=org.id, scope="organization", as_of=AS_OF)
    assert result.organizational_memory.outcome == OrganizationalMemoryOutcome.UNAVAILABLE.value
    assert result.organizational_memory.unavailable_reason
    assert result.organizational_memory.items == []
    # Other categories are computed independently and remain intact.
    assert result.observed.event_count == 5
    assert result.deterministic is not None
    assert result.predictive is not None
    assert result.knowledge is not None


# --- Static architectural guards (M41A) -------------------------------------------------------------
#
# Extends the AST-based guard style already established by `tests/
# test_memory_integration_service.py` (M41) to `_organizational_memory_
# context()` itself -- the one new function context_composition.py
# gained for this milestone -- and to `context_composition.py` as a
# whole, so a future change to *any* of its five categories cannot
# quietly introduce an ML/LLM/vector dependency or a database write
# without failing a test.


def test_organizational_memory_context_never_calls_db_add_flush_or_commit():
    """AST-based (not merely grepped) check, mirroring `tests/test_
    memory_integration_service.py::test_module_never_writes_to_the_
    database`'s own established technique: parses the AST of
    `_organizational_memory_context()` itself rather than its source
    text, since a docstring may legitimately *mention* `db.add()` in
    prose while explaining why it never happens."""
    import ast
    import inspect

    import app.intelligence.context_composition as module

    tree = ast.parse(inspect.getsource(module._organizational_memory_context))
    forbidden_methods = {"add", "flush", "commit"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_methods and isinstance(node.func.value, ast.Name) and node.func.value.id == "db":
                pytest.fail(f"_organizational_memory_context must never call db.{node.func.attr}(...)")


def test_context_composition_module_has_no_ml_llm_or_vector_import():
    """Whole-module guard (not merely the new function) -- a future
    change to any of `context_composition.py`'s five categories, not
    only `organizational_memory`, must never introduce an ML/LLM/
    vector-provider dependency. Checks the module's own `import`/`from`
    lines specifically (not arbitrary prose) so a docstring explaining
    what this module does NOT do can never false-positive the check."""
    import inspect

    import app.intelligence.context_composition as module

    source = inspect.getsource(module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden = ("openai", "anthropic", "langchain", "transformers", "sentence_transformers", "torch", "faiss")
    for line in import_lines:
        lowered = line.lower()
        assert not any(name in lowered for name in forbidden), f"unexpected ML/AI-provider import: {line}"


def test_context_composition_module_never_references_memory_mutation_or_ontology_terminology_mutation():
    """A future change to `context_composition.py` must never gain the
    ability to create/govern organizational memory, accept/create a
    learning candidate, mutate the ontology, or mutate terminology
    mappings -- the same forbidden-symbol list `tests/test_memory_
    integration_service.py::test_module_does_not_reference_model_
    threshold_or_ontology_mutation` already enforces on M41's own
    module, applied here to the module M41A extended."""
    import inspect

    import app.intelligence.context_composition as module

    source = inspect.getsource(module)
    forbidden_symbols = (
        "create_organizational_memory",
        "record_memory_governance_decision",
        "create_learning_candidate",
        "record_governance_decision",
        "TerminologyMappingDecision",
        "propose_concept",
        "approve_concept",
        "train_model",
        "ModelRegistry",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source, f"context_composition.py must never reference {symbol}"
