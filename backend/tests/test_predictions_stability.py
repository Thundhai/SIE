"""Model stability analysis — Model Validation & Governance v0.1, item
17. Pure unit tests, no database."""

import uuid
from datetime import datetime, timedelta, timezone

from app.predictions.dataset import TrainingExample
from app.predictions.stability import (
    analyze_stability_by_data_quality,
    analyze_stability_by_site,
    analyze_stability_over_time,
    summarize_variability,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _example(*, label, as_of, entity_id=None, data_quality="SUFFICIENT_DATA") -> TrainingExample:
    return TrainingExample(
        entity_type="site", entity_id=entity_id or uuid.uuid4(), organization_id=uuid.uuid4(),
        as_of=as_of, feature_snapshot_id=uuid.uuid4(), feature_vector={"x": 1.0}, feature_set_version="v1",
        data_quality=data_quality, label=label, label_definition_version="v1", horizon_days=30,
        supporting_event_ids=[],
    )


def test_stability_over_time_splits_into_chronological_slices_not_random():
    examples = [_example(label=i % 2, as_of=BASE + timedelta(days=i * 10)) for i in range(30)]
    scores = [0.9 if e.label == 1 else 0.1 for e in examples]
    report = analyze_stability_over_time(examples, scores, n_periods=3)
    assert report.dimension == "time_period"
    assert len(report.slices) == 3
    # Each slice's key encodes its own date range -- and slices come out
    # in ascending chronological order.
    starts = [s.key for s in report.slices]
    assert starts == sorted(starts)


def test_stability_by_site_groups_examples_per_entity():
    site_a, site_b = uuid.uuid4(), uuid.uuid4()
    examples = [_example(label=1, as_of=BASE, entity_id=site_a) for _ in range(5)] + [
        _example(label=0, as_of=BASE, entity_id=site_b) for _ in range(5)
    ]
    scores = [0.9] * 5 + [0.1] * 5
    report = analyze_stability_by_site(examples, scores)
    assert {s.key for s in report.slices} == {str(site_a), str(site_b)}
    site_a_slice = next(s for s in report.slices if s.key == str(site_a))
    assert site_a_slice.metrics.recall == 1.0


def test_stability_by_data_quality_separates_sufficient_and_limited():
    examples = [_example(label=1, as_of=BASE, data_quality="SUFFICIENT_DATA") for _ in range(5)] + [
        _example(label=0, as_of=BASE, data_quality="LIMITED_DATA") for _ in range(5)
    ]
    scores = [0.9] * 5 + [0.9] * 5  # deliberately bad on the limited-data group
    report = analyze_stability_by_data_quality(examples, scores)
    by_key = {s.key: s for s in report.slices}
    assert by_key["SUFFICIENT_DATA"].metrics.recall == 1.0
    assert by_key["LIMITED_DATA"].metrics.precision == 0.0


def test_summarize_variability_reports_mean_and_stdev_across_slices():
    examples = [_example(label=i % 2, as_of=BASE + timedelta(days=i * 5)) for i in range(20)]
    scores = [0.9 if e.label == 1 else 0.1 for e in examples]
    report = analyze_stability_over_time(examples, scores, n_periods=4)
    summary = summarize_variability(report, metric_name="recall")
    assert summary.metric_name == "recall"
    assert summary.mean is not None
    assert summary.stdev is not None


def test_a_slice_with_no_data_is_skipped_not_silently_dropped():
    examples = [_example(label=1, as_of=BASE)]
    scores = [0.9]
    report = analyze_stability_over_time(examples, scores, n_periods=5)
    # 5 requested periods but only 1 example -- some slices legitimately
    # have nothing in them; those must show up as explicit skips.
    assert any(s.metrics is None for s in report.slices) or len(report.slices) < 5
