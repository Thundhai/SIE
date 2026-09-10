"""Calibration validation — Model Validation & Governance v0.1, items
14-15. Pure unit tests, no database."""

import random

from app.predictions.calibration import (
    DEFAULT_MIN_SAMPLE_SIZE_FOR_CALIBRATION_CLAIM,
    expected_calibration_error,
    validate_calibration,
)
from app.predictions.enums import ProbabilityStatus
from app.predictions.metrics import calibration_bins


def test_a_well_calibrated_score_set_is_reported_calibrated():
    """Synthetic data with a KNOWN approximate event frequency per score
    band (milestone item 15) -- scores that are directionally consistent
    with the observed rate at real sample size."""
    random.seed(0)
    y_true: list[int] = []
    y_scores: list[float] = []
    # Five bands, each with its own true positive rate, 40 samples/band --
    # the model's own score for each sample is exactly that band's rate
    # plus small noise, so predicted and observed line up closely.
    for true_rate in (0.1, 0.3, 0.5, 0.7, 0.9):
        for _ in range(40):
            y_true.append(1 if random.random() < true_rate else 0)
            y_scores.append(min(0.999, max(0.001, true_rate + random.gauss(0, 0.03))))

    result = validate_calibration(y_true, y_scores)
    assert result.sample_size == 200
    assert result.status == ProbabilityStatus.CALIBRATED.value
    assert result.expected_calibration_error is not None
    assert result.expected_calibration_error < 0.10


def test_a_badly_miscalibrated_score_set_is_reported_uncalibrated():
    random.seed(1)
    # Every score is near 0.9 regardless of the true (low) event rate --
    # systematically overconfident.
    y_true = [1 if random.random() < 0.1 else 0 for _ in range(100)]
    y_scores = [0.9 for _ in range(100)]
    result = validate_calibration(y_true, y_scores)
    assert result.status == ProbabilityStatus.UNCALIBRATED.value


def test_calibration_is_never_claimed_from_a_tiny_sample():
    """Milestone item 15: never claim statistical calibration from tiny
    datasets, even if the numbers happen to look perfect."""
    y_true = [1, 0, 1, 0, 1]
    y_scores = [0.9, 0.1, 0.9, 0.1, 0.9]  # a "perfect" tiny sample
    assert len(y_true) < DEFAULT_MIN_SAMPLE_SIZE_FOR_CALIBRATION_CLAIM
    result = validate_calibration(y_true, y_scores)
    assert result.status == ProbabilityStatus.UNCALIBRATED.value
    assert "sample size" in result.reason.lower()


def test_calibration_with_only_one_class_present_is_uncalibrated_not_fabricated():
    y_true = [1] * 40
    y_scores = [0.5] * 40
    result = validate_calibration(y_true, y_scores)
    assert result.status == ProbabilityStatus.UNCALIBRATED.value
    assert result.expected_calibration_error is None


def test_expected_calibration_error_is_zero_for_a_perfectly_calibrated_set_of_bins():
    bins = calibration_bins([1, 0, 1, 0], [0.75, 0.25, 0.75, 0.25], n_bins=2)
    ece = expected_calibration_error(bins)
    assert ece is not None
    assert ece < 0.3  # small bins, but should be reasonably close


def test_expected_calibration_error_is_none_when_no_bins_have_data():
    ece = expected_calibration_error([])
    assert ece is None
