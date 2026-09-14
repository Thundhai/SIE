"""SIE Milestone 25A: Governed Risk-Area & Organization-Extensible Risk
Taxonomy v0.1 — dedicated regression suite.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** This suite
originally exercised the real `ontology_governance_service`
(`propose_concept`/`approve_concept`/`deprecate_concept`/...) and the
proprietary 11-concept risk-area seed list -- both extracted to the
private Commercial Core repository (see
docs/M43_IP_03_PUBLIC_EXTRACTION.md). What remains here covers exactly
what is still Public SIE's own responsibility:
`resolve_risk_area_concept()` (`app/risk_assessment/risk_area_resolution.py`,
kept, reclassified PUBLIC -- a tenant-scoped, governance-*state* gate
over the `OntologyConcept` table, not a governance *workflow*) and
`POST .../findings`'s use of it. Fixtures build `OntologyConcept` rows
directly via the ORM (see `tests/intelligence_test_helpers.py`) rather
than replaying a governance history that no longer exists in this
repository.

Removed entirely (private, no longer testable here): the 11-seeded-
concept compatibility parametrization (needed the private seed data),
governance-authorization-scoping tests (tested `ontology_governance_service`'s
own internal authorization calls), and candidate-generation resolution
tests (`app/risk_assessment/candidate_generation.py` is private).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, make_org_ontology_concept, make_platform_admin_user

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


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


# --- Item 14: new organization-specific concept -- no enum change, no migration -----------


def test_new_organization_specific_concept_requires_no_enum_change_or_migration(client, db_session):
    """The exact scenario item 14 specifies: an org-specific DROPPED_OBJECTS
    concept cannot be used while PROPOSED, but can once APPROVED -- all
    without touching a Python enum or running a migration (this test
    issues zero DDL of its own)."""
    org = make_org(db_session, "Org With Dropped Objects")
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)

    concept = make_org_ontology_concept(
        db_session, org.id, acting_user_id=admin.id, concept_key="DROPPED_OBJECTS", status="PROPOSED",
    )
    assessment = _create_assessment(client, headers, org.id)

    # PROPOSED cannot be used by Risk Assessment.
    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 422, response.text

    concept.status = "APPROVED"
    db_session.add(concept)
    db_session.flush()

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
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


def test_global_concept_is_usable_by_any_organization(client, db_session):
    admin = make_platform_admin_user(db_session)
    global_concept = make_org_ontology_concept(
        db_session, None, acting_user_id=admin.id, concept_key="PPE_COMPLIANCE", status="APPROVED"
    )
    org = make_org(db_session, "Any Org")
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=global_concept.id)
    assert response.status_code == 201, response.text
    assert response.json()["risk_area"]["scope"] == "GLOBAL"


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
    # commit() (not flush()) -- the read that must observe this update runs
    # in a *different* SQLAlchemy Session (this app's own per-request
    # session, via the `client` fixture's dependency override); a bare
    # flush() is visible only within db_session's own still-open
    # transaction, not cross-session, even though they share one
    # StaticPool-backed SQLite connection (see tests/conftest.py).
    concept_v1.status = "DEPRECATED"
    db_session.add(concept_v1)
    db_session.commit()
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


def test_create_finding_writes_an_audit_log_entry_naming_the_concept(client, db_session):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create_assessment(client, headers, org.id)
    concept = make_org_ontology_concept(
        db_session, None, acting_user_id=admin.id, concept_key="INCIDENT_SAFETY", status="APPROVED"
    )

    response = _create_finding(client, headers, org.id, assessment["id"], concept_id=concept.id)
    assert response.status_code == 201, response.text

    entries = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == uuid.UUID(assessment["id"]), AuditLog.action == "RISK_ASSESSMENT_FINDING_CREATED"
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].event_metadata["risk_area_concept_id"] == str(concept.id)
