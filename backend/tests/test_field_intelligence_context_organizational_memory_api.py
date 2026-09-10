"""SIE Milestone 41A: Learning Integration Corrective — HTTP-layer
tests for the new `organizational_memory` field on
`GET /api/v1/intelligence/context` and
`GET /api/v1/intelligence/sites/{site_id}/context`. Mirrors `tests/
test_field_intelligence_context_api.py`'s own established shape
(runs against the ordinary SQLite `client` fixture) and reuses
`tests.test_memory_integration_api._setup_active_memory()` verbatim --
the identical full HTTP chain (decision -> outcome -> verification ->
ACCEPTED candidate -> memory) M41's own HTTP suite already established,
never a second, parallel fixture.

Covers the M41A spec's checklist items that are specifically HTTP-layer
concerns: cross-tenant isolation over the wire (20), machine-credential
tenant binding (21), human authorized-organization selection (22), and
that the pre-existing decision memory-context endpoint remains reachable
and correct alongside the new context field (23/24). Items 1-19/25/26
are covered at the composition layer by `tests/test_context_composition_
organizational_memory.py`.
"""

from __future__ import annotations

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_ingestion_api import create_org, make_membership, make_user
from tests.test_memory_integration_api import (
    _decision_memory_context_url,
    _retract_memory,
    _setup_active_memory,
)


def _make_client_credential(db_session, org_id, *, scopes=None):
    scopes = scopes if scopes is not None else [Permission.INTELLIGENCE_READ]
    return api_client_service.create(db_session, organization_id=org_id, name="Test Integration", scopes=scopes)


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def test_context_endpoint_includes_organizational_memory_for_an_authorized_member(db_session, client):
    org, _user, headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "member@example.com")

    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "organizational_memory" in body
    assert body["organizational_memory"]["outcome"] == "OK"
    memory_ids = {item["memory_id"] for item in body["organizational_memory"]["items"]}
    assert memory["id"] in memory_ids
    # Never merged into the four pre-existing categories.
    assert "organizational_memory" not in body["observed"]
    assert "organizational_memory" not in body["deterministic"]
    assert "organizational_memory" not in body["predictive"]
    assert "organizational_memory" not in body["knowledge"]


def test_context_endpoint_never_leaks_another_organizations_memory(db_session, client):
    org_a, _user, headers_a, _decision, _outcome, memory_a = _setup_active_memory(
        client, db_session, "org-a-member@example.com"
    )
    org_b = make_org(db_session, name="Org B")
    user_b = make_user(db_session, "org-b-member@example.com")
    make_membership(db_session, user_id=user_b.id, organization_id=org_b.id, role="VIEWER")

    response = client.get(f"/api/v1/intelligence/context?organization_id={org_b.id}", headers=dev_auth_headers(user_b.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organizational_memory"]["items"] == []

    # Sanity: org A's own context still shows its own memory (proves the
    # empty result above is real isolation, not merely a broken query).
    response_a = client.get(f"/api/v1/intelligence/context?organization_id={org_a['id']}", headers=headers_a)
    memory_ids_a = {item["memory_id"] for item in response_a.json()["organizational_memory"]["items"]}
    assert memory_a["id"] in memory_ids_a


def test_context_endpoint_machine_credential_cannot_reach_another_organizations_memory(db_session, client):
    """Item 21: a machine credential is bound to its own `organization_id`
    at the same `authorize_context()` layer every other M32/M33/M41
    endpoint in this router already uses -- no new tenant-selection
    mechanism was introduced for `organizational_memory`."""
    org_a, _user, _headers, _decision, _outcome, _memory = _setup_active_memory(
        client, db_session, "org-a-member-2@example.com"
    )
    org_b = make_org(db_session, name="Org B Machine")
    credential_b = _make_client_credential(db_session, org_b.id)

    response = client.get(f"/api/v1/intelligence/context?organization_id={org_a['id']}", headers=_bearer(credential_b))
    assert response.status_code == 403


def test_context_endpoint_machine_credential_with_read_scope_sees_its_own_memory(db_session, client):
    org, _user, _headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "member-3@example.com")
    credential = _make_client_credential(db_session, uuid.UUID(org["id"]))

    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=_bearer(credential))
    assert response.status_code == 200, response.text
    memory_ids = {item["memory_id"] for item in response.json()["organizational_memory"]["items"]}
    assert memory["id"] in memory_ids


def test_decision_memory_context_endpoint_still_reachable_alongside_new_context_field(db_session, client):
    """Items 23/24: M41's own pre-existing decision-traceability endpoint
    (`GET /intelligence/decisions/{id}/memory-context`) is untouched by
    M41A and remains reachable -- a decision's own memory-context never
    incorrectly includes a memory produced after its own
    `intelligence_as_of` (that memory is itself the *result* of this
    same decision's downstream outcome/verification/candidate chain, so
    it necessarily postdates the decision)."""
    org, _user, headers, decision, _outcome, memory = _setup_active_memory(client, db_session, "member-4@example.com")

    response = client.get(f"{_decision_memory_context_url(decision['id'])}?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200, response.text
    memory_ids = {item["memory_id"] for item in response.json()["items"]}
    assert memory["id"] not in memory_ids


def test_retracted_memory_excluded_from_context_endpoint_over_http(db_session, client):
    org, _user, headers, _decision, _outcome, memory = _setup_active_memory(client, db_session, "member-5@example.com")
    _retract_memory(client, org["id"], headers, memory["id"])

    response = client.get(f"/api/v1/intelligence/context?organization_id={org['id']}", headers=headers)
    assert response.status_code == 200, response.text
    memory_ids = {item["memory_id"] for item in response.json()["organizational_memory"]["items"]}
    assert memory["id"] not in memory_ids
