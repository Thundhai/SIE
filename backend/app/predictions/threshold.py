"""Configurable decision threshold — Model Validation & Governance v0.1,
item 16.

**`probability > 0.5` is never assumed to be the correct safety
threshold.** `evaluate_thresholds()` sweeps a range of candidate
thresholds and reports each one's own recall/precision/false-negative-
rate/false-positive-rate — the actual trade-off at every point — rather
than picking one. `DEFAULT_DECISION_THRESHOLD` below is what
`app/predictions/predictor.py` and `app/predictions/metrics.py` use when
nothing else is specified, documented plainly as an **initial default**,
never a production-validated cutoff.

**Never auto-optimized against synthetic data and called production**
(item 16's own instruction) — nothing in this module picks "the best"
threshold; `select_threshold_by_recall_floor()` is the closest it comes,
and even that is an explicit, named policy a human chose to apply
(maximize precision subject to a minimum recall), not a hidden
optimization.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.predictions.metrics import confusion_counts

DEFAULT_DECISION_THRESHOLD = 0.5
DEFAULT_THRESHOLD_SWEEP = tuple(round(t, 2) for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9))


@dataclass
class ThresholdEvaluation:
    threshold: float
    sample_size: int
    positive_count: int
    precision: float | None
    recall: float | None
    false_negative_rate: float | None  # 1 - recall, restated for safety-review readability
    false_positive_rate: float | None  # FP / (FP + TN)
    f1: float | None


def evaluate_threshold(y_true: list[int], y_scores: list[float], *, threshold: float) -> ThresholdEvaluation:
    y_pred = [1 if s >= threshold else 0 for s in y_scores]
    counts = confusion_counts(y_true, y_pred)

    precision = (counts.true_positive / (counts.true_positive + counts.false_positive)) if (counts.true_positive + counts.false_positive) else None
    recall_denom = counts.true_positive + counts.false_negative
    recall = (counts.true_positive / recall_denom) if recall_denom else None
    fnr = (1 - recall) if recall is not None else None
    fpr_denom = counts.false_positive + counts.true_negative
    fpr = (counts.false_positive / fpr_denom) if fpr_denom else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision is not None and recall is not None and (precision + recall) > 0) else None

    return ThresholdEvaluation(
        threshold=threshold,
        sample_size=len(y_true),
        positive_count=sum(y_true),
        precision=precision,
        recall=recall,
        false_negative_rate=fnr,
        false_positive_rate=fpr,
        f1=f1,
    )


def evaluate_thresholds(
    y_true: list[int], y_scores: list[float], *, thresholds: tuple[float, ...] = DEFAULT_THRESHOLD_SWEEP
) -> list[ThresholdEvaluation]:
    """The full documented trade-off table — every candidate threshold's
    own numbers, side by side, for a human to weigh (milestone item 16).
    Never collapses to one recommended threshold on its own."""
    return [evaluate_threshold(y_true, y_scores, threshold=t) for t in thresholds]


def select_threshold_by_recall_floor(
    y_true: list[int], y_scores: list[float], *, min_recall: float, thresholds: tuple[float, ...] = DEFAULT_THRESHOLD_SWEEP
) -> ThresholdEvaluation | None:
    """An explicit, named selection policy — "the highest threshold
    (fewest false positives) that still meets a minimum recall floor" —
    for a caller that wants one answer rather than the full sweep.
    Returns `None` if no candidate threshold meets `min_recall` at all
    (never silently falls back to a threshold that doesn't)."""
    evaluations = evaluate_thresholds(y_true, y_scores, thresholds=thresholds)
    qualifying = [e for e in evaluations if e.recall is not None and e.recall >= min_recall]
    if not qualifying:
        return None
    return max(qualifying, key=lambda e: e.threshold)


__all__ = [
    "DEFAULT_DECISION_THRESHOLD",
    "DEFAULT_THRESHOLD_SWEEP",
    "ThresholdEvaluation",
    "evaluate_threshold",
    "evaluate_thresholds",
    "select_threshold_by_recall_floor",
]
