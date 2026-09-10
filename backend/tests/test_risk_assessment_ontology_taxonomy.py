"""SIE Milestone 25A: Governed Risk-Area & Organization-Extensible Risk
Taxonomy v0.1 — dedicated regression suite. Covers item 30's own test
list: existing-concept compatibility, extensibility (no enum change, no
migration), governance-state enforcement, tenant isolation, historical
integrity, candidate-generation governed mapping, and API validation
failures. HTTP-level tests run against the ordinary SQLite `client`
fixture (mirrors `tests/test_risk_assessment_api.py`'s own established
shape); ontology governance itself (`propose_concept`/`approve_concept`/
etc.) is plain-column SQLAlchemy, so it works identically on SQLite --
no `@requires_postgres` needed here (contrast `tests/test_ontology_governance.py`,
which uses real Postgres purely by that file's own pre-existing
convention, not because SQLite cannot represent this data).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.risk_assessment.risk_area_ontology_seed import RISK_AREA_SEED_CONCEPTS
from app.services import ontology_governance_service as ogs
from app.services.authorization_service import AuthorizationError
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_org_ontology_concept,
    make_platform_admin_user,
    seed_risk_area_ontology_concepts,
)

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session) -> dict[str, uuid.UUID]:
    return seed_risk_area_ontology_concepts(db_session)


def _create_assessment(client, headers, org_id) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "Taxonomy Test Assessment",
        "assessment_type": "BASELINE",
        "assessment_date": AS_OF.isoformat(),
        "as_of": AS_OF.isoformat(),
        "generate_candidates": False,
    }
    response = client.post(f"{_URL}?organization_id={org_id}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_finding(client, headers, org_id, assessment_id, *, concept_id, **overrides):
    body = {"risk_area_concept_id": str(concept_id), "title": "Taxonomy test finding"}
    body.update(overrides)
    return client.post(f"{_URL}/{assessment_id}/findings?organization_id={org_id}", json=body, headers=headers)


# --- Item 13: existing 11 seeded concepts continue to work, via governed ontology ---------


@pytest.mark.parametrize("seed", RISK_AREA_SEED_CONCEPTS, ids=lambda s: s.legacy_risk_area)
def test_existing_seeded_risk_area_concept_is_accepted(client, db_session, seed, _risk_area_concepts):
    """Proves each of the original 11 risk areas works because its
    corresponding governed ontology concept is APPROVED and
    is_risk_area_eligible -- not because it exists in a Python enum
    (there is no such enum anymore)."""
    concept_id = _risk_area_concepts[seed.legacy_risk_area]
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["risk_area"]["concept_id"] == str(concept_id)
    assert body["risk_area"]["concept_key"] == seed.concept_key
    assert body["risk_area"]["layer"] == seed.layer
    assert body["risk_area"]["scope"] == "GLOBAL"


# --- Item 14: new organization-specific concept -- no enum change, no migration -----------


def test_new_organization_specific_concept_requires_no_enum_change_or_migration(client, db_session):
    """The exact scenario item 14 specifies: propose an org-specific
    DROPPED_OBJECTS concept, verify it cannot be used while PROPOSED,
    approve it through the existing governance mechanism, then create a
    finding with it -- all without touching a Python enum or running a
    migration (this test issues zero DDL of its own)."""
    org = make_org(db_session, "Org With Dropped Objects")
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)

    # 1-2. Propose an organization-specific concept.
    concept = ogs.propose_concept(
        db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="DROPPED_OBJECTS",
        definition="Objects falling from height.", justification="Org-specific extension.",
        acting_user_id=admin.id, organization_id=org.id, is_risk_area_eligible=True,
    )
    assert concept.status == "PROPOSED"

    assessment = _create_assessment(client, headers, org.id)

    # 3. PROPOSED cannot be used by Risk Assessment.
    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 422, response.text

    # 4. Approve through the existing governance mechanism.
    ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)

    # 5-6. Create a finding using DROPPED_OBJECTS.
    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    # 7. Verify success.
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["risk_area"]["concept_key"] == "DROPPED_OBJECTS"
    assert body["risk_area"]["scope"] == "ORGANIZATION"


# --- Item 15: governance state enforcement -------------------------------------------------


@pytest.mark.parametrize("status", ["PROPOSED", "REJECTED", "DEPRECATED"])
def test_non_approved_concept_cannot_be_used(client, db_session, status):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    concept = make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key=f"TAXONOMY_{status}", status=status
    )
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 422, response.text


def test_approved_concept_is_accepted(client, db_session):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    concept = make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key="TAXONOMY_APPROVED", status="APPROVED"
    )
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 201, response.text


def test_approved_but_not_risk_area_eligible_concept_cannot_be_used(client, db_session):
    """Item 9/5: an APPROVED concept is not automatically usable as a
    risk area -- is_risk_area_eligible is its own, separate, governed flag."""
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    concept = make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key="TAXONOMY_NOT_ELIGIBLE",
        status="APPROVED", is_risk_area_eligible=False,
    )
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 422, response.text


# --- Item 16: cross-tenant isolation ---------------------------------------------------------


def test_organization_b_cannot_use_organization_as_approved_concept(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    admin = make_platform_admin_user(db_session)
    concept_a = make_org_ontology_concept(
        db_session, org_a.id, acting_user_id=admin.id, concept_key="ORG_A_DROPPED_OBJECTS", status="APPROVED"
    )

    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_b = dev_auth_headers(manager_b.id)
    assessment_b = _create_assessment(client, headers_b, org_b.id)

    response = _create_finding(client, headers_b, org_b.id, assessment_b["id"], concept_id=concept_a.id)
    assert response.status_code == 404, response.text


def test_global_concept_is_usable_by_any_organization(client, db_session, _risk_area_concepts):
    org = make_org(db_session, "Any Org")
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(
        client, headers, org.id, assessment["id"], concept_id=_risk_area_concepts["PPE_COMPLIANCE"]
    )
    assert response.status_code == 201, response.text
    assert response.json()["risk_area"]["scope"] == "GLOBAL"


def test_governance_authorization_is_scoped_to_the_owning_organization(db_session):
    """Item 29: an ORG_ADMIN of one organization cannot govern another
    organization's ontology concept -- mirrors platform-admin-only
    enforcement for GLOBAL concepts, just scoped one level down."""
    org_a = make_org(db_session, "Governance Org A")
    org_b = make_org(db_session, "Governance Org B")
    admin_a = make_org_member(db_session, org_a.id, role=OrganizationRole.ORG_ADMIN)
    admin_b = make_org_member(db_session, org_b.id, role=OrganizationRole.ORG_ADMIN)

    concept = ogs.propose_concept(
        db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="ORG_A_ONLY",
        definition="d", justification="j", acting_user_id=admin_a.id, organization_id=org_a.id,
    )

    with pytest.raises(AuthorizationError):
        ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=admin_b.id, ontology_version=1)

    # The owning org's own admin can.
    approved = ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=admin_a.id, ontology_version=1)
    assert approved.status == "APPROVED"


def test_risk_assessment_write_permission_does_not_grant_ontology_governance(db_session):
    """Item 29's own explicit example: RISK_ASSESSMENT_WRITE != GOVERNANCE_MANAGE."""
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)  # has RISK_ASSESSMENT_WRITE

    with pytest.raises(AuthorizationError):
        ogs.propose_concept(
            db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="ANALYST_CANNOT_PROPOSE",
            definition="d", justification="j", acting_user_id=analyst.id, organization_id=org.id,
        )


# --- Item 17: historical/version integrity -----------------------------------------------


def test_deprecating_a_concept_does_not_change_a_historical_findings_reference(client, db_session):
    """DROPPED_OBJECTS v1 is used in an assessment; the concept is later
    deprecated -- the historical finding must still resolve to the exact
    concept and version it referenced at creation time, and never
    silently change meaning."""
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    concept_v1 = make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key="DROPPED_OBJECTS_HIST", status="APPROVED",
        ontology_version=1,
    )
    assessment = _create_assessment(client, headers, org.id)
    created = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept_v1.id)
    assert created.status_code == 201, created.text
    finding_id = created.json()["id"]
    assert created.json()["risk_area"]["ontology_version"] == 1

    # The concept evolves: v1 is deprecated, and a distinct v2 concept is approved.
    ogs.deprecate_concept(db_session, concept_id=concept_v1.id, acting_user_id=admin.id, reason="Superseded by v2.")
    make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key="DROPPED_OBJECTS_HIST_V2", status="APPROVED",
        ontology_version=2,
    )

    # The historical finding still resolves to its own original reference.
    response = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers)
    assert response.status_code == 200, response.text
    historical_finding = next(f for f in response.json()["findings"] if f["id"] == finding_id)
    assert historical_finding["risk_area"]["concept_id"] == str(concept_v1.id)
    assert historical_finding["risk_area"]["concept_key"] == "DROPPED_OBJECTS_HIST"
    assert historical_finding["risk_area"]["ontology_version"] == 1

    # A NEW finding can no longer reference the now-deprecated v1 concept.
    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept_v1.id)
    assert response.status_code == 422, response.text


# --- Item 12/25: candidate generation is governed, never a fabricated category ------------


def test_candidate_generation_resolves_a_known_metric_to_its_governed_concept(db_session):
    from app.risk_assessment.candidate_generation import _resolve_global_risk_area_concept

    concept = _resolve_global_risk_area_concept(db_session, ("event_subtype", "INCIDENT", "VEHICLE_INCIDENT"))
    assert concept is not None
    assert concept.concept_key == "VEHICLE_INCIDENT"
    assert concept.is_risk_area_eligible is True
    assert concept.organization_id is None


def test_candidate_generation_skips_an_unmapped_scope_key_rather_than_guessing(db_session):
    from app.risk_assessment.candidate_generation import _resolve_global_risk_area_concept

    # No concept exists at this scope key at all (not seeded) -- must be
    # skipped, never fabricated.
    concept = _resolve_global_risk_area_concept(db_session, ("observation_topic", "OBSERVATION", "NO_SUCH_CONCEPT"))
    assert concept is None


def test_candidate_generation_skips_a_scope_key_whose_concept_is_not_yet_eligible(db_session):
    """Even when a concept row exists at the exact scope key, it must be
    APPROVED and is_risk_area_eligible -- a merely-APPROVED-for-other-
    purposes concept is not silently treated as a risk area."""
    from app.risk_assessment.candidate_generation import _resolve_global_risk_area_concept

    admin = make_platform_admin_user(db_session)
    ogs.propose_concept(
        db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="NOT_A_RISK_AREA_YET",
        definition="d", justification="j", acting_user_id=admin.id, is_risk_area_eligible=False,
    )
    concept = ogs.get_concept_by_scope(
        db_session, layer="observation_topic", parent_domain="OBSERVATION", concept_key="NOT_A_RISK_AREA_YET"
    )
    ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=1)

    resolved = _resolve_global_risk_area_concept(db_session, ("observation_topic", "OBSERVATION", "NOT_A_RISK_AREA_YET"))
    assert resolved is None


# --- Item 30: API validation failures ------------------------------------------------------


def test_create_finding_with_a_nonexistent_concept_id_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=uuid.uuid4())
    assert response.status_code == 404, response.text


def test_create_finding_body_requires_a_uuid_not_an_arbitrary_string(client, db_session):
    """Item 19: the client cannot supply {"risk_area": "whatever"} and
    have it silently accepted -- risk_area_concept_id must be a real UUID,
    validated by the schema before it ever reaches the service layer."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json={"risk_area_concept_id": "whatever", "title": "Bad request"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_create_finding_writes_an_audit_log_entry_naming_the_concept(client, db_session, _risk_area_concepts):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)
    concept_id = _risk_area_concepts["INCIDENT_SAFETY"]

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept_id)
    assert response.status_code == 201, response.text

    entries = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == uuid.UUID(assessment["id"]), AuditLog.action == "RISK_ASSESSMENT_FINDING_CREATED"
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].event_metadata["risk_area_concept_id"] == str(concept_id)
