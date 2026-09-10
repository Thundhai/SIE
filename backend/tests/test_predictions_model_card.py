"""Model card — Model Validation & Governance v0.1, item 33. DB-backed
(SQLite) tests."""

from app.predictions.dataset import build_training_examples
from app.predictions.model_card import (
    PROHIBITED_USES,
    build_model_card,
    render_markdown,
)
from app.predictions.training import train_baseline_model
from tests.fixtures.predictions.synthetic_training_dataset import (
    as_of_dates,
    seed_synthetic_organization,
)


def _train_model(db_session, *, seed=500):
    org, sites = seed_synthetic_organization(db_session, name="Card Test Org", site_names=["S1"], seed=seed)
    dates = as_of_dates()
    examples = build_training_examples(
        db_session, organization_id=org.id, site_ids=[s.id for s in sites], as_of_dates=dates
    )
    return train_baseline_model(db_session, organization_id=org.id, examples=examples)


def test_model_card_names_every_field_the_milestone_requires(db_session):
    entry = _train_model(db_session)
    card = build_model_card(entry)
    d = card.to_dict()
    for key in (
        "model_name", "model_version", "prediction_target_version", "entity_type", "horizon_days",
        "training_period", "validation_period", "test_period", "features", "known_limitations",
        "metrics", "calibration_validated", "intended_use", "prohibited_uses", "status",
    ):
        assert key in d


def test_model_card_prohibited_uses_match_the_milestones_own_list(db_session):
    entry = _train_model(db_session)
    card = build_model_card(entry)
    assert card.prohibited_uses == list(PROHIBITED_USES)
    assert any("disciplinary" in u.lower() for u in card.prohibited_uses)
    assert any("individual worker" in u.lower() for u in card.prohibited_uses)
    assert any("employment" in u.lower() for u in card.prohibited_uses)
    assert any("permit" in u.lower() for u in card.prohibited_uses)
    assert any("equipment shutdown" in u.lower() for u in card.prohibited_uses)


def test_model_card_flags_synthetic_only_training_as_a_known_limitation(db_session):
    entry = _train_model(db_session)
    card = build_model_card(entry)
    assert any("synthetic" in limitation.lower() for limitation in card.known_limitations)


def test_model_card_is_json_serializable(db_session):
    import json

    entry = _train_model(db_session)
    card = build_model_card(entry)
    json.dumps(card.to_dict())


def test_model_card_renders_readable_markdown(db_session):
    entry = _train_model(db_session)
    card = build_model_card(entry)
    markdown = render_markdown(card)
    assert card.model_name in markdown
    assert "## Prohibited use" in markdown
    assert "## Known limitations" in markdown
    assert "not a certainty" in markdown  # the safety-language note
