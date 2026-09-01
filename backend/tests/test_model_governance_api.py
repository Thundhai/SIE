"""Model governance API — Model Validation & Governance v0.1, item 48.
HTTP-level tests against the ordinary SQLite `client` fixture, mirroring
`tests/test_predictions_api.py`'s own pattern.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.membership_service import membership_service
from app.services.permissions import OrganizationRole
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers
from tests.fixtures.predictions.synthetic_training_dataset import (
    DEFAULT_NUM_DAYS,
    DEFAULT_START,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org, make_safety_event


def _seed_exposure_hours(db_session, org, sites, *, num_days: int = DEFAULT_NUM_DAYS) -> None:
    """`check_minimum_requirements()`'s `minimum_exposure_coverage` check
    (app/predictions/data_requirements.py) needs at least one WORKFORCE/
    EXPOSURE_HOURS record per site -- `seed_synthetic_organization()`
    itself deliberately doesn't create any (it's a predictive-features
    fixture, not an exposure one), so tests that need a genuinely
    trainable dataset add their own here, mirroring
    `tests/fixtures/intelligence/synthetic_dataset.py`'s own
    WORKFORCE/EXPOSURE_HOURS shape."""
    for site in sites:
        for month in range(0, num_days, 30):
            db_session.add(
                make_safety_event(
                    organization_id=org.id,
                    site_id=site.id,
                    event_type="WORKFORCE",
                    event_subtype="EXPOSURE_HOURS",
                    event_time=DEFAULT_START + timedelta(days=month),
                    attributes={"hours": 1000},
                    source_record_id=str(uuid.uuid4()),
                )
            )
    db_session.commit()


def _make_user(db_session, organization_id, role):
    user = user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name="U"))
    membership_service.create(
        db_session, organization_id=organization_id, obj_in=OrganizationMembershipCreate(user_id=user.id, role=role)
    )
    return user


def _dataset_body(dataset_id: str, *, num_days: int = DEFAULT_NUM_DAYS, environment: str = "SYNTHETIC", source_systems=None):
    return {
        "dataset_id": dataset_id,
        "environment": environment,
        "date_range_start": DEFAULT_START.isoformat(),
        "date_range_end": (DEFAULT_START + timedelta(days=num_days)).isoformat(),
        "source_systems": source_systems,
    }


def _register_dataset(
    client, db_session, *, site_names=("Site 1", "Site 2"), num_days: int = DEFAULT_NUM_DAYS, seed: int = 1, with_exposure: bool = True
):
    org, sites = seed_synthetic_organization(db_session, name=f"Gov Org {uuid.uuid4().hex[:8]}", site_names=list(site_names), seed=seed, num_days=num_days)
    if with_exposure:
        _seed_exposure_hours(db_session, org, sites, num_days=num_days)
    admin = _make_user(db_session, org.id, OrganizationRole.ORG_ADMIN)
    response = client.post(
        f"/api/v1/intelligence/datasets/validate?organization_id={org.id}",
        json=_dataset_body(f"ds-{uuid.uuid4().hex[:8]}", num_days=num_days),
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 200, response.text
    return org, admin, response.json()


# --- Authentication / authorization -----------------------------------------------------


def test_train_requires_authentication(client, db_session):
    org = make_org(db_session)
    response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


def test_train_requires_governance_manage_not_just_governance_read(client, db_session):
    org = make_org(db_session)
    viewer = _make_user(db_session, org.id, OrganizationRole.VIEWER)  # GOVERNANCE_READ, not GOVERNANCE_MANAGE
    response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": str(uuid.uuid4())},
        headers=dev_auth_headers(viewer.id),
    )
    assert response.status_code == 403


def test_hse_user_has_neither_governance_permission(client, db_session):
    org = make_org(db_session)
    hse_user = _make_user(db_session, org.id, OrganizationRole.HSE_USER)  # neither governance permission
    response = client.get(
        f"/api/v1/intelligence/datasets?organization_id={org.id}",
        headers=dev_auth_headers(hse_user.id),
    )
    assert response.status_code == 403


def test_viewer_can_read_but_not_manage_datasets(client, db_session):
    org = make_org(db_session)
    viewer = _make_user(db_session, org.id, OrganizationRole.VIEWER)
    read_response = client.get(
        f"/api/v1/intelligence/datasets?organization_id={org.id}",
        headers=dev_auth_headers(viewer.id),
    )
    assert read_response.status_code == 200

    manage_response = client.post(
        f"/api/v1/intelligence/datasets/validate?organization_id={org.id}",
        json=_dataset_body("blocked-ds"),
        headers=dev_auth_headers(viewer.id),
    )
    assert manage_response.status_code == 403


# --- Datasets ----------------------------------------------------------------------------


def test_validate_synthetic_dataset_then_list_and_get(client, db_session):
    org, admin, body = _register_dataset(client, db_session)
    assert body["environment"] == "SYNTHETIC"
    assert body["dataset_version"] == "v1"
    assert body["record_count"] > 0
    assert "overall_quality" in body["quality_report"]

    list_response = client.get(f"/api/v1/intelligence/datasets?organization_id={org.id}", headers=dev_auth_headers(admin.id))
    assert list_response.status_code == 200
    assert any(row["id"] == body["id"] for row in list_response.json())

    get_response = client.get(
        f"/api/v1/intelligence/datasets/{body['id']}?organization_id={org.id}", headers=dev_auth_headers(admin.id)
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


def test_validate_real_dataset_requires_source_systems(client, db_session):
    org, _sites = seed_synthetic_organization(db_session, name="Real Org", site_names=["Site 1"], seed=2)
    admin = _make_user(db_session, org.id, OrganizationRole.ORG_ADMIN)
    response = client.post(
        f"/api/v1/intelligence/datasets/validate?organization_id={org.id}",
        json=_dataset_body("real-ds", environment="REAL", source_systems=None),
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422


def test_validate_real_dataset_succeeds_with_source_systems(client, db_session):
    org, _sites = seed_synthetic_organization(db_session, name="Real Org 2", site_names=["Site 1"], seed=3)
    admin = _make_user(db_session, org.id, OrganizationRole.ORG_ADMIN)
    response = client.post(
        f"/api/v1/intelligence/datasets/validate?organization_id={org.id}",
        json=_dataset_body("real-ds-2", environment="REAL", source_systems=["safelytic"]),
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 200
    assert response.json()["environment"] == "REAL"
    assert response.json()["source_systems"] == ["safelytic"]


def test_get_dataset_404s_for_a_dataset_in_a_different_organization(client, db_session):
    _org_a, _admin_a, body = _register_dataset(client, db_session, seed=4)
    org_b = make_org(db_session, "Other Org")
    admin_b = _make_user(db_session, org_b.id, OrganizationRole.ORG_ADMIN)

    response = client.get(
        f"/api/v1/intelligence/datasets/{body['id']}?organization_id={org_b.id}", headers=dev_auth_headers(admin_b.id)
    )
    assert response.status_code == 404


# --- Models: insufficient data ------------------------------------------------------------


def test_train_returns_422_insufficient_data_for_a_too_small_dataset(client, db_session):
    org, admin, body = _register_dataset(client, db_session, site_names=("Only Site",), num_days=30, seed=5, with_exposure=False)
    response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": body["id"]},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "INSUFFICIENT_DATA" in detail["message"]
    assert len(detail["failed_checks"]) > 0


# --- Full model lifecycle -----------------------------------------------------------------


def test_full_model_lifecycle_via_the_api(client, db_session):
    org, admin, dataset_body = _register_dataset(client, db_session, seed=6)
    org_id = org.id

    train_response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org_id}",
        json={"dataset_version_id": dataset_body["id"], "model_type": "logistic_regression"},
        headers=dev_auth_headers(admin.id),
    )
    assert train_response.status_code == 200, train_response.text
    model = train_response.json()
    assert model["status"] == "TRAINED"
    assert model["dataset_version_id"] == dataset_body["id"]
    assert model["calibration_validated"] is False
    model_id = model["id"]

    # A client cannot supply metrics/calibration/status -- only what
    # training.py itself computed server-side is ever present here.
    assert "test" in model["metrics"]
    assert "calibration" in model["metrics"]["test"]

    # Deploying before approval is an invalid transition, not a silent no-op.
    early_deploy = client.post(
        f"/api/v1/intelligence/models/{model_id}/deploy?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert early_deploy.status_code == 400

    validate_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/validate?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["status"] == "VALIDATED"

    card_before_approval = client.get(
        f"/api/v1/intelligence/models/{model_id}/card?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert card_before_approval.status_code == 200
    assert card_before_approval.json()["status"] == "VALIDATED"

    report_response = client.get(
        f"/api/v1/intelligence/models/{model_id}/validation-report?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["recommendation"] in ("APPROVE", "REJECT", "REVIEW")
    assert report["model_id"] == model_id

    approve_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/approve?organization_id={org_id}",
        json={"notes": "prototype pipeline check"},
        headers=dev_auth_headers(admin.id),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPROVED"

    deploy_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/deploy?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert deploy_response.status_code == 200
    assert deploy_response.json()["status"] == "DEPLOYED"

    monitoring_response = client.get(
        f"/api/v1/intelligence/models/{model_id}/monitoring?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert monitoring_response.status_code == 200
    monitoring = monitoring_response.json()
    assert "prediction_monitoring" in monitoring
    assert "performance_monitoring" in monitoring

    undeploy_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/undeploy?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert undeploy_response.status_code == 200
    assert undeploy_response.json()["status"] == "APPROVED"

    # Rollback: redeploy the same, previously-approved version.
    redeploy_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/deploy?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert redeploy_response.status_code == 200
    assert redeploy_response.json()["status"] == "DEPLOYED"

    retire_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/retire?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert retire_response.status_code == 200
    assert retire_response.json()["status"] == "RETIRED"

    # Retirement never deletes history -- the model row and its lifecycle
    # remain retrievable.
    get_response = client.get(
        f"/api/v1/intelligence/models/{model_id}?organization_id={org_id}", headers=dev_auth_headers(admin.id)
    )
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "RETIRED"

    list_response = client.get(f"/api/v1/intelligence/models?organization_id={org_id}", headers=dev_auth_headers(admin.id))
    assert list_response.status_code == 200
    assert any(m["id"] == model_id for m in list_response.json())


def test_reject_model_records_a_reason_and_never_lets_it_deploy(client, db_session):
    org, admin, dataset_body = _register_dataset(client, db_session, seed=7)
    train_response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": dataset_body["id"]},
        headers=dev_auth_headers(admin.id),
    )
    model_id = train_response.json()["id"]
    client.post(f"/api/v1/intelligence/models/{model_id}/validate?organization_id={org.id}", headers=dev_auth_headers(admin.id))

    reject_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/reject?organization_id={org.id}",
        json={"reason": "PR-AUC too low for this prototype's purposes"},
        headers=dev_auth_headers(admin.id),
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "REJECTED"

    deploy_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/deploy?organization_id={org.id}", headers=dev_auth_headers(admin.id)
    )
    assert deploy_response.status_code == 400


def test_reject_requires_a_reason(client, db_session):
    org, admin, dataset_body = _register_dataset(client, db_session, seed=8)
    train_response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": dataset_body["id"]},
        headers=dev_auth_headers(admin.id),
    )
    model_id = train_response.json()["id"]

    response = client.post(
        f"/api/v1/intelligence/models/{model_id}/reject?organization_id={org.id}",
        json={},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422  # RejectModelRequest.reason is required


def test_train_rejects_an_unrecognized_hyperparameter(client, db_session):
    org, admin, dataset_body = _register_dataset(client, db_session, seed=9)
    response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org.id}",
        json={"dataset_version_id": dataset_body["id"], "hyperparameters": {"not_a_real_hyperparameter": 1.0}},
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422


# --- Tenant isolation ----------------------------------------------------------------------


def test_get_model_404s_for_a_model_in_a_different_organization(client, db_session):
    org_a, admin_a, dataset_body = _register_dataset(client, db_session, seed=10)
    train_response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org_a.id}",
        json={"dataset_version_id": dataset_body["id"]},
        headers=dev_auth_headers(admin_a.id),
    )
    model_id = train_response.json()["id"]

    org_b = make_org(db_session, "Other Org")
    admin_b = _make_user(db_session, org_b.id, OrganizationRole.ORG_ADMIN)

    get_response = client.get(
        f"/api/v1/intelligence/models/{model_id}?organization_id={org_b.id}", headers=dev_auth_headers(admin_b.id)
    )
    assert get_response.status_code == 404

    card_response = client.get(
        f"/api/v1/intelligence/models/{model_id}/card?organization_id={org_b.id}", headers=dev_auth_headers(admin_b.id)
    )
    assert card_response.status_code == 404

    monitoring_response = client.get(
        f"/api/v1/intelligence/models/{model_id}/monitoring?organization_id={org_b.id}", headers=dev_auth_headers(admin_b.id)
    )
    assert monitoring_response.status_code == 404

    approve_response = client.post(
        f"/api/v1/intelligence/models/{model_id}/approve?organization_id={org_b.id}",
        json={},
        headers=dev_auth_headers(admin_b.id),
    )
    assert approve_response.status_code == 404


def test_list_models_never_returns_another_organizations_models(client, db_session):
    org_a, admin_a, dataset_a = _register_dataset(client, db_session, site_names=("Site A",), seed=11)
    client.post(
        f"/api/v1/intelligence/models/train?organization_id={org_a.id}",
        json={"dataset_version_id": dataset_a["id"]},
        headers=dev_auth_headers(admin_a.id),
    )

    org_b, admin_b, _dataset_b = _register_dataset(client, db_session, site_names=("Site B",), seed=12)

    list_response = client.get(f"/api/v1/intelligence/models?organization_id={org_b.id}", headers=dev_auth_headers(admin_b.id))
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_train_404s_for_a_dataset_version_in_a_different_organization(client, db_session):
    _org_a, _admin_a, dataset_a = _register_dataset(client, db_session, seed=13)
    org_b = make_org(db_session, "Other Org B")
    admin_b = _make_user(db_session, org_b.id, OrganizationRole.ORG_ADMIN)

    response = client.post(
        f"/api/v1/intelligence/models/train?organization_id={org_b.id}",
        json={"dataset_version_id": dataset_a["id"]},
        headers=dev_auth_headers(admin_b.id),
    )
    assert response.status_code == 404
