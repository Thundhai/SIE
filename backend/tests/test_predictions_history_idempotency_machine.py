"""Predictions API — Intelligence Platform Integration & Enterprise API
v0.1: prediction history (item 18), Idempotency-Key support on
POST /predictions (item 12), and machine-client access (items 17, 36).
"""

import uuid

from app.models.prediction import Prediction
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_intelligence_api import _bearer, _make_client_credential
from tests.test_predictions_api import _deployed_model, _make_authorized_user


def test_history_returns_the_standard_envelope_with_predictions_newest_first(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    first = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    assert first.status_code == 200

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data", "status", "request_id", "timestamp", "data_quality", "provenance"}
    assert body["status"] == "SUCCESS"
    assert body["request_id"]  # a real, non-empty value
    assert body["provenance"]["entity_id"] == str(site.id)
    assert len(body["data"]) == 1
    assert body["data"][0]["entity_id"] == str(site.id)


def test_history_response_carries_the_x_request_id_header_too(client, db_session):
    org, site, _model, _as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_history_is_empty_but_not_an_error_for_an_entity_with_no_predictions_yet(client, db_session):
    org, site, _model, _as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_history_requires_authentication(client, db_session):
    org, site, _model, _as_of = _deployed_model(db_session)
    response = client.get(f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}")
    assert response.status_code == 401


def test_history_404s_for_a_site_in_a_different_organization(client, db_session):
    _org, site, _model, _as_of = _deployed_model(db_session)
    other_org = make_org(db_session, "Other Org")
    user = _make_authorized_user(db_session, other_org.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={other_org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 404


def test_history_respects_limit_and_offset(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)
    # A handful of distinct as_of dates all before the model's own
    # evaluation cutoff, each producing its own recorded Prediction row.
    from datetime import timedelta

    for i in range(3):
        client.post(
            f"/api/v1/intelligence/predictions?organization_id={org.id}",
            json={"entity_id": str(site.id), "as_of": (as_of - timedelta(days=i)).isoformat()},
            headers=dev_auth_headers(user.id),
        )

    page_1 = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}&limit=2&offset=0",
        headers=dev_auth_headers(user.id),
    ).json()
    page_2 = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}&limit=2&offset=2",
        headers=dev_auth_headers(user.id),
    ).json()
    assert len(page_1["data"]) == 2
    assert len(page_2["data"]) == 1
    assert {p["id"] for p in page_1["data"]}.isdisjoint({p["id"] for p in page_2["data"]})


# --- Idempotency-Key ------------------------------------------------------------------


def test_repeated_idempotency_key_with_the_same_body_replays_the_first_response(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)
    body = {"entity_id": str(site.id), "as_of": as_of.isoformat()}
    key = uuid.uuid4().hex

    first = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json=body,
        headers={**dev_auth_headers(user.id), "Idempotency-Key": key},
    )
    second = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json=body,
        headers={**dev_auth_headers(user.id), "Idempotency-Key": key},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    # The replay never re-ran predict_as_of() -- only one Prediction row
    # actually exists for this entity.
    count = db_session.query(Prediction).filter_by(organization_id=org.id, entity_id=site.id).count()
    assert count == 1


def test_repeated_idempotency_key_with_a_different_body_is_a_409_conflict(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)
    key = uuid.uuid4().hex

    first = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers={**dev_auth_headers(user.id), "Idempotency-Key": key},
    )
    assert first.status_code == 200

    conflicting = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id)},  # a materially different body -- as_of omitted
        headers={**dev_auth_headers(user.id), "Idempotency-Key": key},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_omitting_the_idempotency_key_never_triggers_replay_or_conflict_logic(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)
    body = {"entity_id": str(site.id), "as_of": as_of.isoformat()}

    first = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}", json=body, headers=dev_auth_headers(user.id)
    )
    second = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}", json=body, headers=dev_auth_headers(user.id)
    )
    assert first.status_code == 200
    assert second.status_code == 200


# --- Machine-client access -------------------------------------------------------------


def test_machine_client_with_prediction_read_scope_can_request_and_read_predictions(client, db_session):
    org, site, _model, as_of = _deployed_model(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.PREDICTION_READ])

    created = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=_bearer(credential),
    )
    assert created.status_code == 200

    fetched = client.get(
        f"/api/v1/intelligence/predictions/{site.id}?organization_id={org.id}", headers=_bearer(credential)
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created.json()["id"]

    history = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}", headers=_bearer(credential)
    )
    assert history.status_code == 200
    assert len(history.json()["data"]) == 1


def test_machine_client_without_prediction_read_scope_is_forbidden(client, db_session):
    org, site, _model, _as_of = _deployed_model(db_session)
    credential = _make_client_credential(db_session, org.id, scopes=[Permission.SAFETY_DATA_WRITE])

    response = client.get(f"/api/v1/intelligence/predictions/{site.id}?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 403


def test_machine_client_cannot_override_its_organization_to_read_another_tenants_predictions(client, db_session):
    org, site, _model, _as_of = _deployed_model(db_session)
    other_org = make_org(db_session, "Other Org")
    credential = _make_client_credential(db_session, other_org.id, scopes=[Permission.PREDICTION_READ])

    # A valid, active credential -- just for a different organization
    # than the one it's asking about (item 36).
    response = client.get(f"/api/v1/intelligence/predictions/{site.id}?organization_id={org.id}", headers=_bearer(credential))
    assert response.status_code == 403
