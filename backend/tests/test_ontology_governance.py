"""Tests for the SIE Enterprise Ontology & Data Model Expansion v0.1
governance layer: `app/models/ontology_concept.py`,
`app/services/ontology_governance_service.py`. All fixtures here are
synthetic (fabricated concept keys/definitions) -- never derived from
the real enterprise dataset. Requires real PostgreSQL
(`@requires_postgres`, `pg_session`).
"""

from __future__ import annotations

import pytest

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.services import ontology_governance_service as ogs
from app.services.authorization_service import AuthorizationError
from app.services.permissions import OrganizationRole
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_platform_admin_user,
)
from tests.postgres_support import requires_postgres

# --- Naming / structural validation (no DB needed for the pure checks) --------------------------


def test_concept_key_must_be_all_caps_with_underscores():
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs._validate_concept_key("not valid")
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs._validate_concept_key("lowercase")
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs._validate_concept_key("1_STARTS_WITH_DIGIT")
    ogs._validate_concept_key("VALID_CONCEPT_KEY")  # does not raise


def test_event_type_layer_concepts_must_not_declare_a_parent_domain():
    ogs._validate_layer_and_parent_domain("event_type", None, "SOME_NEW_TYPE")  # does not raise
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs._validate_layer_and_parent_domain("event_type", "INCIDENT", "SOME_NEW_TYPE")


def test_unrecognized_layer_is_rejected():
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs._validate_layer_and_parent_domain("not_a_real_layer", "INCIDENT", "X")


# --- Model-level lifecycle helper properties (no DB needed) --------------------------------------


def test_status_helper_properties_without_a_database():
    from app.models.ontology_concept import OntologyConceptStatus

    proposed = OntologyConcept(status=OntologyConceptStatus.PROPOSED)
    approved = OntologyConcept(status=OntologyConceptStatus.APPROVED)
    rejected = OntologyConcept(status=OntologyConceptStatus.REJECTED)
    deprecated = OntologyConcept(status=OntologyConceptStatus.DEPRECATED)

    assert not proposed.is_terminal and not proposed.is_eligible_for_mapping
    assert approved.is_terminal and approved.is_eligible_for_mapping
    assert rejected.is_terminal and not rejected.is_eligible_for_mapping
    assert deprecated.is_terminal and not deprecated.is_eligible_for_mapping


# --- Lifecycle: PROPOSED -> APPROVED / REJECTED; APPROVED -> DEPRECATED --------------------------


@requires_postgres
def test_propose_then_approve_makes_a_concept_eligible_for_mapping(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_TOPIC",
        definition="A synthetic fixture topic.", justification="Test evidence.", acting_user_id=admin.id,
    )
    assert concept.status == "PROPOSED"
    assert ogs.is_valid_concept(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_TOPIC") is False

    approved = ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    assert approved.status == "APPROVED"
    assert approved.ontology_version == 1
    assert ogs.is_valid_concept(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_TOPIC") is True


@requires_postgres
def test_propose_then_reject_leaves_concept_permanently_unresolved(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="event_type", parent_domain=None, concept_key="QUASI_NEW_TYPE",
        definition="d", justification="thin evidence", acting_user_id=admin.id,
    )
    rejected = ogs.reject_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="Not enough evidence.")
    assert rejected.status == "REJECTED"
    assert ogs.is_valid_concept(pg_session, layer="event_type", parent_domain=None, concept_key="QUASI_NEW_TYPE") is False


@requires_postgres
def test_a_terminal_concept_cannot_be_approved_or_rejected_again(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_TERMINAL",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)

    with pytest.raises(ogs.OntologyConceptStateError):
        ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=2)
    with pytest.raises(ogs.OntologyConceptStateError):
        ogs.reject_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="r")


@requires_postgres
def test_deprecate_requires_an_approved_concept_and_is_one_way(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DEPRECATE",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    # Cannot deprecate a merely-PROPOSED concept.
    with pytest.raises(ogs.OntologyConceptStateError):
        ogs.deprecate_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="r")

    ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    deprecated = ogs.deprecate_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="superseded")
    assert deprecated.status == "DEPRECATED"
    assert ogs.is_valid_concept(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DEPRECATE") is False

    # One-way: cannot deprecate again (already terminal, not APPROVED).
    with pytest.raises(ogs.OntologyConceptStateError):
        ogs.deprecate_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="r2")


# --- Duplicate prevention -------------------------------------------------------------------------


@requires_postgres
def test_duplicate_scope_key_is_refused_regardless_of_existing_status(pg_session):
    admin = make_platform_admin_user(pg_session)
    ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DUP",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    with pytest.raises(ogs.OntologyConceptConflictError):
        ogs.propose_concept(
            pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_DUP",
            definition="different definition", justification="different justification", acting_user_id=admin.id,
        )


# --- Cross-domain protection (the milestone's own central requirement) ---------------------------


@requires_postgres
@pytest.mark.parametrize("layer", ["event_subtype", "observation_topic"])
@pytest.mark.parametrize("parent_domain", ["INCIDENT", "OBSERVATION"])
def test_a_parent_domain_not_in_the_existing_ontology_is_rejected(pg_session, layer, parent_domain):
    admin = make_platform_admin_user(pg_session)
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs.propose_concept(
            pg_session, layer=layer, parent_domain="NOT_A_REAL_EVENT_TYPE", concept_key="QUASI_X",
            definition="d", justification="j", acting_user_id=admin.id,
        )


@requires_postgres
@pytest.mark.parametrize(
    ("parent_domain", "bogus_subtype"),
    [("INCIDENT", "OBSERVATION"), ("INCIDENT", "PERMIT"), ("INCIDENT", "TRAINING"),
     ("OBSERVATION", "PERMIT"), ("OBSERVATION", "TRAINING")],
)
def test_event_subtype_concept_key_can_never_reuse_a_different_top_level_event_type(pg_session, parent_domain, bogus_subtype):
    """The milestone's own explicit cross-domain protection requirement:
    INCIDENT+OBSERVATION, INCIDENT+PERMIT, INCIDENT+TRAINING,
    OBSERVATION+PERMIT, OBSERVATION+TRAINING can never become valid
    event_subtype concepts merely because the concept_key names exist
    elsewhere in the ontology."""
    admin = make_platform_admin_user(pg_session)
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs.propose_concept(
            pg_session, layer="event_subtype", parent_domain=parent_domain, concept_key=bogus_subtype,
            definition="d", justification="j", acting_user_id=admin.id,
        )


@requires_postgres
def test_no_ontology_concept_is_created_when_cross_domain_validation_fails(pg_session):
    admin = make_platform_admin_user(pg_session)
    with pytest.raises(ogs.InvalidOntologyConceptError):
        ogs.propose_concept(
            pg_session, layer="event_subtype", parent_domain="INCIDENT", concept_key="OBSERVATION",
            definition="d", justification="j", acting_user_id=admin.id,
        )
    count = pg_session.query(OntologyConcept).filter(
        OntologyConcept.layer == "event_subtype", OntologyConcept.parent_domain == "INCIDENT",
        OntologyConcept.concept_key == "OBSERVATION",
    ).count()
    assert count == 0


@requires_postgres
def test_observation_topic_layer_may_reuse_a_top_level_type_name_deliberately(pg_session):
    """Namespace isolation: `(layer, parent_domain, concept_key)` is the
    real scope key -- an `observation_topic` concept named the same as
    an existing top-level `SafetyEventType` (e.g. `ENVIRONMENTAL`) is
    deliberate and safe, since it lives in a genuinely separate
    dimension never read by the same code as `event_subtype`."""
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="ENVIRONMENTAL",
        definition="Observation topic, distinct from the top-level ENVIRONMENTAL event_type.",
        justification="Real dataset evidence.", acting_user_id=admin.id,
    )
    assert concept.status == "PROPOSED"
    ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    assert ogs.is_valid_concept(pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="ENVIRONMENTAL") is True


# --- Governance / authorization -------------------------------------------------------------------


@requires_postgres
def test_an_organizations_own_governance_manage_holder_cannot_govern_the_ontology(pg_session):
    """The ontology is platform-wide -- an ORG_ADMIN's own
    GOVERNANCE_MANAGE (scoped to their own organization) must never be
    sufficient to change what every OTHER tenant's data can be
    classified as."""
    org = make_org(pg_session, "Ontology - Org Admin Cannot Govern")
    org_admin = make_org_member(pg_session, org.id, role=OrganizationRole.ORG_ADMIN)

    with pytest.raises(AuthorizationError):
        ogs.propose_concept(
            pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_ORG_ADMIN",
            definition="d", justification="j", acting_user_id=org_admin.id,
        )
    count = pg_session.query(OntologyConcept).filter(OntologyConcept.concept_key == "QUASI_ORG_ADMIN").count()
    assert count == 0


@requires_postgres
def test_a_viewer_cannot_govern_the_ontology(pg_session):
    org = make_org(pg_session, "Ontology - Viewer Cannot Govern")
    viewer = make_org_member(pg_session, org.id, role=OrganizationRole.VIEWER)
    with pytest.raises(AuthorizationError):
        ogs.propose_concept(
            pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_VIEWER",
            definition="d", justification="j", acting_user_id=viewer.id,
        )


@requires_postgres
def test_a_user_with_no_membership_at_all_cannot_govern_the_ontology(pg_session):
    import uuid

    from app.schemas.user import UserCreate
    from app.services.user_service import user_service

    stranger = user_service.create(pg_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name="Stranger"))
    with pytest.raises(AuthorizationError):
        ogs.propose_concept(
            pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_STRANGER",
            definition="d", justification="j", acting_user_id=stranger.id,
        )


@requires_postgres
def test_platform_admin_can_perform_the_full_governance_lifecycle(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_PLATFORM_ADMIN",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    approved = ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    assert approved.status == "APPROVED"
    assert approved.reviewer_user_id == admin.id


# --- Audit logging ---------------------------------------------------------------------------------


@requires_postgres
def test_every_lifecycle_transition_is_audited_platform_wide(pg_session):
    admin = make_platform_admin_user(pg_session)
    concept = ogs.propose_concept(
        pg_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="QUASI_AUDIT",
        definition="d", justification="j", acting_user_id=admin.id,
    )
    ogs.approve_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)
    ogs.deprecate_concept(pg_session, concept_id=concept.id, acting_user_id=admin.id, reason="r")

    logs = pg_session.query(AuditLog).filter(
        AuditLog.resource_type == "OntologyConcept", AuditLog.resource_id == concept.id,
    ).all()
    actions = {log.action for log in logs}
    assert {"ONTOLOGY_CONCEPT_PROPOSED", "ONTOLOGY_CONCEPT_APPROVED", "ONTOLOGY_CONCEPT_DEPRECATED"} <= actions
    assert all(log.organization_id is None for log in logs)  # platform-wide, never tenant-scoped
    assert all(log.user_id == admin.id for log in logs)
