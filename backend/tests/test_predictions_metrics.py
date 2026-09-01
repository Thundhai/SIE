"""Evaluation metrics — milestone items 16-18, 41. Pure unit tests, no
database."""

from app.predictions.metrics import (
    confusion_counts,
    evaluate,
    evaluate_by_data_quality,
    f1_score,
    pr_auc,
    precision_score,
    recall_score,
    roc_auc,
)


def test_confusion_counts_are_correct():
    y_true = [1, 1, 0, 0]
    y_pred = [1, 0, 0, 1]
    counts = confusion_counts(y_true, y_pred)
    assert counts.true_positive == 1
    assert counts.false_negative == 1
    assert counts.true_negative == 1
    assert counts.false_positive == 1


def test_precision_recall_f1_on_a_perfect_classifier():
    y_true = [1, 1, 0, 0]
    scores = [0.9, 0.8, 0.2, 0.1]
    result = evaluate(y_true, scores)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_precision_is_none_when_nothing_is_predicted_positive():
    counts = confusion_counts([1, 0], [0, 0])
    assert precision_score(counts) is None


def test_recall_is_none_when_there_are_no_actual_positives():
    counts = confusion_counts([0, 0], [1, 0])
    assert recall_score(counts) is None


def test_f1_is_none_when_precision_or_recall_is_none():
    counts = confusion_counts([0, 0], [0, 0])
    assert f1_score(counts) is None


def test_pr_auc_and_roc_auc_are_none_with_only_one_class_present():
    y_true = [1, 1, 1]
    scores = [0.9, 0.5, 0.1]
    assert pr_auc(y_true, scores) is None
    assert roc_auc(y_true, scores) is None


def test_roc_auc_of_a_perfect_ranking_is_one():
    y_true = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]
    assert roc_auc(y_true, scores) == 1.0


def test_roc_auc_of_a_random_coin_flip_ranking_is_near_half():
    y_true = [1, 0, 1, 0]
    scores = [0.5, 0.5, 0.5, 0.5]  # all tied -- ties contribute half credit
    assert roc_auc(y_true, scores) == 0.5


def test_metrics_never_report_accuracy_as_a_field():
    result = evaluate([1, 0], [0.9, 0.1])
    assert not hasattr(result, "accuracy")


def test_evaluate_by_data_quality_separates_sufficient_and_limited_groups():
    y_true = [1, 0, 1, 0]
    scores = [0.9, 0.1, 0.8, 0.2]
    qualities = ["SUFFICIENT_DATA", "SUFFICIENT_DATA", "LIMITED_DATA", "LIMITED_DATA"]
    grouped = evaluate_by_data_quality(y_true, scores, qualities)
    assert grouped.sufficient_data.sample_size == 2
    assert grouped.limited_data.sample_size == 2
    assert grouped.overall.sample_size == 4


def test_evaluate_by_data_quality_group_is_none_when_the_group_is_empty():
    grouped = evaluate_by_data_quality([1, 0], [0.9, 0.1], ["SUFFICIENT_DATA", "SUFFICIENT_DATA"])
    assert grouped.limited_data is None
    assert grouped.sufficient_data is not None


def test_calibration_bins_report_predicted_mean_and_observed_rate_per_bin():
    result = evaluate([1, 0, 1, 0], [0.9, 0.1, 0.85, 0.05], n_calibration_bins=2)
    assert len(result.calibration) == 2
    for b in result.calibration:
        assert 0.0 <= b.bin_start < b.bin_end <= 1.0


def test_sample_size_and_positive_count_are_always_reported():
    result = evaluate([1, 1, 0], [0.9, 0.9, 0.9])
    assert result.sample_size == 3
    assert result.positive_count == 2
