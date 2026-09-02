"""Tests for the Real Enterprise Terminology & Ontology Calibration v0.1
pipeline: `app/models/terminology_mapping_decision.py`,
`app/services/terminology_calibration_service.py`,
`app/intelligence/terminology_calibration_adapter.py`, and
`app/services/terminology_reprocessing_service.py`.

Every fixture here is synthetic (fabricated project names, terminology
terms, and narrative strings — none derived from any real workbook); no
real enterprise data, PII, or workbook content is referenced anywhere in
this file. Requires real PostgreSQL (`@requires_postgres`, `pg_session`)
— datetime/`ingestion_time` comparisons throughout (versioning,
reprocessing's own fresh-timestamp guarantee, point-in-time checks)
follow the same rationale `tests/test_enterprise_dataset_validation.py`
already documents for why SQLite is unreliable here.
"""

from __future__ import annotations

import pytest

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_calibration_adapter import (
    CalibratedTerminologyMappingAdapter,
)
from app.intelligence.terminology_review import (
    TerminologyReviewEntry,
    TerminologyReviewStatus,
    build_terminology_review,
)
from app.models.audit_log import AuditLog
from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services import terminology_calibration_service as svc
from app.services import terminology_reprocessing_service as reproc
from app.services.authorization_service import AuthorizationError
from app.services.terminology_calibration_service import (
    TerminologyMappingDecisionNotFoundError,
    TerminologyMappingDecisionStateError,
)
from tests.intelligence_test_helpers import make_org, make_org_member
from tests.postgres_support import requires_postgres

_PII_MARKER = "Synthetic Fixture Person"  # a fabricated name, used only to prove it never leaks

# --- Shared synthetic fixtures ------------------------------------------------------------------


def _unknown_candidate_entry(source_term: str = "NearMiss", occurrence_count: int = 6) -> TerminologyReviewEntry:
    return TerminologyReviewEntry(
        domain="event_type", context=None, source_term=source_term, proposed_canonical_term=None,
        status=TerminologyReviewStatus.UNKNOWN, reason="No alias match found.", occurrence_count=occurrence_count,
        example_source_record_ids=("SYN-0001", "SYN-0002"),
    )


def _mapped_entry() -> TerminologyReviewEntry:
    return TerminologyReviewEntry(
        domain="event_type", context=None, source_term="Injury", proposed_canonical_term="INCIDENT",
        status=TerminologyReviewStatus.MAPPED, reason="Matched alias.", occurrence_count=10,
    )


def _create_candidate(db, *, organization_id, source_system="synthetic-hse-xlsx", source_term="NearMiss"):
    entries = [_unknown_candidate_entry(source_term=source_term), _mapped_entry()]
    created = svc.create_review_candidates(db, organization_id=organization_id, source_system=source_system, entries=entries)
    assert len(created) == 1  # the MAPPED entry never becomes a candidate
    return created[0]


# --- Lifecycle: UNKNOWN -> REVIEW_CANDIDATE -> PROPOSED -> APPROVED/REJECTED --------------------


@requires_postgres
def test_unknown_term_becomes_a_review_candidate_never_a_guess(pg_session):
    org = make_org(pg_session, "Calibration - Lifecycle Candidate")
    candidate = _create_candidate(pg_session, organization_id=org.id)
    assert candidate.status == "REVIEW_CANDIDATE"
    assert candidate.proposed_canonical_term is None
    assert candidate.mapping_version == 1
    assert candidate.hse_expert_review_id is not None  # queued in the existing HSE review queue too


@requires_postgres
def test_mapped_entries_never_produce_a_candidate(pg_session):
    org = make_org(pg_session, "Calibration - No Candidate For Mapped")
    created = svc.create_review_candidates(
        pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=[_mapped_entry()]
    )
    assert created == []


@requires_postgres
def test_a_genuinely_ambiguous_term_also_becomes_a_review_candidate_requiring_human_clarification(pg_session):
    """Item 12: a term with multiple plausible canonical classifications
    -- `"finding"`, a real ambiguous entry in the existing, unmodified
    alias table (`AUDIT` or `INSPECTION`) -- must surface for human
    review exactly like an UNKNOWN term, and `suggest_candidates()` must
    show every plausible candidate rather than silently picking one."""
    org = make_org(pg_session, "Calibration - Ambiguous Candidate")
    ambiguous_entry = TerminologyReviewEntry(
        domain="event_type", context=None, source_term="finding", proposed_canonical_term=None,
        status=TerminologyReviewStatus.AMBIGUOUS,
        reason="Term matches multiple plausible candidates (AUDIT, INSPECTION); not resolved automatically.",
        occurrence_count=4, example_source_record_ids=("SYN-0003",),
    )
    created = svc.create_review_candidates(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=[ambiguous_entry])
    assert len(created) == 1
    candidate = created[0]
    assert candidate.status == "REVIEW_CANDIDATE"
    assert candidate.source_term == "finding"

    suggestion = svc.suggest_candidates(candidate.domain, candidate.context, candidate.source_term)
    assert suggestion.outcome.value == "AMBIGUOUS"
    assert set(suggestion.candidates) == {"AUDIT", "INSPECTION"}
    # Never auto-selected -- a human still has to explicitly propose one.
    assert candidate.proposed_canonical_term is None


@requires_postgres
def test_creating_candidates_twice_never_duplicates_or_mutates_an_existing_row(pg_session):
    org = make_org(pg_session, "Calibration - No Duplicate Candidates")
    first = _create_candidate(pg_session, organization_id=org.id)
    admin = make_org_member(pg_session, org.id)
    svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=first.id, proposed_canonical_term="NEAR_MISS",
        rationale="Matches near-miss domain semantics.", acting_user_id=admin.id,
    )
    # Re-running candidate creation over the same batch must never touch the in-flight PROPOSED row.
    entries = [_unknown_candidate_entry(), _mapped_entry()]
    second = svc.create_review_candidates(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=entries)
    assert second == []
    pg_session.refresh(first)
    assert first.status == "PROPOSED"


@requires_postgres
def test_pending_to_approved_lifecycle(pg_session):
    org = make_org(pg_session, "Calibration - Approve Lifecycle")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)

    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="Matches near-miss domain semantics.", acting_user_id=admin.id,
    )
    assert proposed.status == "PROPOSED"
    assert proposed.proposed_by_user_id == admin.id
    assert proposed.proposed_at is not None

    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)
    assert approved.status == "APPROVED"
    assert approved.reviewer_user_id == admin.id
    assert approved.decided_at is not None
    assert approved.is_eligible_for_canonical_classification is True


@requires_postgres
def test_pending_to_rejected_lifecycle(pg_session):
    org = make_org(pg_session, "Calibration - Reject Lifecycle")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)

    rejected = svc.reject_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, acting_user_id=admin.id,
        reason="Term is too ambiguous across this source's own projects to resolve.",
    )
    assert rejected.status == "REJECTED"
    assert rejected.is_eligible_for_canonical_classification is False
    assert "REJECTED" in rejected.rationale


@requires_postgres
def test_approving_without_a_proposed_term_is_refused(pg_session):
    org = make_org(pg_session, "Calibration - Refuse Empty Approval")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term=None,
        rationale="Insufficient confidence to propose anything -- preferable to guessing.", acting_user_id=admin.id,
    )
    with pytest.raises(TerminologyMappingDecisionStateError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)


@requires_postgres
def test_a_review_candidate_can_be_approved_only_after_being_proposed(pg_session):
    org = make_org(pg_session, "Calibration - Cannot Approve Raw Candidate")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    with pytest.raises(TerminologyMappingDecisionStateError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=candidate.id, acting_user_id=admin.id)


@requires_postgres
def test_a_terminal_decision_is_frozen_forever(pg_session):
    org = make_org(pg_session, "Calibration - Terminal Frozen")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    with pytest.raises(TerminologyMappingDecisionStateError):
        svc.propose_mapping(
            pg_session, organization_id=org.id, decision_id=approved.id, proposed_canonical_term="SOMETHING_ELSE",
            rationale="r", acting_user_id=admin.id,
        )
    with pytest.raises(TerminologyMappingDecisionStateError):
        svc.reject_mapping(pg_session, organization_id=org.id, decision_id=approved.id, acting_user_id=admin.id, reason="r")


# --- Versioning (item 8) -------------------------------------------------------------------------


@requires_postgres
def test_changing_an_approved_mapping_opens_a_new_version_never_overwrites_the_old_one(pg_session):
    org = make_org(pg_session, "Calibration - Versioning")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="v1 rationale", acting_user_id=admin.id,
    )
    approved_v1 = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)
    assert approved_v1.mapping_version == 1

    v2_candidate = svc.open_new_version(pg_session, organization_id=org.id, prior_decision_id=approved_v1.id, acting_user_id=admin.id)
    assert v2_candidate.mapping_version == 2
    assert v2_candidate.status == "REVIEW_CANDIDATE"

    # get_active_mapping still resolves to v1 until v2 is itself approved.
    still_active = svc.get_active_mapping(
        pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", domain="event_type", context=None,
        source_term="NearMiss",
    )
    assert still_active.mapping_version == 1

    proposed_v2 = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=v2_candidate.id, proposed_canonical_term="NEAR_MISS_REFINED",
        rationale="v2 rationale", acting_user_id=admin.id,
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed_v2.id, acting_user_id=admin.id)

    now_active = svc.get_active_mapping(
        pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", domain="event_type", context=None,
        source_term="NearMiss",
    )
    assert now_active.mapping_version == 2
    assert now_active.proposed_canonical_term == "NEAR_MISS_REFINED"

    # The v1 row is completely untouched -- full history preserved.
    pg_session.refresh(approved_v1)
    assert approved_v1.status == "APPROVED"
    assert approved_v1.proposed_canonical_term == "NEAR_MISS"
    assert approved_v1.rationale == "v1 rationale"


@requires_postgres
def test_a_new_version_can_only_be_opened_from_a_terminal_decision(pg_session):
    org = make_org(pg_session, "Calibration - New Version Requires Terminal")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    with pytest.raises(TerminologyMappingDecisionStateError):
        svc.open_new_version(pg_session, organization_id=org.id, prior_decision_id=candidate.id, acting_user_id=admin.id)


# --- Tenant / source isolation (item 7) -----------------------------------------------------------


@requires_postgres
def test_an_approved_mapping_in_one_organization_never_affects_another(pg_session):
    org_a = make_org(pg_session, "Calibration - Tenant A")
    org_b = make_org(pg_session, "Calibration - Tenant B")
    admin_a = make_org_member(pg_session, org_a.id)

    candidate_a = _create_candidate(pg_session, organization_id=org_a.id)
    proposed_a = svc.propose_mapping(
        pg_session, organization_id=org_a.id, decision_id=candidate_a.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin_a.id,
    )
    svc.approve_mapping(pg_session, organization_id=org_a.id, decision_id=proposed_a.id, acting_user_id=admin_a.id)

    active_in_b = svc.get_active_mapping(
        pg_session, organization_id=org_b.id, source_system="synthetic-hse-xlsx", domain="event_type", context=None,
        source_term="NearMiss",
    )
    assert active_in_b is None

    # An organization B admin cannot even reach org A's decision by id.
    admin_b = make_org_member(pg_session, org_b.id)
    with pytest.raises(TerminologyMappingDecisionNotFoundError):
        svc.approve_mapping(pg_session, organization_id=org_b.id, decision_id=proposed_a.id, acting_user_id=admin_b.id)


@requires_postgres
def test_an_approved_mapping_on_one_source_system_never_affects_a_different_source_system(pg_session):
    org = make_org(pg_session, "Calibration - Source Isolation")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id, source_system="alm-hse-xlsx")
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    active_on_other_source = svc.get_active_mapping(
        pg_session, organization_id=org.id, source_system="another-system", domain="event_type", context=None,
        source_term="NearMiss",
    )
    assert active_on_other_source is None
    active_on_original_source = svc.get_active_mapping(
        pg_session, organization_id=org.id, source_system="alm-hse-xlsx", domain="event_type", context=None,
        source_term="NearMiss",
    )
    assert active_on_original_source is not None


# --- Authorization (item 9) -----------------------------------------------------------------------


@requires_postgres
def test_a_viewer_cannot_propose_approve_or_reject(pg_session):
    from app.services.permissions import OrganizationRole

    org = make_org(pg_session, "Calibration - Viewer Cannot Modify")
    viewer = make_org_member(pg_session, org.id, role=OrganizationRole.VIEWER)
    candidate = _create_candidate(pg_session, organization_id=org.id)

    with pytest.raises(AuthorizationError):
        svc.propose_mapping(
            pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
            rationale="r", acting_user_id=viewer.id,
        )

    # Get a proposal in via an admin so approve/reject can be attempted by the viewer.
    admin = make_org_member(pg_session, org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    with pytest.raises(AuthorizationError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=viewer.id)
    with pytest.raises(AuthorizationError):
        svc.reject_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=viewer.id, reason="r")


@requires_postgres
def test_a_user_with_no_membership_in_the_organization_cannot_approve(pg_session):
    org = make_org(pg_session, "Calibration - Unauthorized")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )

    stranger_org = make_org(pg_session, "Calibration - Stranger Org")
    stranger = make_org_member(pg_session, stranger_org.id)  # a real user, but no membership in `org`
    with pytest.raises(AuthorizationError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=stranger.id)


@requires_postgres
def test_hse_analyst_and_hse_manager_also_lack_governance_manage(pg_session):
    """`GOVERNANCE_MANAGE` is withheld from every role except ORG_ADMIN in
    `ROLE_PERMISSIONS` -- verified directly here rather than assumed,
    since this milestone's own approval gate depends on it."""
    from app.services.permissions import OrganizationRole

    org = make_org(pg_session, "Calibration - Non-Admin Roles")
    candidate = _create_candidate(pg_session, organization_id=org.id)
    admin = make_org_member(pg_session, org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    for role in (OrganizationRole.HSE_MANAGER, OrganizationRole.HSE_ANALYST, OrganizationRole.HSE_USER):
        member = make_org_member(pg_session, org.id, role=role, name=f"member-{role.value}")
        with pytest.raises(AuthorizationError):
            svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=member.id)


# --- Data quality: only APPROVED is eligible (item 11) --------------------------------------------


@requires_postgres
def test_unknown_ambiguous_pending_and_rejected_all_remain_quarantined_at_ingestion(pg_session):
    org = make_org(pg_session, "Calibration - Data Quality Gate")
    admin = make_org_member(pg_session, org.id)

    # UNKNOWN -- no decision at all.
    unknown_payload = [RawSafetyEventPayload(
        event_type="NearMiss", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx",
        source_record_id="UNK-1",
    )]

    # AMBIGUOUS -- a real ambiguous term from the existing, unmodified alias table.
    ambiguous_payload = [RawSafetyEventPayload(
        event_type="finding", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx",
        source_record_id="AMB-1",
    )]

    empty_index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    assert empty_index == {}
    adapter = CalibratedTerminologyMappingAdapter(active_mappings=empty_index)

    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id, payloads=unknown_payload + ambiguous_payload, adapter=adapter, source_id=None,
    )
    assert {r.quality_state for r in result.records} == {"QUARANTINED"}

    # PENDING (REVIEW_CANDIDATE, then PROPOSED) -- still not eligible.
    candidate = _create_candidate(pg_session, organization_id=org.id, source_term="NearMiss")
    still_empty_index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    assert still_empty_index == {}  # a REVIEW_CANDIDATE is never in the active index

    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    proposed_index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    assert proposed_index == {}  # a PROPOSED-but-not-approved mapping is never in the active index either

    result2 = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-05T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="PEND-1",
        )],
        adapter=CalibratedTerminologyMappingAdapter(active_mappings=proposed_index), source_id=None,
    )
    assert result2.records[0].quality_state == "QUARANTINED"

    # REJECTED -- still not eligible, permanently for this version.
    rejected = svc.reject_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id, reason="Not resolvable.")
    rejected_index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    assert rejected_index == {}
    result3 = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-06T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="REJ-1",
        )],
        adapter=CalibratedTerminologyMappingAdapter(active_mappings=rejected_index), source_id=None,
    )
    assert result3.records[0].quality_state == "QUARANTINED"
    assert rejected.is_eligible_for_canonical_classification is False


@requires_postgres
def test_an_approved_mapping_makes_a_future_ingestion_eligible(pg_session):
    org = make_org(pg_session, "Calibration - Approved Eligible")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    adapter = CalibratedTerminologyMappingAdapter(active_mappings=index)
    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-10T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="OK-1",
        )],
        adapter=adapter, source_id=None,
    )
    assert result.records[0].quality_state == "VALID"
    event = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "OK-1").one()
    assert event.event_type == "NEAR_MISS"
    assert event.attributes["_terminology_calibration"]["event_type_resolved_via_calibration"] == "NearMiss"


# --- Explicit historical reprocessing (item 13) ----------------------------------------------------


@requires_postgres
def test_approval_alone_never_rewrites_already_quarantined_historical_records(pg_session):
    org = make_org(pg_session, "Calibration - No Auto Rewrite")
    admin = make_org_member(pg_session, org.id)
    unknown_index = {}
    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="HIST-1",
        )],
        adapter=CalibratedTerminologyMappingAdapter(active_mappings=unknown_index), source_id=None,
    )
    assert result.records[0].quality_state == "QUARANTINED"

    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    pg_session.expire_all()
    still = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "HIST-1").one()
    assert still.data_quality_status == "QUARANTINED"
    assert still.event_type != "NEAR_MISS"


@requires_postgres
def test_explicit_reprocessing_updates_matching_historical_records_with_a_fresh_ingestion_time(pg_session):
    org = make_org(pg_session, "Calibration - Explicit Reprocessing")
    admin = make_org_member(pg_session, org.id)
    result = enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[
            RawSafetyEventPayload(event_type="NearMiss", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx", source_record_id="REPRO-1"),
            RawSafetyEventPayload(event_type="Injury", event_time="2026-06-02T00:00:00Z", source_system="synthetic-hse-xlsx", source_record_id="REPRO-2"),
        ],
        adapter=CalibratedTerminologyMappingAdapter(), source_id=None,
    )
    assert {r.quality_state for r in result.records} == {"QUARANTINED", "VALID"}

    before = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "REPRO-1").one()
    ingestion_time_before = before.ingestion_time

    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    repro_result = reproc.reprocess_quarantined_records(
        pg_session, organization_id=org.id, decision_id=approved.id, acting_user_id=admin.id
    )
    assert repro_result.records_examined == 1
    assert repro_result.records_updated == 1
    assert repro_result.updated_event_ids == [before.id]

    pg_session.expire_all()
    after = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "REPRO-1").one()
    assert after.event_type == "NEAR_MISS"
    assert after.data_quality_status == "VALID"
    assert after.ingestion_time > ingestion_time_before
    # source_value provenance is never rewritten -- the raw term as received is preserved.
    assert after.source_value["event_type"] == "NearMiss"

    # The unrelated INCIDENT record is untouched.
    other = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "REPRO-2").one()
    assert other.event_type == "INCIDENT"


@requires_postgres
def test_reprocessing_requires_an_approved_decision(pg_session):
    org = make_org(pg_session, "Calibration - Reprocessing Requires Approved")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    with pytest.raises(reproc.ReprocessingRequiresApprovedDecisionError):
        reproc.reprocess_quarantined_records(pg_session, organization_id=org.id, decision_id=candidate.id, acting_user_id=admin.id)


@requires_postgres
def test_reprocessing_is_tenant_and_source_scoped(pg_session):
    org_a = make_org(pg_session, "Calibration - Reprocessing Tenant A")
    org_b = make_org(pg_session, "Calibration - Reprocessing Tenant B")
    admin_a = make_org_member(pg_session, org_a.id)
    admin_b = make_org_member(pg_session, org_b.id)

    # Same term, same source_system name, but genuinely different organizations and different records.
    for org in (org_a, org_b):
        enterprise_ingestion_service.ingest_batch(
            pg_session, organization_id=org.id,
            payloads=[RawSafetyEventPayload(
                event_type="NearMiss", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx",
                source_record_id=f"TENANT-{org.id}",
            )],
            adapter=CalibratedTerminologyMappingAdapter(), source_id=None,
        )

    candidate_a = _create_candidate(pg_session, organization_id=org_a.id)
    proposed_a = svc.propose_mapping(
        pg_session, organization_id=org_a.id, decision_id=candidate_a.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin_a.id,
    )
    approved_a = svc.approve_mapping(pg_session, organization_id=org_a.id, decision_id=proposed_a.id, acting_user_id=admin_a.id)

    # Org B's admin cannot use org A's decision id to reprocess org B's own data.
    with pytest.raises(ValueError):
        reproc.reprocess_quarantined_records(pg_session, organization_id=org_b.id, decision_id=approved_a.id, acting_user_id=admin_b.id)

    repro_result = reproc.reprocess_quarantined_records(
        pg_session, organization_id=org_a.id, decision_id=approved_a.id, acting_user_id=admin_a.id
    )
    assert repro_result.records_updated == 1

    pg_session.expire_all()
    org_b_event = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == f"TENANT-{org_b.id}").one()
    assert org_b_event.data_quality_status == "QUARANTINED"  # never touched by org A's reprocessing


@requires_postgres
def test_reprocessing_an_unsupported_domain_is_refused(pg_session):
    org = make_org(pg_session, "Calibration - Unsupported Domain")
    admin = make_org_member(pg_session, org.id)
    entry = TerminologyReviewEntry(
        domain="training_status", context="TRAINING", source_term="Lapsed", proposed_canonical_term=None,
        status=TerminologyReviewStatus.UNKNOWN, reason="No alias match.", occurrence_count=1,
    )
    created = svc.create_review_candidates(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=[entry])
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=created[0].id, proposed_canonical_term="OVERDUE",
        rationale="r", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)
    with pytest.raises(reproc.ReprocessingNotSupportedError):
        reproc.reprocess_quarantined_records(pg_session, organization_id=org.id, decision_id=approved.id, acting_user_id=admin.id)


# --- Audit logging (item 15) -----------------------------------------------------------------------


@requires_postgres
def test_every_lifecycle_transition_is_audited(pg_session):
    org = make_org(pg_session, "Calibration - Audit Logging")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)
    svc.open_new_version(pg_session, organization_id=org.id, prior_decision_id=approved.id, acting_user_id=admin.id)
    reproc.reprocess_quarantined_records(pg_session, organization_id=org.id, decision_id=approved.id, acting_user_id=admin.id)

    actions = {log.action for log in pg_session.query(AuditLog).filter(AuditLog.organization_id == org.id).all()}
    assert "TERMINOLOGY_MAPPING_CANDIDATE_CREATED" in actions
    assert "TERMINOLOGY_MAPPING_PROPOSED" in actions
    assert "TERMINOLOGY_MAPPING_APPROVED" in actions
    assert "TERMINOLOGY_MAPPING_NEW_VERSION_OPENED" in actions
    assert "TERMINOLOGY_HISTORICAL_REPROCESSING_APPLIED" in actions


# --- Provenance (item 14) -------------------------------------------------------------------------


@requires_postgres
def test_an_approved_mapping_is_traceable_from_the_canonical_event_back_to_its_decision(pg_session):
    org = make_org(pg_session, "Calibration - Provenance")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)

    index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")
    enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-10T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="PROV-1",
        )],
        adapter=CalibratedTerminologyMappingAdapter(active_mappings=index), source_id=None,
    )
    event = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "PROV-1").one()

    # Canonical event -> which raw term was resolved via calibration (never silently indistinguishable).
    assert event.attributes["_terminology_calibration"]["event_type_resolved_via_calibration"] == "NearMiss"
    # That raw term -> the exact decision that approved it, independently re-queryable.
    decision = pg_session.query(TerminologyMappingDecision).filter(
        TerminologyMappingDecision.organization_id == org.id,
        TerminologyMappingDecision.source_term == event.attributes["_terminology_calibration"]["event_type_resolved_via_calibration"],
        TerminologyMappingDecision.status == "APPROVED",
    ).one()
    assert decision.id == approved.id
    assert decision.proposed_canonical_term == event.event_type

    # Feature/intelligence provenance is unaffected -- this is a normal, valid SafetyEvent from here on.
    from app.intelligence.temporal import events_as_of
    visible = pg_session.execute(events_as_of(organization_id=org.id, as_of=event.ingestion_time)).scalars().all()
    assert any(e.id == event.id for e in visible)


# --- Reproducibility --------------------------------------------------------------------------------


@requires_postgres
def test_same_input_and_mapping_version_produce_the_same_classification(pg_session):
    org = make_org(pg_session, "Calibration - Reproducibility")
    admin = make_org_member(pg_session, org.id)
    candidate = _create_candidate(pg_session, organization_id=org.id)
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="r", acting_user_id=admin.id,
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id)
    index = svc.build_active_mapping_index(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx")

    results = []
    for i in range(3):
        result = enterprise_ingestion_service.ingest_batch(
            pg_session, organization_id=org.id,
            payloads=[RawSafetyEventPayload(
                event_type="NearMiss", event_time="2026-06-10T00:00:00Z", source_system="synthetic-hse-xlsx",
                source_record_id=f"REPRO-DET-{i}",
            )],
            adapter=CalibratedTerminologyMappingAdapter(active_mappings=index), source_id=None,
        )
        results.append(result.records[0].quality_state)
    assert results == ["VALID", "VALID", "VALID"]

    events = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id.like("REPRO-DET-%")).all()
    assert {e.event_type for e in events} == {"NEAR_MISS"}


# --- PII (item 21 / testing requirement) -------------------------------------------------------------


@requires_postgres
def test_terminology_review_never_requires_or_exposes_pii(pg_session):
    """A terminology decision needs only the term itself, an occurrence
    count, and internal document ids -- never a worker's name or a
    narrative. Verified by construction: a payload carrying a fabricated
    personal name in its narrative fields never causes that name to
    appear anywhere on the resulting TerminologyMappingDecision."""
    org = make_org(pg_session, "Calibration - PII Exclusion")
    admin = make_org_member(pg_session, org.id)

    payloads = [
        RawSafetyEventPayload(
            event_type="NearMiss", event_time="2026-06-01T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="PII-1", description=f"Synthetic narrative mentioning {_PII_MARKER}.",
            attributes={"PeopleInvolved": _PII_MARKER},
        ),
    ]
    entries = build_terminology_review(payloads)
    created = svc.create_review_candidates(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=entries)
    candidate = created[0]

    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=candidate.id, proposed_canonical_term="NEAR_MISS",
        rationale="Matches near-miss domain semantics.", acting_user_id=admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=admin.id, notes="Reviewed.")

    import json

    serialized = json.dumps(
        {
            "source_term": approved.source_term, "normalized_term": approved.normalized_term,
            "proposed_canonical_term": approved.proposed_canonical_term, "rationale": approved.rationale,
            "provenance": approved.provenance, "example_source_record_ids": approved.example_source_record_ids,
        },
        default=str,
    )
    assert _PII_MARKER not in serialized


# --- Model-level lifecycle helper properties (no DB needed) -----------------------------------------


def test_status_helper_properties_without_a_database():
    from app.models.terminology_mapping_decision import (
        TerminologyMappingDecision,
        TerminologyMappingDecisionStatus,
    )

    candidate = TerminologyMappingDecision(status=TerminologyMappingDecisionStatus.REVIEW_CANDIDATE)
    proposed = TerminologyMappingDecision(status=TerminologyMappingDecisionStatus.PROPOSED)
    approved = TerminologyMappingDecision(status=TerminologyMappingDecisionStatus.APPROVED)
    rejected = TerminologyMappingDecision(status=TerminologyMappingDecisionStatus.REJECTED)

    assert candidate.is_pending and not candidate.is_terminal and not candidate.is_eligible_for_canonical_classification
    assert proposed.is_pending and not proposed.is_terminal and not proposed.is_eligible_for_canonical_classification
    assert approved.is_terminal and not approved.is_pending and approved.is_eligible_for_canonical_classification
    assert rejected.is_terminal and not rejected.is_pending and not rejected.is_eligible_for_canonical_classification
