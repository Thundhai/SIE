"""SIE Milestone 43A: Organizational Standards & Governance Foundation —
HTTP-layer tests for `app/api/v1/governing_standards.py`. Mirrors
`tests/test_organizational_memory_api.py`'s own established shape: runs
against the ordinary SQLite `client` fixture, exercises authorization,
tenant isolation, validation, happy path, and failure cases over the
wire.
"""

from __future__ import annotations

import uuid

from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard import GoverningStandard
from app.models.governing_standard_enums import GoverningStandardType
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member
from tests.test_ingestion_api import create_org_source


def _make_global_standard(db_session, *, name="ISO 45001", regions=None, industry_sectors=None):
    standard = GoverningStandard(
        scope_type=ScopeType.GLOBAL,
        organization_id=None,
        name=name,
        short_description="Occupational health and safety management systems.",
        issuing_organization="ISO",
        standard_type=GoverningStandardType.INTERNATIONAL_STANDARD,
        regions=regions or [],
        industry_sectors=industry_sectors or [],
        verification_status=VerificationStatus.VERIFIED,
        is_active=True,
    )
    db_session.add(standard)
    db_session.commit()
    return standard


def _make_org_standard(db_session, organization_id, *, name="ABC Energy HSE Standard 2026"):
    standard = GoverningStandard(
        scope_type=ScopeType.ORGANIZATION,
        organization_id=organization_id,
        name=name,
        short_description="ABC Energy's own internal HSE standard.",
        issuing_organization="ABC Energy",
        standard_type=GoverningStandardType.ORGANIZATION_SPECIFIC,
        regions=[],
        industry_sectors=[],
        verification_status=VerificationStatus.PENDING,
        is_active=True,
    )
    db_session.add(standard)
    db_session.commit()
    return standard


_STANDARDS_URL = "/api/v1/governing-standards"
_SELECTIONS_URL = "/api/v1/organization-governing-standards"


# --- Catalogue: GET/POST authorization + validation + happy path -----------------------------


def test_list_available_standards_requires_authentication(client, db_session):
    org = make_org(db_session)
    _make_global_standard(db_session)

    response = client.get(f"{_STANDARDS_URL}?organization_id={org.id}")
    assert response.status_code in (401, 403)


def test_list_available_standards_returns_global_and_own_organization_standards(client, db_session):
    org = make_org(db_session)
    member = make_org_member(db_session, org.id, role="HSE_MANAGER")
    _make_global_standard(db_session, name="ISO 45001")
    _make_org_standard(db_session, org.id, name="ABC Energy HSE Standard 2026")

    response = client.get(f"{_STANDARDS_URL}?organization_id={org.id}", headers=dev_auth_headers(member.id))
    assert response.status_code == 200, response.text
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"ISO 45001", "ABC Energy HSE Standard 2026"}


def test_viewer_role_can_read_but_not_manage_standards(client, db_session):
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role="VIEWER")
    _make_global_standard(db_session)

    read_response = client.get(f"{_STANDARDS_URL}?organization_id={org.id}", headers=dev_auth_headers(viewer.id))
    assert read_response.status_code == 200

    create_response = client.post(
        f"{_STANDARDS_URL}?organization_id={org.id}",
        json={
            "name": "Viewer's Standard",
            "short_description": "desc",
            "issuing_organization": "Org",
            "standard_type": "ORGANIZATION_SPECIFIC",
        },
        headers=dev_auth_headers(viewer.id),
    )
    assert create_response.status_code == 403


def test_create_organization_standard_happy_path(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")

    response = client.post(
        f"{_STANDARDS_URL}?organization_id={org.id}",
        json={
            "name": "ABC Energy HSE Standard 2026",
            "short_description": "ABC Energy's own internal HSE standard.",
            "issuing_organization": "ABC Energy",
            "standard_type": "ORGANIZATION_SPECIFIC",
            "regions": ["US"],
            "industry_sectors": ["OIL_GAS"],
        },
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scope_type"] == "ORGANIZATION"
    assert body["organization_id"] == str(org.id)
    assert body["name"] == "ABC Energy HSE Standard 2026"
    assert body["regions"] == ["US"]


def test_create_organization_standard_validation_failure(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")

    response = client.post(
        f"{_STANDARDS_URL}?organization_id={org.id}",
        json={"name": "", "short_description": "", "issuing_organization": "", "standard_type": "ORGANIZATION_SPECIFIC"},
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 422


def test_create_organization_standard_links_a_real_knowledge_source(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")
    source = create_org_source(client, db_session, str(org.id))

    response = client.post(
        f"{_STANDARDS_URL}?organization_id={org.id}",
        json={
            "name": "ABC Energy HSE Standard 2026",
            "short_description": "desc",
            "issuing_organization": "ABC Energy",
            "standard_type": "ORGANIZATION_SPECIFIC",
            "knowledge_source_id": source["id"],
        },
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 201, response.text
    assert response.json()["knowledge_source_id"] == source["id"]


def test_get_one_standard_not_found_for_another_organization(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_org_member(db_session, org_a.id, role="HSE_MANAGER")
    b_standard = _make_org_standard(db_session, org_b.id)

    response = client.get(
        f"{_STANDARDS_URL}/{b_standard.id}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )
    assert response.status_code == 404


# --- Organization selection: happy path, multiple, duplicate, retire, history ----------------


def test_select_and_retire_a_governing_standard_end_to_end(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")
    standard = _make_global_standard(db_session)

    select_response = client.post(
        f"{_SELECTIONS_URL}?organization_id={org.id}",
        json={"standard_id": str(standard.id), "rationale": "Adopted per contractual requirement."},
        headers=dev_auth_headers(manager.id),
    )
    assert select_response.status_code == 201, select_response.text
    assert select_response.json()["status"] == "SELECTED"

    active_response = client.get(f"{_SELECTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(manager.id))
    assert active_response.status_code == 200
    active_items = active_response.json()["items"]
    assert len(active_items) == 1
    assert active_items[0]["standard"]["id"] == str(standard.id)

    retire_response = client.post(
        f"{_SELECTIONS_URL}/{standard.id}/retire?organization_id={org.id}",
        json={"rationale": "No longer applicable."},
        headers=dev_auth_headers(manager.id),
    )
    assert retire_response.status_code == 201, retire_response.text
    assert retire_response.json()["status"] == "RETIRED"

    after_retire = client.get(f"{_SELECTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(manager.id))
    assert after_retire.json()["items"] == []


def test_selecting_multiple_standards(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")
    iso = _make_global_standard(db_session, name="ISO 45001")
    osha = _make_global_standard(db_session, name="OSHA 1910")

    for standard in (iso, osha):
        response = client.post(
            f"{_SELECTIONS_URL}?organization_id={org.id}",
            json={"standard_id": str(standard.id)},
            headers=dev_auth_headers(manager.id),
        )
        assert response.status_code == 201, response.text

    active = client.get(f"{_SELECTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(manager.id)).json()
    assert len(active["items"]) == 2


def test_duplicate_selection_returns_the_same_event_not_a_new_one(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")
    standard = _make_global_standard(db_session)

    first = client.post(
        f"{_SELECTIONS_URL}?organization_id={org.id}",
        json={"standard_id": str(standard.id)},
        headers=dev_auth_headers(manager.id),
    )
    second = client.post(
        f"{_SELECTIONS_URL}?organization_id={org.id}",
        json={"standard_id": str(standard.id)},
        headers=dev_auth_headers(manager.id),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    history = client.get(f"{_SELECTIONS_URL}/history?organization_id={org.id}", headers=dev_auth_headers(manager.id))
    assert history.json()["total"] == 1


def test_hse_analyst_cannot_modify_governance(client, db_session):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role="HSE_ANALYST")
    standard = _make_global_standard(db_session)

    response = client.post(
        f"{_SELECTIONS_URL}?organization_id={org.id}",
        json={"standard_id": str(standard.id)},
        headers=dev_auth_headers(analyst.id),
    )
    assert response.status_code == 403

    # But HSE_ANALYST can still read.
    read_response = client.get(f"{_SELECTIONS_URL}?organization_id={org.id}", headers=dev_auth_headers(analyst.id))
    assert read_response.status_code == 200


def test_selecting_an_unknown_standard_id_is_404(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")

    response = client.post(
        f"{_SELECTIONS_URL}?organization_id={org.id}",
        json={"standard_id": str(uuid.uuid4())},
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 404


def test_retiring_a_never_selected_standard_is_422(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")
    standard = _make_global_standard(db_session)

    response = client.post(
        f"{_SELECTIONS_URL}/{standard.id}/retire?organization_id={org.id}",
        json={},
        headers=dev_auth_headers(manager.id),
    )
    assert response.status_code == 422


# --- Tenant isolation --------------------------------------------------------------------------


def test_organization_a_cannot_read_organization_bs_selections(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_org_member(db_session, org_a.id, role="HSE_MANAGER")
    member_b = make_org_member(db_session, org_b.id, role="HSE_MANAGER")
    standard = _make_global_standard(db_session)

    client.post(
        f"{_SELECTIONS_URL}?organization_id={org_b.id}",
        json={"standard_id": str(standard.id)},
        headers=dev_auth_headers(member_b.id),
    )

    # member_a is not authorized to even query with org_b's organization_id.
    response = client.get(f"{_SELECTIONS_URL}?organization_id={org_b.id}", headers=dev_auth_headers(member_a.id))
    assert response.status_code == 403

    # member_a's own org has no selections of its own.
    own_response = client.get(f"{_SELECTIONS_URL}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id))
    assert own_response.json()["items"] == []


def test_organization_a_cannot_modify_organization_bs_selections(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_org_member(db_session, org_a.id, role="HSE_MANAGER")
    standard = _make_global_standard(db_session)

    response = client.post(
        f"{_SELECTIONS_URL}?organization_id={org_b.id}",
        json={"standard_id": str(standard.id)},
        headers=dev_auth_headers(member_a.id),
    )
    assert response.status_code == 403


def test_organization_a_cannot_access_organization_bs_own_standard_document(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_org_member(db_session, org_a.id, role="HSE_MANAGER")
    b_standard = _make_org_standard(db_session, org_b.id)

    # Neither reachable via GET by id...
    get_response = client.get(
        f"{_STANDARDS_URL}/{b_standard.id}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )
    assert get_response.status_code == 404

    # ...nor selectable.
    select_response = client.post(
        f"{_SELECTIONS_URL}?organization_id={org_a.id}",
        json={"standard_id": str(b_standard.id)},
        headers=dev_auth_headers(member_a.id),
    )
    assert select_response.status_code == 404

    # ...nor does it leak into org A's own available-standards listing.
    list_response = client.get(f"{_STANDARDS_URL}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id))
    assert b_standard.name not in {item["name"] for item in list_response.json()["items"]}
