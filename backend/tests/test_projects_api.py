"""SIE Milestone 35: Organizational & Operational Scope Foundation v0.1
— HTTP-layer tests for `/api/v1/projects` and the `operational_scope`
addition to `GET /api/v1/intelligence/context` /
`GET /api/v1/intelligence/sites/{site_id}/context`. Mirrors
`tests/test_intelligence_decisions_api.py`'s own established shape:
runs against the ordinary SQLite `client` fixture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_safety_event
from tests.test_ingestion_api import create_org, make_membership, make_user

AS_OF = datetime.now(timezone.utc)


def _make_org_and_manager(client, db_session, role="HSE_MANAGER"):
    org = create_org(client)
    user = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role=role)
    return org, user, dev_auth_headers(user.id)


def _create_project(client, org_id, headers, **overrides):
    body = {"name": "Warehouse Expansion", "code": "PRJ-001"}
    body.update(overrides)
    return client.post(f"/api/v1/projects?organization_id={org_id}", json=body, headers=headers)


def _create_site(client, org_id, name="Main Yard"):
    # sites.py is unauthenticated legacy tooling (see its own module) --
    # used here purely to stand up fixture data, unrelated to this
    # milestone's own auth surface.
    return client.post(f"/api/v1/organizations/{org_id}/sites", json={"name": name}).json()


# --- Authorization -------------------------------------------------------------------------


def test_create_project_requires_authentication(client):
    response = client.post(f"/api/v1/projects?organization_id={uuid.uuid4()}", json={"name": "X"})
    assert response.status_code == 401


def test_create_project_rejects_a_human_with_no_membership(client, db_session):
    org = create_org(client)
    user = make_user(db_session, "outsider@example.com")
    response = client.post(
        f"/api/v1/projects?organization_id={org['id']}", json={"name": "X"}, headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 403


def test_viewer_cannot_create_a_project(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session, role="VIEWER")
    response = _create_project(client, org["id"], headers)
    assert response.status_code == 403


def test_viewer_can_list_projects(client, db_session):
    org, manager, manager_headers = _make_org_and_manager(client, db_session)
    _create_project(client, org["id"], manager_headers)
    viewer = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")
    response = client.get(f"/api/v1/projects?organization_id={org['id']}", headers=dev_auth_headers(viewer.id))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_hse_manager_can_create_and_retrieve_a_project(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    create_response = _create_project(client, org["id"], headers, name="Regional Maintenance Program")
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    assert body["name"] == "Regional Maintenance Program"
    assert body["status"] == "ACTIVE"
    assert body["organization_id"] == org["id"]

    get_response = client.get(f"/api/v1/projects/{body['id']}?organization_id={org['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


def test_machine_client_with_scope_can_create_a_project(client, db_session):
    from app.services.api_client_service import api_client_service

    org = create_org(client)
    credential = api_client_service.create(
        db_session, organization_id=uuid.UUID(org["id"]), name="Integration",
        scopes=[Permission.PROJECT_MANAGE, Permission.PROJECT_READ],
    )
    headers = {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}
    response = _create_project(client, org["id"], headers)
    assert response.status_code == 201, response.text


def test_machine_client_without_scope_is_rejected(client, db_session):
    from app.services.api_client_service import api_client_service

    org = create_org(client)
    credential = api_client_service.create(
        db_session, organization_id=uuid.UUID(org["id"]), name="Read Only", scopes=[Permission.INTELLIGENCE_READ]
    )
    headers = {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}
    response = _create_project(client, org["id"], headers)
    assert response.status_code == 403


# --- Tenant isolation ----------------------------------------------------------------------


def test_organization_a_cannot_read_organization_bs_projects(client, db_session):
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    created = _create_project(client, org_b["id"], headers_b).json()

    response = client.get(f"/api/v1/projects/{created['id']}?organization_id={org_a['id']}", headers=headers_a)
    assert response.status_code == 404

    list_response = client.get(f"/api/v1/projects?organization_id={org_a['id']}", headers=headers_a)
    assert list_response.json()["total"] == 0


def test_organization_a_cannot_create_a_relationship_involving_organization_bs_site(client, db_session):
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    project_a = _create_project(client, org_a["id"], headers_a).json()
    site_b = _create_site(client, org_b["id"])

    response = client.post(
        f"/api/v1/projects/{project_a['id']}/sites?organization_id={org_a['id']}",
        json={"site_id": site_b["id"]},
        headers=headers_a,
    )
    assert response.status_code == 404


def test_organization_a_cannot_associate_its_project_with_organization_bs_project_via_cross_org_id(client, db_session):
    """A project id belonging to a different organization cannot be
    read, listed, or targeted for a relationship at all -- always 404."""
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    project_b = _create_project(client, org_b["id"], headers_b).json()
    site_a = _create_site(client, org_a["id"])

    response = client.post(
        f"/api/v1/projects/{project_b['id']}/sites?organization_id={org_a['id']}",
        json={"site_id": site_a["id"]},
        headers=headers_a,
    )
    assert response.status_code == 404


# --- Project/Site relationship management ---------------------------------------------------


def test_link_and_list_sites_for_a_project(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])

    link_response = client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]},
        headers=headers,
    )
    assert link_response.status_code == 201, link_response.text
    assert link_response.json()["id"] == site["id"]

    list_response = client.get(f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}", headers=headers)
    assert list_response.status_code == 200
    assert [s["id"] for s in list_response.json()] == [site["id"]]


def test_a_project_may_span_multiple_sites_over_http(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site_1 = _create_site(client, org["id"], "Site One")
    site_2 = _create_site(client, org["id"], "Site Two")

    for site in (site_1, site_2):
        response = client.post(
            f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
            json={"site_id": site["id"]}, headers=headers,
        )
        assert response.status_code == 201

    list_response = client.get(f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}", headers=headers)
    assert {s["id"] for s in list_response.json()} == {site_1["id"], site_2["id"]}


def test_a_site_may_host_multiple_projects_over_http(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    site = _create_site(client, org["id"])
    project_1 = _create_project(client, org["id"], headers, name="Project One").json()
    project_2 = _create_project(client, org["id"], headers, name="Project Two").json()

    for project in (project_1, project_2):
        response = client.post(
            f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
            json={"site_id": site["id"]}, headers=headers,
        )
        assert response.status_code == 201

    reverse_response = client.get(f"/api/v1/projects/by-site/{site['id']}?organization_id={org['id']}", headers=headers)
    assert reverse_response.status_code == 200
    assert {p["id"] for p in reverse_response.json()} == {project_1["id"], project_2["id"]}


def test_unlink_a_site_from_a_project(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])
    client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]}, headers=headers,
    )

    unlink_response = client.delete(
        f"/api/v1/projects/{project['id']}/sites/{site['id']}?organization_id={org['id']}", headers=headers
    )
    assert unlink_response.status_code == 204

    list_response = client.get(f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}", headers=headers)
    assert list_response.json() == []


def test_unlinking_a_site_that_was_never_linked_is_404(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])
    response = client.delete(
        f"/api/v1/projects/{project['id']}/sites/{site['id']}?organization_id={org['id']}", headers=headers
    )
    assert response.status_code == 404


def test_linking_the_same_site_twice_returns_the_same_relationship(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])

    first = client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]}, headers=headers,
    )
    second = client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]}, headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    list_response = client.get(f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}", headers=headers)
    assert len(list_response.json()) == 1


# --- Field Intelligence Context operational_scope integration (SIE Milestone 35, item 10) ----


def _seed_events(client_db, org_id, *, count=3):
    for i in range(count):
        client_db.add(
            make_safety_event(
                organization_id=org_id, event_type="INCIDENT", event_time=AS_OF - timedelta(days=i),
                ingestion_time=AS_OF - timedelta(days=i), source_record_id=str(uuid.uuid4()),
            )
        )
    client_db.commit()


def test_context_without_project_id_has_no_operational_scope(client, db_session):
    """Backward compatibility (item 11): a pre-M35 caller never supplies
    `project_id`, and the response is unaffected."""
    org, user, headers = _make_org_and_manager(client, db_session)
    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["operational_scope"] is None


def test_organization_context_with_project_id_labels_the_response(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers, name="Regional Program").json()
    site = _create_site(client, org["id"])
    client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]}, headers=headers,
    )

    response = client.get(
        f"/api/v1/intelligence/context?organization_id={org['id']}&project_id={project['id']}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operational_scope"]["level"] == "ORGANIZATION"
    assert body["operational_scope"]["project"]["id"] == project["id"]
    assert body["operational_scope"]["project"]["site_ids"] == [site["id"]]
    assert body["operational_scope"]["site"] is None


def test_site_context_with_project_id_labels_both_site_and_project(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])
    client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site["id"]}, headers=headers,
    )

    response = client.get(
        f"/api/v1/intelligence/sites/{site['id']}/context?organization_id={org['id']}&project_id={project['id']}",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operational_scope"]["level"] == "SITE"
    assert body["operational_scope"]["site"]["id"] == site["id"]
    assert body["operational_scope"]["project"]["id"] == project["id"]


def test_site_context_rejects_a_project_not_associated_with_that_site(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])
    # Deliberately never linked.
    response = client.get(
        f"/api/v1/intelligence/sites/{site['id']}/context?organization_id={org['id']}&project_id={project['id']}",
        headers=headers,
    )
    assert response.status_code == 400


def test_context_with_a_project_id_from_a_different_organization_is_404(client, db_session):
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    project_b = _create_project(client, org_b["id"], headers_b).json()

    response = client.get(
        f"/api/v1/intelligence/context?organization_id={org_a['id']}&project_id={project_b['id']}", headers=headers_a
    )
    assert response.status_code == 404


def test_operational_scope_project_site_ids_reflects_current_not_historical_membership(client, db_session):
    """SIE Milestone 35 item 7: `ProjectSite` carries no point-in-time
    history. A historical `as_of` request's `operational_scope.project
    .site_ids` reflects TODAY's relationships -- proven here by linking
    a second site *after* the first context call and confirming the
    second call (same historical `as_of`) picks it up."""
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site_1 = _create_site(client, org["id"], "Site One")
    client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site_1["id"]}, headers=headers,
    )

    # historical_as_of's ISO timezone offset ("+00:00") contains a raw
    # "+" -- passed via `params=` (not f-string-embedded) so httpx
    # percent-encodes it correctly (see tests/test_intelligence_decisions_api.py's
    # own established fix for the identical gotcha).
    historical_as_of = (AS_OF - timedelta(days=90)).isoformat()
    first = client.get(
        "/api/v1/intelligence/context",
        params={"organization_id": org["id"], "project_id": project["id"], "as_of": historical_as_of},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["operational_scope"]["project"]["site_ids"] == [site_1["id"]]

    site_2 = _create_site(client, org["id"], "Site Two")
    client.post(
        f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
        json={"site_id": site_2["id"]}, headers=headers,
    )

    second = client.get(
        "/api/v1/intelligence/context",
        params={"organization_id": org["id"], "project_id": project["id"], "as_of": historical_as_of},
        headers=headers,
    )
    assert {site_1["id"], site_2["id"]} == set(second.json()["operational_scope"]["project"]["site_ids"])
