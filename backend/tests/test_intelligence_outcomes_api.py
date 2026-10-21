"""Outcomes/Verification API -- human-only writers.

Outcome and Verification records are human-authored only (owner
decision, 2026-10-21; `sie-contract` 0.7.0). Both write routes refuse a
machine (API-client) caller with 403 before reaching Commercial Core,
even when that caller holds `INTELLIGENCE_DECISION_WRITE`. A permitted
human caller still reaches the stub and gets 501, and read routes are
unchanged for both identity kinds.
"""

from __future__ import annotations

import uuid

from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.test_ingestion_api import create_org, make_membership, make_user
from tests.test_intelligence_api import _bearer, _make_client_credential

WRITE_ROUTES = ("/api/v1/intelligence/outcomes", "/api/v1/intelligence/outcomes/{outcome_id}/verifications")


def _write_path(route: str, org_id: str) -> str:
    return route.format(outcome_id=uuid.uuid4()) + f"?organization_id={org_id}"


def test_machine_caller_with_write_scope_is_refused_on_both_write_routes(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_DECISION_WRITE])

    for route in WRITE_ROUTES:
        response = client.post(_write_path(route, org["id"]), json={}, headers=_bearer(credential))
        assert response.status_code == 403, route
        assert "human user" in response.json()["detail"], route


def test_human_caller_with_write_permission_still_reaches_the_stub(client, db_session):
    org = create_org(client)
    user = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN")

    for route in WRITE_ROUTES:
        response = client.post(_write_path(route, org["id"]), json={}, headers=dev_auth_headers(user.id))
        assert response.status_code == 501, route


def test_human_caller_without_membership_gets_the_normal_permission_403(client, db_session):
    org = create_org(client)
    user = make_user(db_session, f"{uuid.uuid4().hex}@example.com")

    response = client.post(_write_path(WRITE_ROUTES[0], org["id"]), json={}, headers=dev_auth_headers(user.id))
    assert response.status_code == 403
    assert "human user" not in response.json()["detail"]


def test_machine_caller_without_write_scope_gets_the_normal_permission_403(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.post(_write_path(WRITE_ROUTES[0], org["id"]), json={}, headers=_bearer(credential))
    assert response.status_code == 403
    assert "missing scope" in response.json()["detail"]


def test_machine_caller_can_still_use_read_routes(client, db_session):
    org = create_org(client)
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]), scopes=[Permission.INTELLIGENCE_READ])

    response = client.get(f"/api/v1/intelligence/outcomes?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 501


def test_openapi_documents_the_human_only_writer_rule(client):
    schema = client.get("/openapi.json").json()
    for path in ("/api/v1/intelligence/outcomes", "/api/v1/intelligence/outcomes/{outcome_id}/verifications"):
        forbidden = schema["paths"][path]["post"]["responses"]["403"]["description"]
        assert "human user" in forbidden, path
    tag = next(t for t in schema["tags"] if t["name"] == "intelligence-outcomes")
    assert "human user" in tag["description"]
