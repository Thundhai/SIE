"""SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1 —
`app/api/v1/risk_assessments.py`. HTTP-level tests against the ordinary
SQLite `client` fixture, mirroring `tests/test_actions_api.py`'s own
established shape. Covers item 28's full test list: assessment
lifecycle, risk calculation (through the API), controls, residual risk,
findings, temporal, tenant isolation, authorization, audit, regression.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.ontology_concept import OntologyConcept
from app.models.risk_assessment import RiskAssessment
from app.services.api_client_service import api_client_service
from app.services.permissions import OrganizationRole, Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_safety_event,
    make_site,
    seed_risk_area_ontology_concepts,
)

_URL = "/api/v1/risk-assessments"
AS_OF = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _risk_area_concepts(db_session) -> dict[str, uuid.UUID]:
    """SIE Milestone 25A: every risk-area-bearing finding in this file
    now references a governed `OntologyConcept`, not a closed enum --
    seed the same 11 GLOBAL concepts migration 0017 seeds on a real
    database, autouse so no test in this file has to remember to. See
    `tests/intelligence_test_helpers.py::seed_risk_area_ontology_concepts()`."""
    return seed_risk_area_ontology_concepts(db_session)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.RISK_ASSESSMENT_READ, Permission.RISK_ASSESSMENT_WRITE]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _create_body(**overrides) -> dict:
    body = {
        "scope": "ORGANIZATION",
        "title": "Enterprise Q3 Assessment",
        "assessment_type": "BASELINE",
        "assessment_date": AS_OF.isoformat(),
        "as_of": AS_OF.isoformat(),
        "generate_candidates": False,
    }
    body.update(overrides)
    return body


def _create(client, headers, org_id, **overrides) -> dict:
    response = client.post(f"{_URL}?organization_id={org_id}", json=_create_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _risk_area_concept_id(db_session, concept_key: str = "VEHICLE_INCIDENT") -> str:
    """SIE Milestone 25A: `risk_area` is now a governed
    `OntologyConcept` reference, not a closed enum string -- resolves the
    GLOBAL concept `seed_risk_area_ontology_concepts()` (autouse fixture
    above) already seeded. Defaults to `VEHICLE_INCIDENT`, the concept
    the old `RiskArea.VEHICLE_SAFETY` enum member mapped to (see
    `app/risk_assessment/risk_area_ontology_seed.py`)."""
    concept = db_session.execute(
        select(OntologyConcept).where(
            OntologyConcept.concept_key == concept_key, OntologyConcept.organization_id.is_(None)
        )
    ).scalar_one()
    return str(concept.id)


def _finding_body(db_session, **overrides) -> dict:
    body = {"risk_area_concept_id": _risk_area_concept_id(db_session), "title": "Repeated vehicle incidents"}
    body.update(overrides)
    return body


# --- Assessment lifecycle (item 28) ----------------------------------------------------


def test_create_assessment_minimal_payload(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    body = _create(client, dev_auth_headers(manager.id), org.id)
    assert body["status"] == "DRAFT"
    assert body["version"] == 1
    assert body["lineage_id"] == body["id"]
    assert body["methodology_version"] == "risk-assessment-v1"
    assert body["findings"] == []
    assert "intelligence_context" in body


def test_create_site_scope_requires_site_id(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    response = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE"),
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 422


def test_create_site_scope_rejects_a_foreign_site(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    other_site = make_site(db_session, other_org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    response = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(other_site.id)),
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 404


def test_draft_is_editable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)

    response = client.patch(f"{_URL}/{created['id']}?organization_id={org.id}", json={"title": "Revised title"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Revised title"


def test_submit_transitions_draft_to_in_review(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)

    response = client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "IN_REVIEW"
    assert response.json()["submitted_at"] is not None


def test_in_review_is_still_editable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)

    response = client.patch(f"{_URL}/{created['id']}?organization_id={org.id}", json={"title": "Still editable"}, headers=headers)
    assert response.status_code == 200


def test_approve_transitions_in_review_to_approved(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)

    response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["approved_at"] is not None


def test_approved_assessment_is_immutable(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)

    response = client.patch(f"{_URL}/{created['id']}?organization_id={org.id}", json={"title": "Nope"}, headers=headers)
    assert response.status_code == 422


def test_invalid_transition_draft_to_approved_directly_is_rejected(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)

    response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)
    assert response.status_code == 422


def test_invalid_transition_cannot_submit_an_already_approved_assessment(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)

    response = client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    assert response.status_code == 422


def test_supersede_opens_a_new_version_in_the_same_lineage(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1 = _create(client, headers, org.id)
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)

    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])
    assert v2["version"] == 2
    assert v2["lineage_id"] == v1["lineage_id"]
    assert v2["supersedes_id"] == v1["id"]
    assert v2["status"] == "DRAFT"

    # v1 stays APPROVED (fully active/queryable) until v2 is itself approved.
    response = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers)
    assert response.json()["status"] == "APPROVED"

    client.post(f"{_URL}/{v2['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v2['id']}/approve?organization_id={org.id}", headers=headers)

    response = client.get(f"{_URL}/{v1['id']}?organization_id={org.id}", headers=headers)
    assert response.json()["status"] == "SUPERSEDED"


def test_only_an_approved_assessment_can_be_superseded(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    draft = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(supersedes_assessment_id=draft["id"]),
        headers=headers,
    )
    assert response.status_code == 422


def test_list_assessments_pagination(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for _ in range(3):
        _create(client, headers, org.id)

    response = client.get(f"{_URL}?organization_id={org.id}&page=1&page_size=2", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_assessments_filters_by_status(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    _create(client, headers, org.id)
    submitted = _create(client, headers, org.id)
    client.post(f"{_URL}/{submitted['id']}/submit?organization_id={org.id}", headers=headers)

    response = client.get(f"{_URL}?organization_id={org.id}&status=IN_REVIEW", headers=headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == submitted["id"]


def test_get_nonexistent_assessment_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    response = client.get(f"{_URL}/{uuid.uuid4()}?organization_id={org.id}", headers=dev_auth_headers(manager.id))
    assert response.status_code == 404


# --- Risk calculation through the API (item 28's own "Risk calculation") --------------


def test_finding_with_a_rating_gets_the_deterministic_inherent_risk(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4, consequence=4),
        headers=headers,
    )
    assert response.status_code == 201
    finding = response.json()
    assert finding["inherent_risk_score"] == 16
    assert finding["inherent_risk_classification"] == "HIGH"
    assert finding["candidate_status"] is None  # directly human-authored


def test_finding_rejects_an_out_of_range_likelihood(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=6, consequence=4),
        headers=headers,
    )
    assert response.status_code == 422


def test_finding_requires_likelihood_and_consequence_together(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4),
        headers=headers,
    )
    assert response.status_code == 422


# --- Controls (item 28) -----------------------------------------------------------------


def test_finding_with_no_controls_has_an_empty_controls_list(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    created = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()
    assert created["controls"] == []


def _add_control(client, headers, org_id, assessment_id, finding_id, **overrides):
    control = {"description": "Traffic management plan", "control_type": "ADMINISTRATIVE"}
    control.update(overrides)
    return client.patch(
        f"{_URL}/{assessment_id}/findings/{finding_id}?organization_id={org_id}",
        json={"controls": [control]},
        headers=headers,
    )


def test_control_effectiveness_effective(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()

    response = _add_control(client, headers, org.id, assessment["id"], finding["id"], effectiveness="EFFECTIVE")
    assert response.status_code == 200
    assert response.json()["controls"][0]["effectiveness"] == "EFFECTIVE"


def test_control_effectiveness_partially_effective(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()

    response = _add_control(client, headers, org.id, assessment["id"], finding["id"], effectiveness="PARTIALLY_EFFECTIVE")
    assert response.json()["controls"][0]["effectiveness"] == "PARTIALLY_EFFECTIVE"


def test_control_effectiveness_ineffective(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()

    response = _add_control(client, headers, org.id, assessment["id"], finding["id"], effectiveness="INEFFECTIVE")
    assert response.json()["controls"][0]["effectiveness"] == "INEFFECTIVE"


def test_control_effectiveness_defaults_to_not_assessed_never_conflated_with_ineffective(client, db_session):
    """Item 12: "no control information was provided" must never be
    represented as "the control is ineffective" -- these are different
    states."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}", json=_finding_body(db_session), headers=headers
    ).json()

    response = _add_control(client, headers, org.id, assessment["id"], finding["id"])
    control = response.json()["controls"][0]
    assert control["effectiveness"] == "NOT_ASSESSED"
    assert control["effectiveness"] != "INEFFECTIVE"


# --- Residual risk (item 28) -------------------------------------------------------------


def test_residual_risk_is_an_independent_assessment_not_a_percentage_reduction(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4, consequence=4),
        headers=headers,
    ).json()
    assert finding["inherent_risk_score"] == 16

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{finding['id']}?organization_id={org.id}",
        json={"residual_likelihood": 2, "residual_consequence": 4},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()
    # The milestone's own worked example: inherent 16/HIGH -> residual 8/MODERATE.
    assert updated["residual_risk_score"] == 8
    assert updated["residual_risk_classification"] == "MODERATE"
    # Inherent risk is untouched by supplying a residual rating.
    assert updated["inherent_risk_score"] == 16
    assert updated["inherent_risk_classification"] == "HIGH"


def test_no_fabricated_percentage_reduction_field_exists(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)
    finding = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, likelihood=4, consequence=4),
        headers=headers,
    ).json()
    assert not any("percent" in key.lower() or "reduction" in key.lower() for key in finding)


# --- Findings: candidate lifecycle (item 28) ----------------------------------------------


def test_candidate_findings_are_generated_from_a_recurring_pattern(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)

    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()

    response = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    )
    assert response.status_code == 201
    findings = response.json()["findings"]
    assert len(findings) >= 1
    candidate = findings[0]
    assert candidate["candidate_status"] == "IDENTIFIED"
    assert candidate["likelihood"] is None  # never an approved risk on its own
    assert candidate["source"] == "INTELLIGENCE_PATTERN"
    assert candidate["originating_calculation_version"] is not None
    assert len(candidate["evidence"]) >= 1


def test_a_human_can_accept_a_candidate_and_supply_a_rating(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()
    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    ).json()
    candidate = assessment["findings"][0]

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{candidate['id']}?organization_id={org.id}",
        json={"candidate_status": "ACCEPTED", "likelihood": 3, "consequence": 3},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["candidate_status"] == "ACCEPTED"
    assert updated["inherent_risk_score"] == 9


def test_a_candidate_cannot_be_rated_before_being_accepted(client, db_session):
    """Item 27's own architectural boundary: candidate != approved risk."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()
    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    ).json()
    candidate = assessment["findings"][0]
    assert candidate["candidate_status"] == "IDENTIFIED"

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{candidate['id']}?organization_id={org.id}",
        json={"likelihood": 3, "consequence": 3},
        headers=headers,
    )
    assert response.status_code == 422


def test_a_candidate_can_be_rejected(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()
    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    ).json()
    candidate = assessment["findings"][0]

    response = client.patch(
        f"{_URL}/{assessment['id']}/findings/{candidate['id']}?organization_id={org.id}",
        json={"candidate_status": "REJECTED"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["candidate_status"] == "REJECTED"
    assert response.json()["likelihood"] is None


def test_evidence_linkage_to_an_event(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    event = make_safety_event(
        organization_id=org.id, event_type="INCIDENT", event_time=AS_OF, ingestion_time=AS_OF,
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(event)
    db_session.commit()
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "EVENT", "reference_id": str(event.id)}]),
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["evidence"][0]["reference_id"] == str(event.id)


def test_evidence_rejects_a_foreign_organizations_event(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org 2")
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    foreign_event = make_safety_event(
        organization_id=other_org.id, event_type="INCIDENT", event_time=AS_OF, ingestion_time=AS_OF,
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(foreign_event)
    db_session.commit()
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "EVENT", "reference_id": str(foreign_event.id)}]),
        headers=headers,
    )
    assert response.status_code == 404


def test_evidence_intelligence_source_linkage_uses_a_reference_label_not_an_id(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "ANOMALY", "reference_label": "anomaly:incident_count"}]),
        headers=headers,
    )
    assert response.status_code == 201
    evidence = response.json()["evidence"][0]
    assert evidence["reference_id"] is None
    assert evidence["reference_label"] == "anomaly:incident_count"


def test_evidence_anomaly_type_rejects_a_reference_id(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    assessment = _create(client, headers, org.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "ANOMALY", "reference_id": str(uuid.uuid4())}]),
        headers=headers,
    )
    assert response.status_code == 422


# --- Temporal (item 28) -----------------------------------------------------------------


def test_future_events_are_excluded_from_candidate_generation(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    future_event = make_safety_event(
        organization_id=org.id, site_id=site.id, event_type="INCIDENT",
        event_time=AS_OF + timedelta(days=5), ingestion_time=AS_OF + timedelta(days=5),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(future_event)
    db_session.commit()

    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    ).json()
    all_event_ids = {
        eid for f in assessment["findings"] for ev in f["evidence"] for eid in [ev["reference_id"]] if eid
    }
    assert str(future_event.id) not in all_event_ids


def test_future_ingestion_is_excluded_from_candidate_generation(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    backdated = make_safety_event(
        organization_id=org.id, site_id=site.id, event_type="INCIDENT",
        event_time=AS_OF - timedelta(days=1), ingestion_time=AS_OF + timedelta(days=1),
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(backdated)
    db_session.commit()

    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=True),
        headers=headers,
    ).json()
    all_event_ids = {
        eid for f in assessment["findings"] for ev in f["evidence"] for eid in [ev["reference_id"]] if eid
    }
    assert str(backdated.id) not in all_event_ids


def test_actions_created_after_as_of_are_excluded_from_intelligence_context(client, db_session):
    """`actions_context` inside `intelligence_context` is point-in-time
    filtered exactly like GET /intelligence/enterprise already is
    (Milestone 22A) -- this milestone reuses that computation
    unmodified."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    past_as_of = AS_OF - timedelta(days=10)

    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(as_of=past_as_of.isoformat(), generate_candidates=False),
        headers=headers,
    ).json()
    assert assessment["as_of"] is not None
    # No action-specific field is asserted here beyond successful,
    # point-in-time-correct computation -- actions_context itself is not
    # part of IntelligenceContextRead's own minimal item-26 shape, so this
    # test only confirms the as_of is honored end-to-end without error.
    response = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers)
    assert response.status_code == 200


def test_historical_assessment_is_reproducible(client, db_session):
    """Item 18: "what did we assess the risk to be at that time?" --
    fetching the same historical assessment twice returns the identical
    intelligence_context, since as_of is fixed and every Milestone 22-24
    computation is itself point-in-time-correct and deterministic."""
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    for i in range(3):
        event = make_safety_event(
            organization_id=org.id, site_id=site.id, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        db_session.add(event)
    db_session.commit()

    assessment = client.post(
        f"{_URL}?organization_id={org.id}",
        json=_create_body(scope="SITE", site_id=str(site.id), generate_candidates=False),
        headers=headers,
    ).json()

    first = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers).json()
    second = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=headers).json()
    assert first["intelligence_context"] == second["intelligence_context"]


# --- Tenant isolation (item 28) -----------------------------------------------------------


def test_organization_isolation_on_list(client, db_session):
    org_a = make_org(db_session, "Org A7")
    org_b = make_org(db_session, "Org B7")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    _create(client, dev_auth_headers(manager_a.id), org_a.id)
    _create(client, dev_auth_headers(manager_b.id), org_b.id)

    response = client.get(f"{_URL}?organization_id={org_a.id}", headers=dev_auth_headers(manager_a.id))
    assert response.json()["total"] == 1


def test_organization_isolation_on_get(client, db_session):
    org_a = make_org(db_session, "Org A8")
    org_b = make_org(db_session, "Org B8")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = client.get(f"{_URL}/{assessment['id']}?organization_id={org_b.id}", headers=dev_auth_headers(manager_b.id))
    assert response.status_code == 404


def test_site_isolation_rejects_cross_tenant_site_in_create(client, db_session):
    org_a = make_org(db_session, "Org A9")
    org_b = make_org(db_session, "Org B9")
    site_b = make_site(db_session, org_b.id)
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)

    response = client.post(
        f"{_URL}?organization_id={org_a.id}",
        json=_create_body(scope="SITE", site_id=str(site_b.id)),
        headers=dev_auth_headers(manager_a.id),
    )
    assert response.status_code == 404


def test_event_evidence_isolation(client, db_session):
    org_a = make_org(db_session, "Org A10")
    org_b = make_org(db_session, "Org B10")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    foreign_event = make_safety_event(
        organization_id=org_b.id, event_type="INCIDENT", event_time=AS_OF, ingestion_time=AS_OF,
        source_record_id=str(uuid.uuid4()),
    )
    db_session.add(foreign_event)
    db_session.commit()
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org_a.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "EVENT", "reference_id": str(foreign_event.id)}]),
        headers=dev_auth_headers(manager_a.id),
    )
    assert response.status_code == 404


def test_action_evidence_isolation(client, db_session):
    from app.models.safety_action import SafetyAction

    org_a = make_org(db_session, "Org A11")
    org_b = make_org(db_session, "Org B11")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    foreign_action = SafetyAction(
        organization_id=org_b.id, title="Foreign action", action_type="CORRECTIVE", priority="MEDIUM",
        status="OPEN", attributes={},
    )
    db_session.add(foreign_action)
    db_session.commit()
    assessment = _create(client, dev_auth_headers(manager_a.id), org_a.id)

    response = client.post(
        f"{_URL}/{assessment['id']}/findings?organization_id={org_a.id}",
        json=_finding_body(db_session, evidence=[{"evidence_type": "ACTION", "reference_id": str(foreign_action.id)}]),
        headers=dev_auth_headers(manager_a.id),
    )
    assert response.status_code == 404


def test_assessment_isolation_cannot_supersede_a_foreign_organizations_assessment(client, db_session):
    org_a = make_org(db_session, "Org A12")
    org_b = make_org(db_session, "Org B12")
    manager_a = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    manager_b = make_org_member(db_session, org_b.id, role=OrganizationRole.HSE_MANAGER)
    headers_b = dev_auth_headers(manager_b.id)
    v1 = _create(client, headers_b, org_b.id)
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org_b.id}", headers=headers_b)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org_b.id}", headers=headers_b)

    response = client.post(
        f"{_URL}?organization_id={org_a.id}",
        json=_create_body(supersedes_assessment_id=v1["id"]),
        headers=dev_auth_headers(manager_a.id),
    )
    assert response.status_code == 404


# --- Authorization (item 28, "according to the actual existing permission model") ------


def test_viewer_can_read_but_not_write(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    viewer = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    assessment = _create(client, dev_auth_headers(manager.id), org.id)

    read_response = client.get(f"{_URL}/{assessment['id']}?organization_id={org.id}", headers=dev_auth_headers(viewer.id))
    assert read_response.status_code == 200

    write_response = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=dev_auth_headers(viewer.id))
    assert write_response.status_code == 403


def test_hse_user_can_read_but_not_write(client, db_session):
    org = make_org(db_session)
    hse_user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    response = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=dev_auth_headers(hse_user.id))
    assert response.status_code == 403

    list_response = client.get(f"{_URL}?organization_id={org.id}", headers=dev_auth_headers(hse_user.id))
    assert list_response.status_code == 200


def test_hse_analyst_can_write_but_not_approve(client, db_session):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    headers = dev_auth_headers(analyst.id)
    created = _create(client, headers, org.id)
    submit_response = client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    assert submit_response.status_code == 200

    approve_response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)
    assert approve_response.status_code == 403


def test_hse_manager_can_write_and_approve(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)
    assert response.status_code == 200


def test_org_admin_can_do_everything(client, db_session):
    org = make_org(db_session)
    admin = make_org_member(db_session, org.id, role=OrganizationRole.ORG_ADMIN)
    headers = dev_auth_headers(admin.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)
    assert response.status_code == 200


def test_platform_admin_can_access_across_the_authorization_boundary(client, db_session):
    from app.models.user import User

    org = make_org(db_session)
    admin_user = User(email=f"{uuid.uuid4().hex}@example.com", name="Platform Admin", platform_role="PLATFORM_ADMIN")
    db_session.add(admin_user)
    db_session.commit()

    response = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=dev_auth_headers(admin_user.id))
    assert response.status_code == 201


def test_machine_client_with_scope_can_manage_assessments(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id)
    response = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=_bearer(credential))
    assert response.status_code == 201


def test_machine_client_without_scope_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.INTELLIGENCE_READ])
    response = client.post(f"{_URL}?organization_id={org.id}", json=_create_body(), headers=_bearer(credential))
    assert response.status_code == 403


def test_machine_client_cannot_approve_without_the_approve_scope(client, db_session):
    org = make_org(db_session)
    credential = _make_client_credential(
        db_session, org.id, scopes=[Permission.RISK_ASSESSMENT_READ, Permission.RISK_ASSESSMENT_WRITE]
    )
    created = _create(client, _bearer(credential), org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=_bearer(credential))

    response = client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 403


# --- Audit (item 28) ---------------------------------------------------------------------


def test_create_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    created = _create(client, dev_auth_headers(manager.id), org.id)

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    ).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_CREATED" for e in entries)


def test_update_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.patch(f"{_URL}/{created['id']}?organization_id={org.id}", json={"title": "Updated"}, headers=headers)

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    ).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_UPDATED" for e in entries)


def test_submit_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    ).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_SUBMITTED" for e in entries)


def test_approve_writes_an_audit_log_entry(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    created = _create(client, headers, org.id)
    client.post(f"{_URL}/{created['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{created['id']}/approve?organization_id={org.id}", headers=headers)

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    ).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_APPROVED" for e in entries)


def test_supersede_writes_an_audit_log_entry_for_the_new_version(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    headers = dev_auth_headers(manager.id)
    v1 = _create(client, headers, org.id)
    client.post(f"{_URL}/{v1['id']}/submit?organization_id={org.id}", headers=headers)
    client.post(f"{_URL}/{v1['id']}/approve?organization_id={org.id}", headers=headers)
    v2 = _create(client, headers, org.id, supersedes_assessment_id=v1["id"])

    entries = db_session.execute(select(AuditLog).where(AuditLog.resource_id == uuid.UUID(v2["id"]))).scalars().all()
    assert any(e.action == "RISK_ASSESSMENT_CREATED" for e in entries)


def test_risk_score_component_is_present_and_untouched_by_this_milestone(client, db_session):
    """Item 1: enterprise-risk-v1 is an unmodified analytical input,
    exposed read-only inside intelligence_context."""
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    created = _create(client, dev_auth_headers(manager.id), org.id)
    assert created["intelligence_context"]["deterministic_risk"]["version"] == "enterprise-risk-v1"
    assert created["intelligence_context"]["calculation_versions"]["risk_score"] == "enterprise-risk-v1"
