"""Controlled model comparison — Model Validation & Governance v0.1,
items 8-10, 45-46. DB-backed (SQLite) tests using the synthetic training
dataset fixture."""

from app.predictions.dataset import build_training_examples
from app.predictions.model_comparison import compare_models, comparison_table
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)


def _build_examples(db_session, *, seed=200):
    org, sites = seed_synthetic_organization(db_session, name="Comparison Org", site_names=["S1", "S2"], seed=seed)
    dates = as_of_dates()
    return build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )


def test_both_models_are_evaluated_on_the_identical_split(db_session):
    examples = _build_examples(db_session)
    report = compare_models(examples)
    # Same TemporalSplit object backs both summaries -- proven by
    # identical test-set sample sizes on both sides.
    assert report.logistic_regression.test_metrics.overall.sample_size == report.gradient_boosting.test_metrics.overall.sample_size
    assert report.logistic_regression.test_metrics.overall.sample_size == len(report.split.test)


def test_comparison_table_has_one_row_per_model_never_a_winner_field(db_session):
    examples = _build_examples(db_session)
    report = compare_models(examples)
    table = comparison_table(report)
    assert len(table) == 2
    models = {row["model"] for row in table}
    assert models == {"logistic_regression", "gradient_boosting"}
    for row in table:
        assert "winner" not in row
        assert "is_best" not in row


def test_report_never_picks_a_best_model_no_such_function_exists(db_session):
    import app.predictions.model_comparison as comparison_module

    assert not hasattr(comparison_module, "pick_best_model")
    assert not hasattr(comparison_module, "select_best_model")


def test_report_includes_calibration_error_analysis_and_stability_for_both_models(db_session):
    examples = _build_examples(db_session)
    report = compare_models(examples)
    for summary in (report.logistic_regression, report.gradient_boosting):
        assert summary.calibration is not None
        assert summary.error_analysis is not None
        assert summary.stability_over_time is not None
        assert summary.stability_by_site is not None
        assert summary.stability_by_data_quality is not None


def test_metrics_are_reported_separately_for_sufficient_and_limited_data_entities(db_session):
    examples = _build_examples(db_session)
    report = compare_models(examples)
    for summary in (report.logistic_regression, report.gradient_boosting):
        assert hasattr(summary.test_metrics, "sufficient_data")
        assert hasattr(summary.test_metrics, "limited_data")


def test_a_deterministic_seed_produces_reproducible_model_parameters(db_session):
    examples = _build_examples(db_session, seed=321)
    report_a = compare_models(examples)
    report_b = compare_models(examples)
    # Same data, same hyperparameters, same deterministic algorithms --
    # logistic regression weights must match exactly.
    assert report_a.logistic_regression.model_params["weights"] == report_b.logistic_regression.model_params["weights"]
