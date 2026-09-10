"""Data drift, feature drift, and model performance drift — Model
Validation & Governance v0.1, items 29-32. Pure unit tests for the
statistical helpers; DB-backed tests for `check_model_for_review()`/
`acknowledge_review_flag()` (which persist `ModelReviewFlag` rows)."""

import random

from app.models.model_review_flag import ModelReviewFlag
from app.predictions.drift import (
    acknowledge_review_flag,
    check_model_for_review,
    compute_data_drift,
    compute_feature_drift,
    compute_psi,
)
from app.predictions.enums import ReviewFlagReason
from tests.intelligence_test_helpers import make_org, make_reviewer_user


def test_psi_is_near_zero_for_two_samples_from_the_same_distribution():
    random.seed(0)
    baseline = [random.gauss(5, 1) for _ in range(200)]
    same = [random.gauss(5, 1) for _ in range(200)]
    psi = compute_psi(baseline, same)
    assert psi is not None
    assert psi < 0.1


def test_psi_is_large_for_two_clearly_different_samples():
    random.seed(0)
    baseline = [random.gauss(5, 1) for _ in range(200)]
    shifted = [random.gauss(15, 1) for _ in range(200)]
    psi = compute_psi(baseline, shifted)
    assert psi is not None
    assert psi > 0.25


def test_psi_is_none_for_too_small_a_sample():
    assert compute_psi([1.0, 2.0], [1.0, 2.0]) is None


def test_compute_feature_drift_flags_only_the_features_that_actually_shifted():
    random.seed(0)
    baseline = [{"a": random.gauss(5, 1), "b": random.gauss(5, 1)} for _ in range(300)]
    current = [{"a": random.gauss(5, 1), "b": random.gauss(50, 1)} for _ in range(300)]
    report = compute_feature_drift(baseline, current, feature_names=("a", "b"))
    by_name = {r.feature_name: r for r in report.results}
    assert by_name["b"].status == "SIGNIFICANT_SHIFT"
    assert by_name["a"].status == "STABLE"


def test_compute_data_drift_flags_a_sharp_event_frequency_change():
    result = compute_data_drift(
        baseline_record_count=30, baseline_period_days=30, current_record_count=300, current_period_days=30
    )
    assert result.status == "SHIFTED"
    assert result.frequency_ratio == 10.0


def test_compute_data_drift_reports_stable_for_a_similar_rate():
    result = compute_data_drift(
        baseline_record_count=30, baseline_period_days=30, current_record_count=33, current_period_days=30
    )
    assert result.status == "STABLE"


def test_check_model_for_review_creates_a_flag_on_a_real_performance_drop(db_session):
    from datetime import date

    from app.predictions import model_registry

    org = make_org(db_session)
    entry = model_registry.create_model_entry(
        db_session, organization_id=org.id, model_name="drift-model", model_type="logistic_regression",
        entity_type="site", prediction_target_version="v1", label_definition_version="v1",
        feature_set_version="v1", training_data_version="v1", horizon_days=30,
        training_period_start=date(2026, 1, 1), training_period_end=date(2026, 2, 1),
        validation_period_start=date(2026, 2, 2), validation_period_end=date(2026, 3, 1),
        test_period_start=date(2026, 3, 2), test_period_end=date(2026, 4, 1),
        hyperparameters={}, metrics={}, parameters={},
    )

    flag = check_model_for_review(
        db_session, entry, reason=ReviewFlagReason.PERFORMANCE_DRIFT, metric_name="recall",
        historical_value=0.8, current_value=0.4, threshold=0.15,
    )
    assert flag is not None
    assert flag.status == "OPEN"
    assert flag.reason == ReviewFlagReason.PERFORMANCE_DRIFT.value

    stored = db_session.query(ModelReviewFlag).filter_by(model_id=entry.id).one()
    assert stored.id == flag.id


def test_check_model_for_review_creates_nothing_for_a_small_difference(db_session):
    from datetime import date

    from app.predictions import model_registry

    org = make_org(db_session)
    entry = model_registry.create_model_entry(
        db_session, organization_id=org.id, model_name="stable-model", model_type="logistic_regression",
        entity_type="site", prediction_target_version="v1", label_definition_version="v1",
        feature_set_version="v1", training_data_version="v1", horizon_days=30,
        training_period_start=date(2026, 1, 1), training_period_end=date(2026, 2, 1),
        validation_period_start=date(2026, 2, 2), validation_period_end=date(2026, 3, 1),
        test_period_start=date(2026, 3, 2), test_period_end=date(2026, 4, 1),
        hyperparameters={}, metrics={}, parameters={},
    )
    flag = check_model_for_review(
        db_session, entry, reason=ReviewFlagReason.PERFORMANCE_DRIFT, metric_name="recall",
        historical_value=0.8, current_value=0.78, threshold=0.15,
    )
    assert flag is None
    assert db_session.query(ModelReviewFlag).filter_by(model_id=entry.id).count() == 0


def test_never_retrains_or_redeploys_a_model_on_drift_detection():
    """Milestone item 32, non-negotiable: detecting drift only ever
    writes a ModelReviewFlag -- the module never imports
    app/predictions/model_registry.py at all (checked via the AST, so a
    mention of it in a docstring/comment doesn't trip this)."""
    import ast
    import inspect

    import app.predictions.drift as drift_module

    tree = ast.parse(inspect.getsource(drift_module))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    # app.models.model_registry_entry (the ORM row type) is fine to
    # import -- only the transition *service* module is forbidden.
    assert "app.predictions.model_registry" not in imported_modules


def test_acknowledge_review_flag_records_who_and_when(db_session):
    from datetime import date

    from app.predictions import model_registry

    org = make_org(db_session)
    reviewer = make_reviewer_user(db_session)
    entry = model_registry.create_model_entry(
        db_session, organization_id=org.id, model_name="ack-model", model_type="logistic_regression",
        entity_type="site", prediction_target_version="v1", label_definition_version="v1",
        feature_set_version="v1", training_data_version="v1", horizon_days=30,
        training_period_start=date(2026, 1, 1), training_period_end=date(2026, 2, 1),
        validation_period_start=date(2026, 2, 2), validation_period_end=date(2026, 3, 1),
        test_period_start=date(2026, 3, 2), test_period_end=date(2026, 4, 1),
        hyperparameters={}, metrics={}, parameters={},
    )
    flag = check_model_for_review(
        db_session, entry, reason=ReviewFlagReason.DATA_DRIFT, metric_name="event_frequency",
        historical_value=10.0, current_value=100.0, threshold=1.0,
    )
    acknowledged = acknowledge_review_flag(db_session, flag, user_id=reviewer.id)
    assert acknowledged.status == "ACKNOWLEDGED"
    assert acknowledged.acknowledged_by_user_id == reviewer.id
    assert acknowledged.acknowledged_at is not None
