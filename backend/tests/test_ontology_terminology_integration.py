"""Tests for SIE Milestone 16 ("Governed Ontology-to-Terminology
Integration & Controlled Remapping Foundation v0.1"):
`app/services/ontology_terminology_integration_service.py` and its
wiring into `app/services/terminology_calibration_service.approve_mapping()`.

Cases A-N below are exactly the milestone's own required test list.
Every fixture is synthetic (fabricated organizations/terms) except the
10 real, already-committed Milestone 15 governed ontology concepts
themselves (FIRE, PROCEDURE_VIOLATION, PPE_COMPLIANCE, ...), applied
fresh in each test via the same durable artifact mechanism
`tests/test_ontology_concept_artifact.py` already exercises -- never the
real enterprise workbook, never a real `SafetyEvent`. Requires real
PostgreSQL (`@requires_postgres`, `pg_session`).
"""

from __future__ import annotations

import inspect

import pytest

from app.intelligence.terminology_review import TerminologyReviewEntry, TerminologyReviewStatus
from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services import ontology_governance_service as ogs
from app.services import ontology_terminology_integration_service as oti
from app.services import terminology_calibration_service as svc
from app.services.authorization_service import AuthorizationError
from app.services.ontology_concept_artifact_service import apply_ontology_concept_artifact
from app.services.ontology_terminology_integration_service import (
    OntologyValidationOutcome,
    validate_canonical_target,
)
from app.services.terminology_calibration_service import InvalidCanonicalTermError
from tests.intelligence_test_helpers import make_org, make_org_member, make_platform_admin_user
from tests.postgres_support import requires_postgres


def _apply_real_ontology(pg_session) -> None:
    """Applies the real, already-committed Milestone 15 durable ontology
    artifact (10 approved concepts) -- never a synthetic stand-in,
    because cases A/B/C/D/E/J/L/N below specifically exercise the real
    governed concepts (FIRE, PROCEDURE_VIOLATION, PPE_COMPLIANCE) this
    milestone's own examples name. Never touches real enterprise data --
    see `test_ontology_real_data_safety.py`'s own already-established
    guarantee, reused here."""
    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)


def _create_and_propose(pg_session, *, org_id, org_admin_id, domain, context, source_term, proposed_canonical_term):
    entry = TerminologyReviewEntry(
        domain=domain, context=context, source_term=source_term, proposed_canonical_term=None,
        status=TerminologyReviewStatus.UNKNOWN, reason="No alias match.", occurrence_count=1,
    )
    created = svc.create_review_candidates(pg_session, organization_id=org_id, source_system="synthetic-hse-xlsx", entries=[entry])
    return svc.propose_mapping(
        pg_session, organization_id=org_id, decision_id=created[0].id, proposed_canonical_term=proposed_canonical_term,
        rationale="Synthetic Milestone 16 fixture.", acting_user_id=org_admin_id,
    )


# --- A-K: the ontology validation contract itself, direct calls -----------------------------------


@requires_postgres
def test_a_valid_incident_subtype_validates(pg_session):
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="FIRE")
    assert result.outcome == OntologyValidationOutcome.VALID
    assert result.is_valid
    assert result.concept is not None
    assert result.concept.concept_key == "FIRE"


@requires_postgres
def test_b_valid_observation_subtype_validates(pg_session):
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="OBSERVATION", concept_key="PROCEDURE_VIOLATION")
    assert result.outcome == OntologyValidationOutcome.VALID


@requires_postgres
def test_c_valid_observation_topic_validates(pg_session):
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="PPE_COMPLIANCE")
    assert result.outcome == OntologyValidationOutcome.VALID


@requires_postgres
def test_d_wrong_layer_fails(pg_session):
    """PPE_COMPLIANCE is governed under observation_topic, not
    event_subtype -- requesting it at event_subtype must fail, never
    silently resolve to the observation_topic concept."""
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="OBSERVATION", concept_key="PPE_COMPLIANCE")
    assert result.outcome == OntologyValidationOutcome.WRONG_LAYER
    assert not result.is_valid


@requires_postgres
def test_e_wrong_parent_domain_fails(pg_session):
    """FIRE is governed under event_subtype/INCIDENT -- requesting it
    under event_subtype/OBSERVATION must fail."""
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="OBSERVATION", concept_key="FIRE")
    assert result.outcome == OntologyValidationOutcome.WRONG_PARENT_DOMAIN
    assert not result.is_valid


@requires_postgres
def test_f_nonexistent_concept_never_validates(pg_session):
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="MAGICAL_SAFETY_CONCEPT")
    assert result.outcome == OntologyValidationOutcome.NOT_FOUND
    assert not result.is_valid


@requires_postgres
def test_g_proposed_concept_never_validates(pg_session):
    admin = make_platform_admin_user(pg_session)
    ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_PROPOSED_ONLY",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    result = validate_canonical_target(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_PROPOSED_ONLY")
    assert result.outcome == OntologyValidationOutcome.NOT_APPROVED
    assert result.concept is not None and result.concept.status == "PROPOSED"


@requires_postgres
def test_h_rejected_concept_never_validates(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_REJECTED_TARGET",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    ogs.reject_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="Synthetic rejection.")
    result = validate_canonical_target(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_REJECTED_TARGET")
    assert result.outcome == OntologyValidationOutcome.NOT_APPROVED
    assert result.concept is not None and result.concept.status == "REJECTED"


@requires_postgres
def test_i_deprecated_concept_never_validates(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DEPRECATED_TARGET",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    ogs.deprecate_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="Synthetic deprecation.")
    result = validate_canonical_target(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DEPRECATED_TARGET")
    assert result.outcome == OntologyValidationOutcome.NOT_APPROVED
    assert result.concept is not None and result.concept.status == "DEPRECATED"


@requires_postgres
def test_j_cross_domain_top_level_value_never_validates(pg_session):
    """OBSERVATION was never proposed as an event_subtype concept under
    INCIDENT (governance would refuse the proposal itself -- see
    tests/test_ontology_governance.py's own cross-domain protection
    tests) -- so it simply does not exist anywhere in the ontology."""
    _apply_real_ontology(pg_session)
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="OBSERVATION")
    assert result.outcome == OntologyValidationOutcome.NOT_FOUND


@requires_postgres
def test_k_observation_topic_distinction(pg_session):
    """The exact same concept_key (PPE_COMPLIANCE) validates under its
    own governed layer (observation_topic) and fails under the wrong one
    (event_subtype) -- the milestone's own central layer-semantics
    guarantee, in one test."""
    _apply_real_ontology(pg_session)
    topic_result = validate_canonical_target(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="PPE_COMPLIANCE")
    subtype_result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="OBSERVATION", concept_key="PPE_COMPLIANCE")
    assert topic_result.outcome == OntologyValidationOutcome.VALID
    assert subtype_result.outcome != OntologyValidationOutcome.VALID
    assert subtype_result.outcome == OntologyValidationOutcome.WRONG_LAYER


# --- INVALID: structurally malformed requests ------------------------------------------------------


@requires_postgres
def test_unrecognized_layer_is_invalid(pg_session):
    result = validate_canonical_target(pg_session, layer="not_a_real_layer", parent_domain="INCIDENT", concept_key="FIRE")
    assert result.outcome == OntologyValidationOutcome.INVALID


@requires_postgres
def test_empty_concept_key_is_invalid(pg_session):
    result = validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="")
    assert result.outcome == OntologyValidationOutcome.INVALID


# --- L: historical (pre-Milestone-16) decisions are never mutated ---------------------------------


@requires_postgres
def test_l_a_historical_decision_using_the_static_vocabulary_is_never_mutated_by_the_ontology_integration(pg_session):
    """NEAR_MISS predates the governed ontology entirely (it has no
    OntologyConcept row) -- this decision must approve exactly as it did
    before Milestone 16, and must never be stamped with ontology
    traceability it never earned."""
    org = make_org(pg_session, "Ontology Integration - Historical Decision")
    org_admin = make_org_member(pg_session, org.id)

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_type", context=None,
        source_term="QuasiHistoricalNearMiss", proposed_canonical_term="NEAR_MISS",
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    assert approved.status == "APPROVED"
    assert approved.proposed_canonical_term == "NEAR_MISS"
    assert "ontology_concept_id" not in (approved.provenance or {})
    assert "ontology_version" not in (approved.provenance or {})


@requires_postgres
def test_l_environmental_event_type_remains_approvable_despite_the_same_named_observation_topic_concept(pg_session):
    """Critical backward-compatibility case: the top-level SafetyEventType
    ENVIRONMENTAL and the governed observation_topic/OBSERVATION concept
    ENVIRONMENTAL share a name but are two different things at two
    different scopes. A NEW event_type decision proposing ENVIRONMENTAL
    must keep resolving against the pre-existing static vocabulary,
    never be refused merely because a same-named concept exists
    elsewhere in the ontology."""
    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - Environmental Backward Compat")
    org_admin = make_org_member(pg_session, org.id)

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_type", context=None,
        source_term="QuasiEnvironmentalTerm", proposed_canonical_term="ENVIRONMENTAL",
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    assert approved.status == "APPROVED"
    assert "ontology_concept_id" not in (approved.provenance or {})  # governed under a DIFFERENT layer/scope


# --- M: a NEW decision cannot target an ontology concept that is not APPROVED ----------------------


@requires_postgres
def test_m_a_new_decision_cannot_be_approved_against_a_proposed_only_ontology_concept(pg_session):
    admin = make_platform_admin_user(pg_session)
    ogs.propose_concept(
        pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="QUASI_UNAPPROVED_TARGET",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    org = make_org(pg_session, "Ontology Integration - New Decision Rejected")
    org_admin = make_org_member(pg_session, org.id)

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiUnapprovedSourceTerm", proposed_canonical_term="QUASI_UNAPPROVED_TARGET",
    )
    with pytest.raises(InvalidCanonicalTermError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    pg_session.expire_all()
    still_proposed = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.id == proposed.id).one()
    assert still_proposed.status == "PROPOSED"  # never silently approved


@requires_postgres
def test_m_a_new_decision_targeting_a_governed_and_approved_concept_succeeds(pg_session):
    """The positive mirror of the case above -- proves the ontology is
    genuinely *authoritative* (FIRE was never in the pre-existing static
    subtype vocabulary at all; this approval is only possible because
    Milestone 16 makes the governed ontology a valid target)."""
    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - New Decision Approved")
    org_admin = make_org_member(pg_session, org.id)

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiFireSourceTerm", proposed_canonical_term="FIRE",
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)
    assert approved.status == "APPROVED"
    assert approved.proposed_canonical_term == "FIRE"


# --- N: ontology version traceability ---------------------------------------------------------------


@requires_postgres
def test_n_a_new_decision_records_the_ontology_version_it_was_validated_against(pg_session):
    """source term -> decision -> canonical ontology concept -> ontology
    version, exactly the provenance chain the milestone requires --
    verified against the final chosen design (provenance JSON, not a new
    column; see terminology_calibration_service.py's own docstring)."""
    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - Version Traceability")
    org_admin = make_org_member(pg_session, org.id)

    fire_concept = ogs.get_concept_by_scope(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="FIRE")
    assert fire_concept is not None

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiFireTraceabilityTerm", proposed_canonical_term="FIRE",
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    assert approved.provenance["ontology_concept_id"] == str(fire_concept.id)
    assert approved.provenance["ontology_version"] == fire_concept.ontology_version == 1
    assert approved.provenance["ontology_layer"] == "event_subtype"
    assert approved.provenance["ontology_parent_domain"] == "INCIDENT"

    # Full chain, source term -> decision -> concept -> version:
    assert approved.source_term == "QuasiFireTraceabilityTerm"
    assert approved.proposed_canonical_term == "FIRE"


# --- Authorization: reused, not weakened or bypassed -------------------------------------------------


@requires_postgres
def test_an_unauthorized_viewer_cannot_approve_a_decision_even_against_a_governed_concept(pg_session):
    """The ontology integration adds no new authorization path -- a
    viewer is refused by the exact same, unmodified
    authorization_service.require() call approve_mapping() already
    made, regardless of the proposed target."""
    from app.services.permissions import OrganizationRole

    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - Viewer Refused")
    org_admin = make_org_member(pg_session, org.id)
    viewer = make_org_member(pg_session, org.id, role=OrganizationRole.VIEWER)

    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiViewerRefusedTerm", proposed_canonical_term="FIRE",
    )
    with pytest.raises(AuthorizationError):
        svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=viewer.id)


@requires_postgres
def test_validate_canonical_target_itself_generates_no_audit_records(pg_session):
    """Read-only validation must never produce a misleading mutation
    audit record -- validate_canonical_target() is called many times
    above; none of those calls should have written to AuditLog."""
    from app.models.audit_log import AuditLog

    _apply_real_ontology(pg_session)
    before = pg_session.query(AuditLog).count()
    validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="FIRE")
    validate_canonical_target(pg_session, layer="event_subtype", parent_domain="OBSERVATION", concept_key="PPE_COMPLIANCE")
    validate_canonical_target(pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="NOTHING_HERE")
    after = pg_session.query(AuditLog).count()
    assert after == before


def test_the_integration_service_never_imports_reprocessing_or_the_real_loader_or_audit_service():
    """Static guarantee mirroring test_ontology_real_data_safety.py's own
    pattern: the module never imports the real-data reprocessing/loader
    machinery, and never imports audit_service (it is read-only and must
    never itself write an audit record -- see the runtime test above)."""
    import_lines = [
        line for line in inspect.getsource(oti).splitlines() if line.startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "terminology_reprocessing_service" not in joined
    assert "real_dataset_loader" not in joined
    assert "audit_service" not in joined


# --- Real-data safety --------------------------------------------------------------------------------


@requires_postgres
def test_real_data_safety_ontology_integration_never_touches_real_data_shaped_rows(pg_session):
    """Exercising the full validation + terminology-decision integration
    mechanism (all of the above, replayed compactly here) must never
    create or modify a SafetyEvent or EnterpriseIngestionRecord/Batch,
    and must never touch the real terminology decision artifact file."""
    import hashlib

    from app.services.terminology_decision_artifact_service import (
        DEFAULT_ARTIFACT_PATH as TERMINOLOGY_ARTIFACT_PATH,
    )

    before_hash = hashlib.sha256(TERMINOLOGY_ARTIFACT_PATH.read_bytes()).hexdigest()

    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - Real Data Safety")
    org_admin = make_org_member(pg_session, org.id)
    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiRealDataSafetyTerm", proposed_canonical_term="FIRE",
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    assert pg_session.query(SafetyEvent).count() == 0
    assert pg_session.query(EnterpriseIngestionRecord).count() == 0
    assert pg_session.query(EnterpriseIngestionBatch).count() == 0

    after_hash = hashlib.sha256(TERMINOLOGY_ARTIFACT_PATH.read_bytes()).hexdigest()
    assert before_hash == after_hash


@requires_postgres
def test_real_data_safety_none_of_the_15_rejected_terms_are_touched(pg_session):
    """The 15 rejected real-enterprise terms remain exactly REJECTED in
    the real decision artifact -- this milestone's own governed-ontology
    capability is never used to auto-remap them."""
    import json

    from app.services.terminology_decision_artifact_service import (
        DEFAULT_ARTIFACT_PATH as TERMINOLOGY_ARTIFACT_PATH,
    )

    _apply_real_ontology(pg_session)
    org = make_org(pg_session, "Ontology Integration - Rejected Terms Untouched")
    org_admin = make_org_member(pg_session, org.id)
    proposed = _create_and_propose(
        pg_session, org_id=org.id, org_admin_id=org_admin.id, domain="event_subtype", context="INCIDENT",
        source_term="QuasiRejectedTermsCheck", proposed_canonical_term="FIRE",
    )
    svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)

    with open(TERMINOLOGY_ARTIFACT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    rejected = [d for d in data["decisions"] if d["decision"] == "REJECTED"]
    approved = [d for d in data["decisions"] if d["decision"] == "APPROVED"]
    assert len(rejected) == 15
    assert len(approved) == 3
