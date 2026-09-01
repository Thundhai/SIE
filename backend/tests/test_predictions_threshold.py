"""Configurable decision threshold — Model Validation & Governance v0.1,
item 16. Pure unit tests, no database."""

from app.predictions.threshold import (
    DEFAULT_THRESHOLD_SWEEP,
    evaluate_threshold,
    evaluate_thresholds,
    select_threshold_by_recall_floor,
)


def test_evaluate_threshold_reports_the_full_trade_off():
    y_true = [1, 1, 0, 0]
    y_scores = [0.9, 0.4, 0.6, 0.1]
    result = evaluate_threshold(y_true, y_scores, threshold=0.5)
    assert result.threshold == 0.5
    assert result.recall == 0.5  # only the 0.9 score counts as predicted-positive among the two actual positives
    assert result.false_negative_rate == 0.5


def test_a_lower_threshold_never_decreases_recall():
    y_true = [1, 1, 0, 0]
    y_scores = [0.9, 0.4, 0.6, 0.1]
    low = evaluate_threshold(y_true, y_scores, threshold=0.3)
    high = evaluate_threshold(y_true, y_scores, threshold=0.8)
    assert low.recall >= high.recall


def test_evaluate_thresholds_sweeps_every_candidate_never_picks_one():
    y_true = [1, 0, 1, 0, 1, 0]
    y_scores = [0.9, 0.1, 0.6, 0.4, 0.3, 0.2]
    results = evaluate_thresholds(y_true, y_scores)
    assert len(results) == len(DEFAULT_THRESHOLD_SWEEP)
    assert [r.threshold for r in results] == list(DEFAULT_THRESHOLD_SWEEP)


def test_select_threshold_by_recall_floor_returns_the_highest_qualifying_threshold():
    y_true = [1, 1, 1, 0, 0, 0]
    y_scores = [0.9, 0.6, 0.3, 0.8, 0.2, 0.1]
    selected = select_threshold_by_recall_floor(y_true, y_scores, min_recall=1.0)
    assert selected is not None
    assert selected.recall >= 1.0
    # The highest threshold that still recalls everything.
    assert selected.threshold <= 0.3


def test_select_threshold_by_recall_floor_returns_none_when_unreachable():
    y_true = [1, 1, 0, 0]
    # Every positive scores below the entire swept threshold range (which
    # starts at 0.1) -- no threshold in the sweep can ever recall them.
    y_scores = [0.01, 0.02, 0.9, 0.9]
    selected = select_threshold_by_recall_floor(y_true, y_scores, min_recall=0.9)
    assert selected is None
