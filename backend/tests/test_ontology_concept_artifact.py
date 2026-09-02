"""Tests for the durable ontology concept artifact and its apply
mechanism (`app/services/ontology_concept_artifact_service.py`) -- SIE
Enterprise Ontology & Data Model Expansion v0.1.

The artifact itself (`backend/config/enterprise_ontology_concepts_v1.json`)
is real, committed, non-synthetic content -- but it contains only
canonical-concept definitions, evidence counts already public in
`docs/REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`, and general
justification text -- never a real record ID, name, narrative, email,
phone number, or real database UUID. Every test applies the real
artifact against a synthetic platform-admin identity -- never the real
workbook. Requires real PostgreSQL (`@requires_postgres`, `pg_session`).
"""

from __future__ import annotations

import json
import re

import pytest

from app.models.ontology_concept import OntologyConcept
from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services.authorization_service import AuthorizationError
from app.services.ontology_concept_artifact_service import (
    DEFAULT_ARTIFACT_PATH,
    OntologyConceptArtifactFormatError,
    apply_ontology_concept_artifact,
)
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_platform_admin_user,
)
from tests.postgres_support import requires_postgres

_PII_MARKERS = ("Emmanuel", "Inwon", "@gmail", "@yahoo")
_UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# --- The artifact file itself (no database needed) -----------------------------------------------


def test_the_artifact_file_exists_and_is_valid_json():
    assert DEFAULT_ARTIFACT_PATH.exists(), f"missing {DEFAULT_ARTIFACT_PATH}"
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["ontology_version"] == 1
    assert isinstance(data["concepts"], list)


def test_the_artifact_documents_exactly_the_15_rejected_terminology_gap_terms():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["concepts"]) == 15


def test_the_artifact_contains_exactly_10_approved_concepts():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    approved = [c for c in data["concepts"] if c["decision"] == "APPROVED"]
    assert len(approved) == 10
    for c in approved:
        assert c["concept_key"] is not None


def test_the_artifact_contains_exactly_5_documented_non_concepts():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    rejected = [c for c in data["concepts"] if c["decision"] == "REJECTED"]
    assert len(rejected) == 5
    for c in rejected:
        assert c["concept_key"] is None


def test_ppe_compliance_is_approved_as_an_observation_topic_not_an_event_subtype():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    ppe = next(c for c in data["concepts"] if c["concept_key"] == "PPE_COMPLIANCE")
    assert ppe["layer"] == "observation_topic"
    assert ppe["parent_domain"] == "OBSERVATION"
    assert ppe["decision"] == "APPROVED"


def test_the_artifact_never_proposes_a_cross_domain_concept():
    """Every APPROVED entry's parent_domain must be a real SafetyEventType
    and concept_key must never collide with a top-level type when
    layer=event_subtype -- the artifact itself must already respect the
    ontology boundary rule, not merely rely on the service to catch it."""
    from app.intelligence.enums import SafetyEventType

    valid_types = {t.value for t in SafetyEventType}
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["concepts"]:
        if c["decision"] != "APPROVED":
            continue
        assert c["parent_domain"] in valid_types
        if c["layer"] == "event_subtype":
            assert c["concept_key"] not in valid_types


def test_the_artifact_contains_no_real_record_ids_or_pii():
    raw = DEFAULT_ARTIFACT_PATH.read_text(encoding="utf-8")
    for marker in _PII_MARKERS:
        assert marker not in raw
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    serialized = json.dumps(data)
    for forbidden_key in ("source_record_id", "document_no", "example_source_record_ids", "batch_id"):
        assert forbidden_key not in serialized


def test_the_artifact_never_hardcodes_a_concept_uuid():
    with open(DEFAULT_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert not _UUID_PATTERN.search(json.dumps(data))


# --- Applying the artifact (requires PostgreSQL) --------------------------------------------------


@requires_postgres
def test_applying_the_artifact_creates_exactly_10_approved_concepts(pg_session):
    admin = make_platform_admin_user(pg_session)
    result = apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)
    assert result.total_in_artifact == 15
    assert result.approved_new == 10
    assert result.documented_no_concept == 5
    assert result.already_satisfied == 0

    concepts = pg_session.query(OntologyConcept).all()
    assert len(concepts) == 10
    assert all(c.status == "APPROVED" for c in concepts)
    assert all(c.ontology_version == 1 for c in concepts)


@requires_postgres
def test_applying_the_artifact_twice_does_not_duplicate_concepts(pg_session):
    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)
    result2 = apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)

    assert result2.approved_new == 0
    assert result2.already_satisfied == 10
    count = pg_session.query(OntologyConcept).count()
    assert count == 10  # never 20


@requires_postgres
def test_applying_the_artifact_never_creates_a_terminology_mapping_decision(pg_session):
    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)
    count = pg_session.query(TerminologyMappingDecision).count()
    assert count == 0  # ontology concepts are a separate governance object


@requires_postgres
def test_applying_the_artifact_never_creates_or_modifies_a_safety_event(pg_session):
    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)
    count = pg_session.query(SafetyEvent).count()
    assert count == 0


@requires_postgres
def test_applying_the_artifact_requires_platform_admin(pg_session):
    org = make_org(pg_session, "Ontology Artifact - Authorization Boundary")
    from app.services.permissions import OrganizationRole
    org_admin = make_org_member(pg_session, org.id, role=OrganizationRole.ORG_ADMIN)

    with pytest.raises(AuthorizationError):
        apply_ontology_concept_artifact(pg_session, acting_user_id=org_admin.id)

    count = pg_session.query(OntologyConcept).count()
    assert count == 0


@requires_postgres
def test_a_malformed_artifact_file_fails_loudly(pg_session, tmp_path):
    admin = make_platform_admin_user(pg_session)
    bad_path = tmp_path / "bad_ontology_artifact.json"
    bad_path.write_text(json.dumps({"ontology_version": 1, "concepts": [{"layer": "event_type"}]}))  # missing keys

    with pytest.raises(OntologyConceptArtifactFormatError):
        apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id, artifact_path=bad_path)


@requires_postgres
def test_applied_concepts_are_individually_traceable_by_scope_key(pg_session):
    admin = make_platform_admin_user(pg_session)
    result = apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)

    fire_id = result.concept_ids[("event_subtype", "INCIDENT", "FIRE")]
    fire = pg_session.query(OntologyConcept).filter(OntologyConcept.id == fire_id).one()
    assert fire.concept_key == "FIRE"
    assert fire.layer == "event_subtype"
    assert fire.parent_domain == "INCIDENT"
    assert fire.status == "APPROVED"
