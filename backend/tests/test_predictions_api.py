"""Predictions API — milestone items 31, 45. HTTP-level tests against the
ordinary SQLite `client` fixture."""

import uuid

from app.predictions import model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.training import train_baseline_model
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.membership_service import membership_service
from app.services.permissions import OrganizationRole
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org, make_reviewer_user, make_site


def _make_authorized_user(db_session, organization_id, role=OrganizationRole.HSE_MANAGER):
    user = user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name="U"))
    membership_service.create(
        db_session, organization_id=organization_id, obj_in=OrganizationMembershipCreate(user_id=user.id, role=role)
    )
    return user


def _deployed_model(db_session, *, seed=1):
    org, sites = seed_synthetic_organization(db_session, name="API Org", site_names=["Site 1"], seed=seed)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    return org, sites[0], entry, dates[-1]


def test_create_prediction_requires_authentication(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    response = client.post(f"/api/v1/intelligence/predictions?organization_id={org.id}", json={"entity_id": str(site.id)})
    assert response.status_code == 401


def test_create_prediction_requires_permission_in_the_target_organization(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    other_org = make_org(db_session, "Other Org")
    user = _make_authorized_user(db_session, other_org.id)  # authorized elsewhere, not here

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id)},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_prediction_404s_for_a_site_in_a_different_organization(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    site_in_other_org = make_site(db_session, other_org.id)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site_in_other_org.id)},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 404


def test_create_prediction_404s_for_a_nonexistent_site(client, db_session):
    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)
    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(uuid.uuid4())},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 404


def test_create_prediction_abstains_when_no_model_is_deployed(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id)},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "NO_PREDICTION"
    assert body["abstention_reason"] == "MODEL_UNAVAILABLE"
    assert body["risk_score"] is None
    assert body["probability"] is None


def test_create_prediction_never_accepts_a_client_supplied_risk_score_or_feature_value(client, db_session):
    """Milestone item 45: the request schema has no such field at all --
    a client attempting to inject one is simply ignored (extra fields
    dropped), never trusted."""
    org, site, _entry, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={
            "entity_id": str(site.id),
            "as_of": as_of.isoformat(),
            "risk_score": 0.99,
            "label": 1,
            "feature_values": {"incident_count_30d": 999},
        },
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    # The injected risk_score is never honored -- the server computed its
    # own from the actual, server-side feature snapshot.
    assert body["risk_score"] != 0.99


def test_create_prediction_returns_a_scored_prediction_with_safety_language(client, db_session):
    org, site, _entry, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "PREDICTED"
    assert body["risk_category"] in ("ELEVATED", "MODERATE", "LOW")
    assert "model estimate" in body["safety_language_note"].lower()
    assert body["probability"] is None  # calibration_validated=False in this fixture


def test_get_latest_prediction_returns_the_most_recent_recorded_prediction(client, db_session):
    org, site, _entry, as_of = _deployed_model(db_session)
    user = _make_authorized_user(db_session, org.id)

    create_response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    assert create_response.status_code == 200

    get_response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == create_response.json()["id"]


def test_get_latest_prediction_404s_when_nothing_has_been_recorded(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = _make_authorized_user(db_session, org.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 404


def test_get_latest_prediction_404s_for_a_site_in_a_different_organization(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    site_in_other_org = make_site(db_session, other_org.id)
    user = _make_authorized_user(db_session, org.id)

    response = client.get(
        f"/api/v1/intelligence/predictions/{site_in_other_org.id}?organization_id={org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 404
