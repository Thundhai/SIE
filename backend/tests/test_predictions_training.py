"""Training orchestration — milestone items 20, 22, 39, 43, 48. DB-backed
(SQLite) tests using the synthetic training dataset fixture."""

import pytest

from app.predictions.dataset import build_training_examples
from app.predictions.enums import ModelStatus
from app.predictions.training import PROTOTYPE_MODEL_LABEL, train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)
from tests.intelligence_test_helpers import make_org


def _build_examples(db_session, *, seed=7):
    org, sites = seed_synthetic_organization(
        db_session, name="Training Org", site_names=["Site 1", "Site 2"], seed=seed
    )
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    return org, sites, examples


def test_train_baseline_model_produces_a_trained_registry_entry(db_session):
    org, _sites, examples = _build_examples(db_session)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    assert entry.status == ModelStatus.TRAINED.value
    assert entry.model_type == "logistic_regression"


def test_trained_model_is_always_labeled_as_a_prototype_on_synthetic_data(db_session):
    """Milestone item 48: never described as production predictive
    intelligence."""
    org, _sites, examples = _build_examples(db_session)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    assert entry.notes == PROTOTYPE_MODEL_LABEL
    assert "Prototype" in entry.notes
    assert "Synthetic" in entry.notes


def test_metrics_are_reported_separately_for_train_validation_and_test(db_session):
    org, _sites, examples = _build_examples(db_session)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    for split_name in ("train", "validation", "test"):
        assert split_name in entry.metrics
        assert "overall" in entry.metrics[split_name]
        assert "sufficient_data" in entry.metrics[split_name]
        assert "limited_data" in entry.metrics[split_name]
        overall = entry.metrics[split_name]["overall"]
        assert "accuracy" not in overall  # never the headline metric
        assert "precision" in overall and "recall" in overall and "pr_auc" in overall


def test_metrics_never_report_a_fabricated_number_when_a_group_is_empty_or_single_class(db_session):
    org, _sites, examples = _build_examples(db_session)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    # Whatever the actual composition, pr_auc/roc_auc must be a real
    # float or explicitly None -- never silently coerced.
    for split_name in ("train", "validation", "test"):
        overall = entry.metrics[split_name]["overall"]
        assert overall["pr_auc"] is None or isinstance(overall["pr_auc"], float)
        assert overall["roc_auc"] is None or isinstance(overall["roc_auc"], float)


def test_model_parameters_are_persisted_and_reconstructible(db_session):
    org, _sites, examples = _build_examples(db_session)
    entry = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    assert "preprocessor" in entry.parameters
    assert "model" in entry.parameters
    assert entry.parameters["model"]["model_type"] == "logistic_regression"


def test_training_examples_from_a_different_organization_are_rejected(db_session):
    """Milestone item 43: a model is trained on exactly one
    organization's own data."""
    _org, _sites, examples = _build_examples(db_session)
    other_org = make_org(db_session, "Other Org")
    with pytest.raises(ValueError):
        train_baseline_model(db_session, organization_id=other_org.id, examples=examples)


def test_repeated_training_creates_a_new_model_version_never_overwrites(db_session):
    org, _sites, examples = _build_examples(db_session)
    first = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    second = train_baseline_model(db_session, organization_id=org.id, examples=examples)
    assert first.id != second.id
    assert first.model_version != second.model_version
    # The first row must still exist, unmodified -- never overwritten.
    db_session.refresh(first)
    assert first.status == ModelStatus.TRAINED.value
