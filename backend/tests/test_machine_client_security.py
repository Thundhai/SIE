"""Machine-client security — Intelligence Platform Integration &
Enterprise API v0.1, item 39's own checklist, walked end to end over
plain HTTP: invalid credential, revoked credential, expired credential,
wrong scope, wrong organization, missing auth header, malformed auth
header, credential rotation, least privilege.

`POST /api/v1/intelligence/events` (requires `Permission.SAFETY_DATA_WRITE`)
is used as the representative protected route throughout, since it needs
no response-shape stubbing (unlike RAG/retrieval) and no seeded model
(unlike predictions) -- the auth/scope pipeline under test
(`app/api/deps_machine_auth.py`) is identical on every machine-client
route, per that module's own docstring.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_ingestion_api import create_org, make_membership, make_user

_EVENTS_URL = "/api/v1/intelligence/events"


def _event_payload(source_record_id: str = "rec-1") -> dict:
    return {
        "event_type": "NEAR_MISS",
        "event_time": "2026-01-01T00:00:00Z",
        "source_system": "test",
        "source_record_id": source_record_id,
    }


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _org_admin(client, db_session, org_id: str):
    admin = make_user(db_session, f"{uuid.uuid4().hex}@example.com")
    make_membership(db_session, user_id=admin.id, organization_id=uuid.UUID(org_id), role="ORG_ADMIN")
    return admin


# --- Missing / malformed Authorization header --------------------------------------------


def test_missing_authorization_header_is_rejected(client):
    response = client.post(_EVENTS_URL, json=_event_payload())
    assert response.status_code == 401


def test_authorization_header_without_bearer_scheme_is_rejected(client):
    response = client.post(_EVENTS_URL, json=_event_payload(), headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_bearer_credential_without_a_colon_separator_is_rejected(client):
    response = client.post(_EVENTS_URL, json=_event_payload(), headers={"Authorization": "Bearer not-a-valid-token"})
    assert response.status_code == 401


def test_empty_bearer_token_is_rejected(client):
    response = client.post(_EVENTS_URL, json=_event_payload(), headers={"Authorization": "Bearer "})
    assert response.status_code == 401


# --- Invalid credential -------------------------------------------------------------------


def test_unknown_client_id_is_rejected(client):
    response = client.post(
        _EVENTS_URL, json=_event_payload(), headers={"Authorization": "Bearer sie_doesnotexist:whatever-secret"}
    )
    assert response.status_code == 401


def test_wrong_secret_for_a_real_client_id_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(
        _EVENTS_URL,
        json=_event_payload(),
        headers={"Authorization": f"Bearer {credential.client_id}:wrong-secret"},
    )
    assert response.status_code == 401


# --- Revoked credential -------------------------------------------------------------------


def test_revoked_credential_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    api_client_service.revoke(db_session, api_client=credential.api_client)

    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 401


# --- Expired credential -------------------------------------------------------------------


def test_expired_credential_is_rejected(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session,
        organization_id=org.id,
        name="Client",
        scopes=[Permission.SAFETY_DATA_WRITE],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 401


def test_a_credential_with_a_future_expiry_still_authenticates(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session,
        organization_id=org.id,
        name="Client",
        scopes=[Permission.SAFETY_DATA_WRITE],
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 200


def test_a_credential_with_no_expiry_never_expires(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 200


# --- Wrong scope (least privilege) ---------------------------------------------------------


def test_credential_without_the_required_scope_is_denied(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Read-only client", scopes=[Permission.SAFETY_DATA_READ]
    )
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 403


def test_credential_with_no_scopes_at_all_is_denied(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(db_session, organization_id=org.id, name="Scopeless client", scopes=[])
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 403


def test_least_privilege_a_client_scoped_only_for_writes_cannot_read_analytics(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Write-only client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    # Writing is fine -- it's the one thing this credential was granted.
    assert client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential)).status_code == 200
    # Reading analytics is not -- that scope was never granted.
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org.id}", headers=_bearer(credential)
    )
    assert response.status_code == 403


def test_least_privilege_a_client_scoped_only_for_reads_cannot_write_events(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Read-only client", scopes=[Permission.INTELLIGENCE_READ]
    )
    assert (
        client.get(
            f"/api/v1/intelligence/analytics/summary?organization_id={org.id}", headers=_bearer(credential)
        ).status_code
        == 200
    )
    response = client.post(_EVENTS_URL, json=_event_payload(), headers=_bearer(credential))
    assert response.status_code == 403


# --- Wrong organization --------------------------------------------------------------------


def test_credential_cannot_read_a_different_organizations_analytics_by_naming_it(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential = api_client_service.create(
        db_session, organization_id=org_a.id, name="Client", scopes=[Permission.INTELLIGENCE_READ]
    )
    response = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={org_b.id}", headers=_bearer(credential)
    )
    assert response.status_code == 403


# --- Credential rotation --------------------------------------------------------------------


def test_rotating_a_credential_over_http_invalidates_the_old_secret_and_activates_the_new_one(client, db_session):
    org = create_org(client, "Rotation Org")
    admin = _org_admin(client, db_session, org["id"])

    created = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Rotating Client", "scopes": [Permission.SAFETY_DATA_WRITE.value]},
        headers=dev_auth_headers(admin.id),
    ).json()
    old_headers = {"Authorization": f"Bearer {created['client_id']}:{created['secret']}"}
    assert client.post(_EVENTS_URL, json=_event_payload("before-rotation"), headers=old_headers).status_code == 200

    rotated = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients/{created['id']}/rotate",
        headers=dev_auth_headers(admin.id),
    ).json()
    # Same client identity and organization/scopes survive rotation --
    # only the secret changes (item 26's own requirement).
    assert rotated["client_id"] == created["client_id"]
    assert rotated["id"] == created["id"]
    assert rotated["scopes"] == created["scopes"]
    assert rotated["secret"] != created["secret"]

    # The old secret is now dead...
    assert client.post(_EVENTS_URL, json=_event_payload("after-rotation-old"), headers=old_headers).status_code == 401
    # ...and the new one works immediately, with no gap in org/scope association.
    new_headers = {"Authorization": f"Bearer {rotated['client_id']}:{rotated['secret']}"}
    assert (
        client.post(_EVENTS_URL, json=_event_payload("after-rotation-new"), headers=new_headers).status_code == 200
    )


def test_revoking_a_credential_over_http_stops_it_from_authenticating(client, db_session):
    org = create_org(client, "Revocation Org")
    admin = _org_admin(client, db_session, org["id"])

    created = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Revocable Client", "scopes": [Permission.SAFETY_DATA_WRITE.value]},
        headers=dev_auth_headers(admin.id),
    ).json()
    headers = {"Authorization": f"Bearer {created['client_id']}:{created['secret']}"}
    assert client.post(_EVENTS_URL, json=_event_payload("before-revoke"), headers=headers).status_code == 200

    revoke_response = client.post(
        f"/api/v1/organizations/{org['id']}/api-clients/{created['id']}/revoke",
        headers=dev_auth_headers(admin.id),
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "REVOKED"

    assert client.post(_EVENTS_URL, json=_event_payload("after-revoke"), headers=headers).status_code == 401


def test_api_client_management_endpoints_never_return_the_secret_on_list(client, db_session):
    org = create_org(client, "Listing Org")
    admin = _org_admin(client, db_session, org["id"])
    client.post(
        f"/api/v1/organizations/{org['id']}/api-clients",
        json={"name": "Listed Client", "scopes": [Permission.SAFETY_DATA_WRITE.value]},
        headers=dev_auth_headers(admin.id),
    )

    listing = client.get(f"/api/v1/organizations/{org['id']}/api-clients", headers=dev_auth_headers(admin.id)).json()
    assert len(listing) == 1
    assert "secret" not in listing[0]
    assert "hashed_secret" not in listing[0]
