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


# --- Field Intelligence Context genuine project filtering (SIE Milestone 35A) ------------------


def test_project_scoped_context_genuinely_filters_event_count_not_merely_labels_it(client, db_session):
    """M35A's own central requirement: `event_count` differs between two
    projects at the same site based on explicit attribution, not merely
    a shared `operational_scope` label wrapping identical site-wide
    numbers (M35's original gap)."""
    org, user, headers = _make_org_and_manager(client, db_session)
    site = _create_site(client, org["id"])
    project_alpha = _create_project(client, org["id"], headers, name="Project Alpha", code="ALPHA").json()
    project_beta = _create_project(client, org["id"], headers, name="Project Beta", code="BETA").json()
    for project in (project_alpha, project_beta):
        client.post(
            f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
            json={"site_id": site["id"]}, headers=headers,
        )

    site_uuid = uuid.UUID(site["id"])
    org_uuid = uuid.UUID(org["id"])
    alpha_events = [
        make_safety_event(
            organization_id=org_uuid, site_id=site_uuid, event_type="INCIDENT",
            event_time=AS_OF - timedelta(days=i), ingestion_time=AS_OF - timedelta(days=i),
            source_record_id=str(uuid.uuid4()),
        )
        for i in range(3)
    ]
    beta_event = make_safety_event(
        organization_id=org_uuid, site_id=site_uuid, event_type="INCIDENT",
        event_time=AS_OF, ingestion_time=AS_OF, source_record_id=str(uuid.uuid4()),
    )
    for event in [*alpha_events, beta_event]:
        db_session.add(event)
    db_session.commit()
    for event in alpha_events:
        db_session.refresh(event)
    db_session.refresh(beta_event)

    for event in alpha_events:
        client.put(
            f"/api/v1/projects/{project_alpha['id']}/events/{event.id}?organization_id={org['id']}", headers=headers
        )
    client.put(
        f"/api/v1/projects/{project_beta['id']}/events/{beta_event.id}?organization_id={org['id']}", headers=headers
    )

    alpha_context = client.get(
        "/api/v1/intelligence/context",
        params={"organization_id": org["id"], "project_id": project_alpha["id"]}, headers=headers,
    ).json()
    beta_context = client.get(
        "/api/v1/intelligence/context",
        params={"organization_id": org["id"], "project_id": project_beta["id"]}, headers=headers,
    ).json()
    site_wide_context = client.get(
        "/api/v1/intelligence/context", params={"organization_id": org["id"]}, headers=headers
    ).json()

    assert alpha_context["observed"]["event_count"] == 3
    assert beta_context["observed"]["event_count"] == 1
    assert site_wide_context["observed"]["event_count"] == 4
    assert alpha_context["operational_scope"]["project"]["filtered"] is True
    assert set(alpha_context["observed"]["evidence_sample_event_ids"]) == {str(e.id) for e in alpha_events}
    assert beta_context["observed"]["evidence_sample_event_ids"] == [str(beta_event.id)]


def test_project_scoped_context_is_point_in_time_correct_across_a_reassignment(client, db_session):
    """SIE Milestone 35B, end-to-end through the real
    GET /intelligence/context pipeline (not just events_as_of() in
    isolation): an event attributed to Alpha on June 20, reassigned to
    Beta on June 25, must still show up in Alpha's `event_count` for an
    `as_of` of June 23 (before the reassignment) and disappear from it
    for an `as_of` of June 26 (after) -- while Beta's context shows the
    opposite. History rows are written directly (backdating `created_at`
    -- the real PUT/DELETE routes always use `utcnow()` and cannot be
    backdated over HTTP) to simulate the two calls having actually
    happened on those two dates."""
    from app.models.safety_event_project_attribution_history import (
        SafetyEventProjectAttributionAction,
        SafetyEventProjectAttributionHistory,
    )

    org, user, headers = _make_org_and_manager(client, db_session)
    site = _create_site(client, org["id"])
    project_alpha = _create_project(client, org["id"], headers, name="Alpha", code="ALPHA").json()
    project_beta = _create_project(client, org["id"], headers, name="Beta", code="BETA").json()
    for project in (project_alpha, project_beta):
        client.post(
            f"/api/v1/projects/{project['id']}/sites?organization_id={org['id']}",
            json={"site_id": site["id"]}, headers=headers,
        )

    org_uuid = uuid.UUID(org["id"])
    site_uuid = uuid.UUID(site["id"])
    event_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    event = make_safety_event(
        organization_id=org_uuid, site_id=site_uuid, event_type="INCIDENT",
        event_time=event_time, ingestion_time=event_time, source_record_id=str(uuid.uuid4()),
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    db_session.add(
        SafetyEventProjectAttributionHistory(
            organization_id=org_uuid, event_id=event.id, project_id=uuid.UUID(project_alpha["id"]),
            action=SafetyEventProjectAttributionAction.ATTRIBUTED,
            created_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        SafetyEventProjectAttributionHistory(
            organization_id=org_uuid, event_id=event.id, project_id=uuid.UUID(project_beta["id"]),
            action=SafetyEventProjectAttributionAction.ATTRIBUTED,
            created_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    def context(project_id, as_of_day):
        response = client.get(
            "/api/v1/intelligence/context",
            params={
                "organization_id": org["id"], "project_id": project_id,
                "as_of": datetime(2026, 6, as_of_day, tzinfo=timezone.utc).isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert context(project_alpha["id"], 23)["observed"]["event_count"] == 1
    assert context(project_alpha["id"], 26)["observed"]["event_count"] == 0
    assert context(project_beta["id"], 26)["observed"]["event_count"] == 1
    assert context(project_beta["id"], 23)["observed"]["event_count"] == 0


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
