"""False negative / false positive error analysis — Model Validation &
Governance v0.1, items 12-13. Pure unit tests over `analyze_errors()`."""

import uuid
from datetime import datetime, timezone

import pytest

from app.predictions.dataset import TrainingExample
from app.predictions.error_analysis import analyze_errors

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _example(label: int, **overrides) -> TrainingExample:
    defaults = dict(
        entity_type="site", entity_id=uuid.uuid4(), organization_id=uuid.uuid4(), as_of=AS_OF,
        feature_snapshot_id=uuid.uuid4(), feature_vector={"x": 1.0}, feature_set_version="v1",
        data_quality="SUFFICIENT_DATA", label=label, label_definition_version="v1", horizon_days=30,
        supporting_event_ids=[uuid.uuid4()],
    )
    defaults.update(overrides)
    return TrainingExample(**defaults)


def test_false_negatives_are_predicted_zero_but_actually_one():
    examples = [_example(1), _example(0)]
    scores = [0.2, 0.2]  # both predicted negative at threshold 0.5
    report = analyze_errors(examples, scores, model_version="v1", threshold=0.5)
    assert report.false_negative_count == 1
    assert report.false_positive_count == 0
    assert report.false_negatives[0].actual_label == 1
    assert report.false_negatives[0].predicted_label == 0


def test_false_positives_are_predicted_one_but_actually_zero():
    examples = [_example(0), _example(1)]
    scores = [0.8, 0.8]  # both predicted positive
    report = analyze_errors(examples, scores, model_version="v1", threshold=0.5)
    assert report.false_positive_count == 1
    assert report.false_positives[0].actual_label == 0
    assert report.false_positives[0].predicted_label == 1


def test_correct_predictions_never_appear_in_either_list():
    examples = [_example(1), _example(0)]
    scores = [0.9, 0.1]
    report = analyze_errors(examples, scores, model_version="v1", threshold=0.5)
    assert report.false_negative_count == 0
    assert report.false_positive_count == 0


def test_error_records_carry_full_provenance_for_review():
    example = _example(1, feature_vector={"incident_count_30d": 2.0})
    report = analyze_errors([example], [0.1], model_version="model-v3", threshold=0.5)
    record = report.false_negatives[0]
    assert record.entity_id == example.entity_id
    assert record.as_of == example.as_of
    assert record.feature_vector == example.feature_vector
    assert record.feature_snapshot_id == example.feature_snapshot_id
    assert record.supporting_event_ids == example.supporting_event_ids
    assert record.model_version == "model-v3"
    assert record.data_quality == example.data_quality


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError):
        analyze_errors([_example(1), _example(0)], [0.5], model_version="v1")
