"""Tests for the durable terminology decision artifact and its apply
mechanism (`app/services/terminology_decision_artifact_service.py`) --
Terminology Calibration v0.1 corrective commit, blocker 1.

The artifact itself (`backend/config/real_enterprise_terminology_decisions_v1.json`)
is real, committed, non-synthetic content -- but it contains only
terminology terms and occurrence counts already public in
`docs/REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`, never a real
record ID, name, narrative, email, or phone number, and never a real
database UUID (decision IDs are generated fresh by `TerminologyMappingDecision`
every time the artifact is applied). Every test here applies the real
artifact against a synthetic test organization -- never the real
workbook, never the throwaway database from the prior milestone's own
execution. Requires real PostgreSQL (`@requires_postgres`, `pg_session`).
"""

from __future__ import annotations

import json

import pytest

from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services.authorization_service import AuthorizationError
from app.services.terminology_decision_artifact_service import (
    DEFAULT_ARTIFACT_PATH,
    TerminologyDecisionArtifactConflictError,
    TerminologyDecisionArtifactFormatError,
    apply_terminology_decision_artifact,
)
from tests.intelligence_test_helpers import make_org, make_org_member
from tests.postgres_support import requires_postgres

_PII_MARKERS = ("Emmanuel", "Inwon", "@gmail", "@yahoo", "+1", "+44", "+971")


# --- The artifact file itself (no database needed) -----------------------------------------------


def test_the_artifact_file_exists_and_is_valid_json():
    assert DEFAULT_ARTIFACT_PATH.exists(), f"missing {DEFAULT_ARTIFACT_PATH}"
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["source_system"] == "alm-hse-xlsx"
    assert isinstance(data["decisions"], list)


def test_the_artifact_contains_exactly_18_decisions():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["decisions"]) == 18


def test_the_artifact_contains_exactly_3_approved_decisions():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    approved = [d for d in data["decisions"] if d["decision"] == "APPROVED"]
    assert len(approved) == 3
    assert {d["source_term"] for d in approved} == {"NearMiss", "PropertyDamage", "VehicleAccident"}


def test_the_artifact_contains_exactly_15_rejected_decisions():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    rejected = [d for d in data["decisions"] if d["decision"] == "REJECTED"]
    assert len(rejected) == 15


def test_the_three_approved_incident_decisions_contain_the_correct_compound_subtype():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by_term = {d["source_term"]: d for d in data["decisions"] if d["decision"] == "APPROVED"}
    assert by_term["NearMiss"]["canonical_event_type"] == "INCIDENT"
    assert by_term["NearMiss"]["target_event_subtype"] == "NEAR_MISS"
    assert by_term["PropertyDamage"]["canonical_event_type"] == "INCIDENT"
    assert by_term["PropertyDamage"]["target_event_subtype"] == "PROPERTY_DAMAGE"
    assert by_term["VehicleAccident"]["canonical_event_type"] == "INCIDENT"
    assert by_term["VehicleAccident"]["target_event_subtype"] == "VEHICLE_INCIDENT"
    for d in by_term.values():
        assert d["domain"] == "event_type"
        assert d["context"] is None


def test_all_11_observation_terms_are_rejected():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    observation_terms = [d for d in data["decisions"] if d["domain"] == "event_subtype" and d["context"] == "OBSERVATION"]
    assert len(observation_terms) == 11
    assert all(d["decision"] == "REJECTED" for d in observation_terms)


def test_ppe_compliance_is_rejected_with_the_documented_rationale():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    ppe = next(d for d in data["decisions"] if d["source_term"] == "PPE Compliance")
    assert ppe["decision"] == "REJECTED"
    assert ppe["domain"] == "event_subtype"
    assert ppe["context"] == "OBSERVATION"
    assert ppe["canonical_event_type"] is None
    rationale = ppe["rationale"]
    assert "PPE_ISSUE is not an exact semantic equivalent" in rationale
    assert "broader observation topic" in rationale.lower() or "broader" in rationale.lower()


def test_the_two_others_decisions_remain_independently_scoped_in_the_artifact():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    others = [d for d in data["decisions"] if d["source_term"] == "Others"]
    assert len(others) == 2
    domains = {(d["domain"], d["context"]) for d in others}
    assert domains == {("event_type", None), ("event_subtype", "OBSERVATION")}


def test_the_artifact_contains_no_real_record_ids_or_pii():
    raw = DEFAULT_ARTIFACT_PATH.read_text(encoding="utf-8")
    for marker in _PII_MARKERS:
        assert marker not in raw
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # No field anywhere resembling a real per-record identifier
    # (source_record_id, document number, batch id, ...).
    serialized = json.dumps(data)
    for forbidden_key in ("source_record_id", "document_no", "example_source_record_ids", "batch_id"):
        assert forbidden_key not in serialized


def test_the_artifact_never_hardcodes_a_decision_uuid():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    serialized = json.dumps(data)
    # A UUID would appear as a 36-char hyphenated hex string; the only
    # "id"-shaped field in the artifact is its own non-UUID artifact_id.
    import re
    uuid_pattern = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    assert not uuid_pattern.search(serialized)


# --- Applying the artifact (requires PostgreSQL) --------------------------------------------------


@requires_postgres
def test_applying_the_artifact_creates_the_expected_governed_decisions(pg_session):
    org = make_org(pg_session, "Artifact - Apply")
    admin = make_org_member(pg_session, org.id)

    result = apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)
    assert result.total_in_artifact == 18
    assert result.created_new == 18
    assert result.approved == 3
    assert result.rejected == 15
    assert result.already_satisfied == 0

    decisions = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.organization_id == org.id).all()
    assert len(decisions) == 18
    assert {d.status for d in decisions} == {"APPROVED", "REJECTED"}  # none left pending

    near_miss = next(d for d in decisions if d.source_term == "NearMiss")
    assert near_miss.status == "APPROVED"
    assert near_miss.proposed_canonical_term == "INCIDENT"
    assert near_miss.provenance["target_event_subtype"] == "NEAR_MISS"
    assert near_miss.mapping_version == 1


@requires_postgres
def test_applying_the_artifact_twice_does_not_duplicate_decisions(pg_session):
    org = make_org(pg_session, "Artifact - Idempotent")
    admin = make_org_member(pg_session, org.id)

    apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)
    result2 = apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)

    assert result2.created_new == 0
    assert result2.approved == 0
    assert result2.rejected == 0
    assert result2.already_satisfied == 18

    count = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.organization_id == org.id).count()
    assert count == 18  # never 36


@requires_postgres
def test_existing_terminal_decisions_are_not_silently_overwritten(pg_session):
    """A terminal decision that CONFLICTS with what the artifact now
    declares must raise loudly, never be silently corrected."""
    org = make_org(pg_session, "Artifact - No Silent Overwrite")
    admin = make_org_member(pg_session, org.id)
    apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)

    near_miss = pg_session.query(TerminologyMappingDecision).filter(
        TerminologyMappingDecision.organization_id == org.id, TerminologyMappingDecision.source_term == "NearMiss",
    ).one()
    near_miss.provenance = {**(near_miss.provenance or {}), "target_event_subtype": "SOMETHING_ELSE"}
    pg_session.add(near_miss)
    pg_session.commit()

    with pytest.raises(TerminologyDecisionArtifactConflictError):
        apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)

    pg_session.expire_all()
    unchanged = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.id == near_miss.id).one()
    assert unchanged.provenance["target_event_subtype"] == "SOMETHING_ELSE"  # never silently corrected


@requires_postgres
def test_a_rejected_decision_is_never_flipped_to_approved_by_reapplication(pg_session):
    org = make_org(pg_session, "Artifact - Never Reject-To-Approve")
    admin = make_org_member(pg_session, org.id)
    apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)

    fire = pg_session.query(TerminologyMappingDecision).filter(
        TerminologyMappingDecision.organization_id == org.id, TerminologyMappingDecision.source_term == "FireIncident",
    ).one()
    assert fire.status == "REJECTED"

    apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)
    pg_session.expire_all()
    still_rejected = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.id == fire.id).one()
    assert still_rejected.status == "REJECTED"


@requires_postgres
def test_applying_the_artifact_never_automatically_reprocesses_records(pg_session):
    org = make_org(pg_session, "Artifact - Never Reprocesses")
    admin = make_org_member(pg_session, org.id)
    apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id)

    events = pg_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org.id).count()
    assert events == 0  # applying the artifact touches only TerminologyMappingDecision rows


@requires_postgres
def test_applying_the_artifact_requires_governance_manage(pg_session):
    org = make_org(pg_session, "Artifact - Authorization Boundary")
    from app.services.permissions import OrganizationRole
    viewer = make_org_member(pg_session, org.id, role=OrganizationRole.VIEWER)

    with pytest.raises(AuthorizationError):
        apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=viewer.id)

    count = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.organization_id == org.id).count()
    assert count == 0  # nothing created by the refused attempt


@requires_postgres
def test_applying_the_artifact_is_tenant_scoped(pg_session):
    org_a = make_org(pg_session, "Artifact - Tenant A")
    org_b = make_org(pg_session, "Artifact - Tenant B")
    admin_a = make_org_member(pg_session, org_a.id)

    apply_terminology_decision_artifact(pg_session, organization_id=org_a.id, acting_user_id=admin_a.id)

    count_b = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.organization_id == org_b.id).count()
    assert count_b == 0  # org A's application never touches org B


@requires_postgres
def test_a_malformed_artifact_file_fails_loudly(pg_session, tmp_path):
    org = make_org(pg_session, "Artifact - Malformed File")
    admin = make_org_member(pg_session, org.id)

    bad_path = tmp_path / "bad_artifact.json"
    bad_path.write_text(json.dumps({"source_system": "x", "decisions": [{"source_term": "X"}]}))  # missing keys

    with pytest.raises(TerminologyDecisionArtifactFormatError):
        apply_terminology_decision_artifact(pg_session, organization_id=org.id, acting_user_id=admin.id, artifact_path=bad_path)
