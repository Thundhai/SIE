"""Audit logging for every governance event — Model Validation &
Governance v0.1, item 47's own list: dataset validation; model
training/validation/approval/deployment/retirement; prediction
generated/abstained; model review required.

`tests/test_predictions_governance.py::test_record_validation_report_writes_an_audit_log_entry`
already covers `MODEL_VALIDATION_REPORT_GENERATED`, and
`tests/test_predictions_predictor.py`/`test_predictions_api.py` already
exercise `PREDICTION_GENERATED`/`PREDICTION_ABSTAINED` incidentally --
this file is the one place every *other* governance `AuditAction` is
checked directly against a real `AuditLog` row, and the one place
that checks, across all of them together, that no audit metadata ever
carries a feature value, a raw event payload, or anything else beyond
small identifiers/labels/statuses (item 47's "never log sensitive
feature values unnecessarily")."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.audit_log import AuditLog
from app.predictions import dataset_registry, model_registry
from app.predictions.dataset import build_training_examples
from app.predictions.drift import acknowledge_review_flag, check_model_for_review
from app.predictions.enums import DatasetEnvironment, ReviewFlagReason
from app.predictions.enums import PredictionOutcome as PredictionOutcomeEnum
from app.predictions.outcome_tracking import evaluate_prediction_outcome
from app.predictions.predictor import predict_as_of
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    DEFAULT_START,
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org, make_reviewer_user

# Every governance audit action's metadata must be a JSON-flat mapping of
# scalars (or short lists of scalar identifiers, e.g. failed-check names)
# -- never a nested feature vector, coefficient list, or raw event payload.
_ALLOWED_METADATA_VALUE_TYPES = (str, int, float, bool, type(None))


def _assert_metadata_is_flat_and_scalar_only(metadata: dict) -> None:
    for key, value in metadata.items():
        if isinstance(value, list):
            assert all(isinstance(item, _ALLOWED_METADATA_VALUE_TYPES) for item in value), (
                f"metadata[{key!r}] is a list containing a non-scalar element -- looks like a feature "
                f"vector or nested payload, not an identifier/label list: {value!r}"
            )
        else:
            assert isinstance(value, _ALLOWED_METADATA_VALUE_TYPES), (
                f"metadata[{key!r}] is a {type(value).__name__}, not a flat scalar -- "
                f"a governance audit log must never carry a nested/raw payload: {value!r}"
            )


def _one_audit_log(db_session, *, action: str, resource_id) -> AuditLog:
    return db_session.query(AuditLog).filter_by(resource_id=resource_id, action=action).one()


def _bare_model_entry(db_session, org, *, name="audit-log-model"):
    """A minimal `ModelRegistryEntry`, no real training run -- mirrors
    `tests/test_predictions_drift.py`'s own pattern; these tests only
    care about the audit trail around status transitions, not about
    actual model quality."""
    return model_registry.create_model_entry(
        db_session, organization_id=org.id, model_name=name, model_type="logistic_regression",
        entity_type="site", prediction_target_version="v1", label_definition_version="v1",
        feature_set_version="v1", training_data_version="v1", horizon_days=30,
        training_period_start=date(2026, 1, 1), training_period_end=date(2026, 2, 1),
        validation_period_start=date(2026, 2, 2), validation_period_end=date(2026, 3, 1),
        test_period_start=date(2026, 3, 2), test_period_end=date(2026, 4, 1),
        hyperparameters={}, metrics={}, parameters={},
    )


def _deployed_model(db_session, *, seed=900):
    org, sites = seed_synthetic_organization(db_session, name="Audit Org", site_names=["S1"], seed=seed)
    dates = as_of_dates()
    examples = build_training_examples(db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    return org, sites[0], entry, dates


def test_dataset_validated_is_audit_logged(db_session):
    org, _sites = seed_synthetic_organization(db_session, name="Dataset Audit Org", site_names=["S1"], seed=901, num_days=200)
    dv = dataset_registry.register_dataset(
        db_session, organization_id=org.id, dataset_id="audit-ds", environment=DatasetEnvironment.SYNTHETIC,
        date_range_start=DEFAULT_START, date_range_end=DEFAULT_START + timedelta(days=200),
        source_systems=["synthetic-fixture"],
    )
    logged = _one_audit_log(db_session, action="DATASET_VALIDATED", resource_id=dv.id)
    assert logged.organization_id == org.id
    assert logged.resource_type == "dataset_version"
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)
    assert logged.event_metadata["dataset_id"] == "audit-ds"


def test_model_approved_is_audit_logged_and_names_the_reviewer(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id, notes="looks fine")

    logged = _one_audit_log(db_session, action="MODEL_APPROVED", resource_id=entry.id)
    assert logged.organization_id == org.id
    assert logged.user_id == reviewer.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)
    assert logged.event_metadata["reviewer_user_id"] == str(reviewer.id)


def test_model_rejected_is_audit_logged(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.reject(db_session, entry, reviewer_user_id=reviewer.id, reason="poor calibration")

    logged = _one_audit_log(db_session, action="MODEL_REJECTED", resource_id=entry.id)
    assert logged.organization_id == org.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)


def test_model_deployed_is_audit_logged(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)

    logged = _one_audit_log(db_session, action="MODEL_DEPLOYED", resource_id=entry.id)
    assert logged.organization_id == org.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)


def test_model_undeployed_is_audit_logged(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    entry = model_registry.undeploy(db_session, entry)

    logged = _one_audit_log(db_session, action="MODEL_UNDEPLOYED", resource_id=entry.id)
    assert logged.organization_id == org.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)


def test_model_retired_is_audit_logged(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.approve(db_session, entry, reviewer_user_id=reviewer.id)
    entry = model_registry.deploy(db_session, entry)
    entry = model_registry.retire(db_session, entry)

    logged = _one_audit_log(db_session, action="MODEL_RETIRED", resource_id=entry.id)
    assert logged.organization_id == org.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)


def test_model_review_required_is_audit_logged_without_leaking_feature_values(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)

    flag = check_model_for_review(
        db_session, entry, reason=ReviewFlagReason.PERFORMANCE_DRIFT, metric_name="recall",
        historical_value=0.8, current_value=0.4, threshold=0.15,
    )
    assert flag is not None

    logged = _one_audit_log(db_session, action="MODEL_REVIEW_REQUIRED", resource_id=flag.id)
    assert logged.organization_id == org.id
    assert logged.resource_type == "model_review_flag"
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)
    assert set(logged.event_metadata) == {"model_id", "reason", "metric_name", "historical_value", "current_value"}


def test_model_review_acknowledged_is_audit_logged(db_session):
    org = make_org(db_session)
    entry = _bare_model_entry(db_session, org)
    flag = check_model_for_review(
        db_session, entry, reason=ReviewFlagReason.PERFORMANCE_DRIFT, metric_name="recall",
        historical_value=0.8, current_value=0.4, threshold=0.15,
    )
    reviewer = make_reviewer_user(db_session)
    flag = acknowledge_review_flag(db_session, flag, user_id=reviewer.id)

    logged = _one_audit_log(db_session, action="MODEL_REVIEW_ACKNOWLEDGED", resource_id=flag.id)
    assert logged.organization_id == org.id
    assert logged.user_id == reviewer.id
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)


def test_prediction_outcome_evaluated_is_audit_logged(db_session):
    org, site, model, dates = _deployed_model(db_session)
    as_of = dates[len(dates) // 2]
    prediction = predict_as_of(db_session, organization_id=org.id, site_id=site.id, as_of=as_of, model=model)
    assert prediction.outcome == PredictionOutcomeEnum.PREDICTED.value

    matured = prediction.prediction_time + timedelta(days=prediction.horizon_days + 1)
    outcome = evaluate_prediction_outcome(db_session, prediction_id=prediction.id, as_of_now=matured)
    assert outcome is not None

    logged = _one_audit_log(db_session, action="PREDICTION_OUTCOME_EVALUATED", resource_id=outcome.id)
    assert logged.organization_id == org.id
    assert logged.resource_type == "prediction_outcome"
    _assert_metadata_is_flat_and_scalar_only(logged.event_metadata)
    # actual_label/predicted_risk_category are the outcome's own summary
    # fields, never the underlying feature snapshot or event content.
    assert set(logged.event_metadata) == {"prediction_id", "actual_label", "predicted_risk_category"}
