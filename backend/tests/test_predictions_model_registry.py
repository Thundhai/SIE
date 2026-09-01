"""The minimal model registry — milestone items 24-26. DB-backed
(SQLite) tests."""

from datetime import date

import pytest

from app.predictions import model_registry
from app.predictions.enums import ModelStatus
from tests.intelligence_test_helpers import make_org


def _create_entry(db_session, org_id, **overrides):
    defaults = dict(
        organization_id=org_id,
        model_name="test-model",
        model_type="logistic_regression",
        entity_type="site",
        prediction_target_version="v1",
        label_definition_version="v1",
        feature_set_version="v1",
        training_data_version="v1",
        horizon_days=30,
        training_period_start=date(2026, 1, 1),
        training_period_end=date(2026, 3, 1),
        validation_period_start=date(2026, 3, 2),
        validation_period_end=date(2026, 4, 1),
        test_period_start=date(2026, 4, 2),
        test_period_end=date(2026, 5, 1),
        hyperparameters={},
        metrics={},
        parameters={},
    )
    defaults.update(overrides)
    return model_registry.create_model_entry(db_session, **defaults)


def test_create_model_entry_always_starts_as_trained(db_session):
    org = make_org(db_session)
    entry = _create_entry(db_session, org.id)
    assert entry.status == ModelStatus.TRAINED.value
    assert entry.calibration_validated is False


def test_model_version_auto_increments_per_organization_and_model_name(db_session):
    org = make_org(db_session)
    first = _create_entry(db_session, org.id)
    second = _create_entry(db_session, org.id)
    assert first.model_version == "v1"
    assert second.model_version == "v2"


def test_model_version_numbering_is_independent_per_organization(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    entry_a = _create_entry(db_session, org_a.id)
    entry_b = _create_entry(db_session, org_b.id)
    assert entry_a.model_version == "v1"
    assert entry_b.model_version == "v1"


def test_full_lifecycle_trained_to_deployed(db_session):
    org = make_org(db_session)
    entry = _create_entry(db_session, org.id)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=True)
    assert entry.status == ModelStatus.VALIDATED.value
    assert entry.calibration_validated is True
    entry = model_registry.approve(db_session, entry)
    assert entry.status == ModelStatus.APPROVED.value
    entry = model_registry.deploy(db_session, entry)
    assert entry.status == ModelStatus.DEPLOYED.value
    entry = model_registry.retire(db_session, entry)
    assert entry.status == ModelStatus.RETIRED.value


def test_invalid_transitions_are_rejected(db_session):
    org = make_org(db_session)
    entry = _create_entry(db_session, org.id)
    with pytest.raises(model_registry.InvalidModelTransitionError):
        model_registry.deploy(db_session, entry)  # TRAINED -> DEPLOYED skips VALIDATED/APPROVED
    with pytest.raises(model_registry.InvalidModelTransitionError):
        model_registry.approve(db_session, entry)  # TRAINED -> APPROVED skips VALIDATED


def test_retired_and_rejected_are_terminal(db_session):
    org = make_org(db_session)
    entry = _create_entry(db_session, org.id)
    entry = model_registry.reject(db_session, entry, reason="poor recall")
    assert entry.status == ModelStatus.REJECTED.value
    with pytest.raises(model_registry.InvalidModelTransitionError):
        model_registry.mark_validated(db_session, entry, calibration_validated=False)


def test_training_never_calls_a_status_transition_itself(db_session):
    """Milestone item 26: create_model_entry() is the only call training
    makes -- it must never leave TRAINED on its own."""
    org = make_org(db_session)
    entry = _create_entry(db_session, org.id)
    assert entry.status == ModelStatus.TRAINED.value


def test_deploying_a_new_model_retires_the_previously_deployed_one_for_the_same_org_and_entity_type(db_session):
    org = make_org(db_session)
    first = _create_entry(db_session, org.id, model_name="model-a")
    first = model_registry.mark_validated(db_session, first, calibration_validated=False)
    first = model_registry.approve(db_session, first)
    first = model_registry.deploy(db_session, first)
    assert first.status == ModelStatus.DEPLOYED.value

    second = _create_entry(db_session, org.id, model_name="model-b")
    second = model_registry.mark_validated(db_session, second, calibration_validated=False)
    second = model_registry.approve(db_session, second)
    second = model_registry.deploy(db_session, second)

    db_session.refresh(first)
    assert first.status == ModelStatus.RETIRED.value
    assert second.status == ModelStatus.DEPLOYED.value

    deployed = model_registry.get_deployed_model(db_session, organization_id=org.id, entity_type="site")
    assert deployed.id == second.id


def test_get_deployed_model_returns_none_when_nothing_is_deployed(db_session):
    org = make_org(db_session)
    _create_entry(db_session, org.id)  # stays TRAINED
    assert model_registry.get_deployed_model(db_session, organization_id=org.id, entity_type="site") is None


def test_get_deployed_model_is_scoped_per_organization(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    entry = _create_entry(db_session, org_a.id)
    entry = model_registry.mark_validated(db_session, entry, calibration_validated=False)
    entry = model_registry.approve(db_session, entry)
    model_registry.deploy(db_session, entry)

    assert model_registry.get_deployed_model(db_session, organization_id=org_a.id, entity_type="site") is not None
    assert model_registry.get_deployed_model(db_session, organization_id=org_b.id, entity_type="site") is None
