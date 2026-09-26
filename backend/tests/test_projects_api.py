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


# M43-IP-03: "Field Intelligence Context operational_scope integration"
# (5 tests) removed -- they verified project/site linkage correctness
# exclusively via `GET /intelligence/context`'s `operational_scope`
# field, and that endpoint's computation was extracted to the private
# Commercial Core repository. See docs/M43_IP_03_PUBLIC_EXTRACTION.md's
# "Test coverage regressions" section.


# --- SafetyEvent <-> Project attribution (SIE Milestone 35A) -----------------------------------


def _seed_one_event(db_session, org_id, *, site_id=None):
    event = make_safety_event(
        organization_id=org_id, site_id=site_id, event_type="INCIDENT",
        event_time=AS_OF, ingestion_time=AS_OF, source_record_id=str(uuid.uuid4()),
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_attribute_event_to_project_over_http(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    event = _seed_one_event(db_session, uuid.UUID(org["id"]))

    response = client.put(
        f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["attributed_project_id"] == project["id"]


def test_attributing_an_event_requires_project_manage_not_just_read(client, db_session):
    org, manager, manager_headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], manager_headers).json()
    event = _seed_one_event(db_session, uuid.UUID(org["id"]))
    viewer = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER")

    response = client.put(
        f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}",
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_attribute_event_to_project_404s_for_a_cross_tenant_event(client, db_session):
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    project_a = _create_project(client, org_a["id"], headers_a).json()
    event_b = _seed_one_event(db_session, uuid.UUID(org_b["id"]))

    response = client.put(
        f"/api/v1/projects/{project_a['id']}/events/{event_b.id}?organization_id={org_a['id']}", headers=headers_a
    )
    assert response.status_code == 404


def test_attribute_event_to_project_404s_for_a_cross_tenant_project(client, db_session):
    org_a, user_a, headers_a = _make_org_and_manager(client, db_session)
    org_b, user_b, headers_b = _make_org_and_manager(client, db_session)
    project_b = _create_project(client, org_b["id"], headers_b).json()
    event_a = _seed_one_event(db_session, uuid.UUID(org_a["id"]))

    response = client.put(
        f"/api/v1/projects/{project_b['id']}/events/{event_a.id}?organization_id={org_a['id']}", headers=headers_a
    )
    assert response.status_code == 404


def test_attribute_event_to_project_422s_when_the_project_is_not_associated_with_the_events_site(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    site = _create_site(client, org["id"])
    # Deliberately never linked.
    event = _seed_one_event(db_session, uuid.UUID(org["id"]), site_id=uuid.UUID(site["id"]))

    response = client.put(
        f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert response.status_code == 422


def test_clear_event_project_attribution_over_http_then_second_call_404s(client, db_session):
    """SIE Milestone 35B correction: a repeat DELETE, with nothing left
    to clear, now 404s rather than silently re-succeeding (M35A's
    original "always idempotent" framing is deliberately narrowed --
    see app/services/safety_event_project_service.py's own docstring)."""
    org, user, headers = _make_org_and_manager(client, db_session)
    project = _create_project(client, org["id"], headers).json()
    event = _seed_one_event(db_session, uuid.UUID(org["id"]))
    client.put(f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}", headers=headers)

    first = client.delete(
        f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert first.status_code == 204
    second = client.delete(
        f"/api/v1/projects/{project['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert second.status_code == 404

    detail = client.get(f"/api/v1/events/{event.id}?organization_id={org['id']}", headers=headers)
    assert detail.json()["attributed_project_id"] is None


def test_clear_event_project_attribution_over_http_rejects_a_mismatched_project(client, db_session):
    """SIE Milestone 35B's own correctness fix: DELETE via a project the
    event is not currently attributed to is rejected, not silently
    accepted."""
    org, user, headers = _make_org_and_manager(client, db_session)
    project_alpha = _create_project(client, org["id"], headers, name="Alpha", code="ALPHA").json()
    project_beta = _create_project(client, org["id"], headers, name="Beta", code="BETA").json()
    event = _seed_one_event(db_session, uuid.UUID(org["id"]))
    client.put(
        f"/api/v1/projects/{project_alpha['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )

    response = client.delete(
        f"/api/v1/projects/{project_beta['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert response.status_code == 404

    detail = client.get(f"/api/v1/events/{event.id}?organization_id={org['id']}", headers=headers)
    assert detail.json()["attributed_project_id"] == project_alpha["id"]


def test_list_project_events_returns_only_attributed_events(client, db_session):
    org, user, headers = _make_org_and_manager(client, db_session)
    project_alpha = _create_project(client, org["id"], headers, name="Project Alpha", code="ALPHA").json()
    project_beta = _create_project(client, org["id"], headers, name="Project Beta", code="BETA").json()
    event_alpha = _seed_one_event(db_session, uuid.UUID(org["id"]))
    event_beta = _seed_one_event(db_session, uuid.UUID(org["id"]))
    event_unattributed = _seed_one_event(db_session, uuid.UUID(org["id"]))
    client.put(
        f"/api/v1/projects/{project_alpha['id']}/events/{event_alpha.id}?organization_id={org['id']}",
        headers=headers,
    )
    client.put(
        f"/api/v1/projects/{project_beta['id']}/events/{event_beta.id}?organization_id={org['id']}", headers=headers
    )

    response = client.get(f"/api/v1/projects/{project_alpha['id']}/events?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [e["id"] for e in body["items"]] == [str(event_alpha.id)]
    assert str(event_beta.id) not in [e["id"] for e in body["items"]]
    assert str(event_unattributed.id) not in [e["id"] for e in body["items"]]


def test_two_projects_at_the_same_site_do_not_both_claim_an_events_attribution_over_http(client, db_session):
    """The user's own explicitly required scenario, at the HTTP layer:
    Site X hosts both Project Alpha and Project Beta. Attributing an
    event at Site X to Alpha must not cause it to also appear under
    Beta's event listing."""
    org, user, headers = _make_org_and_manager(client, db_session)
    site_x = _create_site(client, org["id"], "Site X")
    project_alpha = _create_project(client, org["id"], headers, name="Project Alpha", code="ALPHA").json()
    project_beta = _create_project(client, org["id"], headers, name="Project Beta", code="BETA").json()
    for project in (project_alpha, project_beta):
        client.post(
            f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
            json={"site_id": site_x["id"]}, headers=headers,
        )
    event = _seed_one_event(db_session, uuid.UUID(org["id"]), site_id=uuid.UUID(site_x["id"]))

    attribute_response = client.put(
        f"/api/v1/projects/{project_alpha['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
    )
    assert attribute_response.status_code == 200, attribute_response.text

    alpha_events = client.get(
        f"/api/v1/projects/{project_alpha['id']}/events?organization_id={org['id']}", headers=headers
    ).json()
    beta_events = client.get(
        f"/api/v1/projects/{project_beta['id']}/events?organization_id={org['id']}", headers=headers
    ).json()
    assert [e["id"] for e in alpha_events["items"]] == [str(event.id)]
    assert beta_events["items"] == []



# M43-IP-03: the 3 tests formerly in "Field Intelligence Context genuine
# project filtering" (test_project_scoped_context_genuinely_filters_event_count_not_merely_labels_it,
# test_project_scoped_context_is_point_in_time_correct_across_a_reassignment,
# test_operational_scope_project_site_ids_is_point_in_time_correct_after_m36)
# removed -- they verified project/site operational-scope correctness
# exclusively by asserting on `GET /intelligence/context`'s response
# shape, and that endpoint's computation (app.intelligence.context_composition)
# was extracted to the private Commercial Core repository. The
# project/site attribution logic itself they were exercising
# (app.services.project_site_service, app.intelligence.temporal) is
# unchanged and still public; only the HTTP-level verification path
# through the now-removed intelligence endpoint is gone. Not rewritten
# against a different endpoint in this milestone -- see
# docs/M43_IP_03_PUBLIC_EXTRACTION.md's "Test coverage regressions"
# section. A future milestone should re-verify this behavior either at
# the service layer directly or against a genuine Commercial Core client
# integration.
