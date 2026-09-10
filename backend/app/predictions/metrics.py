"""Evaluation metrics, in pure Python — milestone items 16-18, 41.

**Class imbalance is expected** (elevated-risk events are rare) — this
module never reports accuracy as a headline metric (it is not even
computed). Primary metrics are **Recall, Precision, and PR-AUC**;
secondary metrics are **ROC-AUC, F1, and calibration**, all computed
here from first principles (no `sklearn.metrics`) so every number is
traceable to this file, not to an opaque library call.

**Metrics are never fabricated.** When a metric is undefined for the
given data (e.g. `PR-AUC`/`ROC-AUC` need both classes present; a rate
needs a non-zero denominator), the corresponding field is `None`, with
`sample_size`/`positive_count` always reported alongside so *why* it is
`None` is inspectable — never a placeholder number.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class ConfusionCounts:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def total(self) -> int:
        return self.true_positive + self.false_positive + self.true_negative + self.false_negative


def confusion_counts(y_true: list[int], y_pred: list[int]) -> ConfusionCounts:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    return ConfusionCounts(true_positive=tp, false_positive=fp, true_negative=tn, false_negative=fn)


def precision_score(counts: ConfusionCounts) -> float | None:
    denom = counts.true_positive + counts.false_positive
    return (counts.true_positive / denom) if denom else None


def recall_score(counts: ConfusionCounts) -> float | None:
    denom = counts.true_positive + counts.false_negative
    return (counts.true_positive / denom) if denom else None


def f1_score(counts: ConfusionCounts) -> float | None:
    p, r = precision_score(counts), recall_score(counts)
    if p is None or r is None or (p + r) == 0:
        return None
    return 2 * p * r / (p + r)


def _pr_points(y_true: list[int], y_scores: list[float]) -> list[tuple[float, float]]:
    """`(recall, precision)` at every distinct score threshold, sorted by
    ascending recall — the points a PR-AUC trapezoidal integral is taken
    over."""
    n_pos = sum(y_true)
    if n_pos == 0:
        return []
    order = sorted(range(len(y_scores)), key=lambda i: -y_scores[i])
    tp = fp = 0
    points: list[tuple[float, float]] = [(0.0, 1.0)]  # conventional PR-curve start
    for i in order:
        if y_true[i] == 1:
            tp += 1
        else:
            fp += 1
        recall = tp / n_pos
        precision = tp / (tp + fp)
        points.append((recall, precision))
    return points


def pr_auc(y_true: list[int], y_scores: list[float]) -> float | None:
    points = _pr_points(y_true, y_scores)
    if not points or len(set(y_true)) < 2:
        return None
    points.sort(key=lambda p: p[0])
    area = 0.0
    for (r0, p0), (r1, p1) in itertools.pairwise(points):
        area += (r1 - r0) * (p0 + p1) / 2.0
    return area


def roc_auc(y_true: list[int], y_scores: list[float]) -> float | None:
    """Mann-Whitney U formulation: the probability a random positive is
    scored higher than a random negative, with tied scores contributing
    half credit -- avoids any dependency on a curve-plotting library."""
    n_pos = sum(1 for t in y_true if t == 1)
    n_neg = sum(1 for t in y_true if t == 0)
    if n_pos == 0 or n_neg == 0:
        return None

    # Average rank for tied scores (1-indexed), ascending score order.
    order = sorted(range(len(y_scores)), key=lambda i: y_scores[i])
    ranks = [0.0] * len(y_scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and y_scores[order[j + 1]] == y_scores[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-indexed
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1

    rank_sum_pos = sum(ranks[i] for i in range(len(y_true)) if y_true[i] == 1)
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def brier_score(y_true: list[int], y_prob: list[float]) -> float | None:
    if not y_true:
        return None
    return sum((p - t) ** 2 for t, p in zip(y_true, y_prob)) / len(y_true)


@dataclass
class CalibrationBin:
    bin_start: float
    bin_end: float
    predicted_mean: float | None
    observed_rate: float | None
    count: int


def calibration_bins(y_true: list[int], y_prob: list[float], *, n_bins: int = 5) -> list[CalibrationBin]:
    bins: list[CalibrationBin] = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, p in enumerate(y_prob) if (p >= lo and (p < hi or (b == n_bins - 1 and p <= hi)))]
        if idx:
            predicted_mean = sum(y_prob[i] for i in idx) / len(idx)
            observed_rate = sum(y_true[i] for i in idx) / len(idx)
        else:
            predicted_mean = None
            observed_rate = None
        bins.append(CalibrationBin(bin_start=lo, bin_end=hi, predicted_mean=predicted_mean, observed_rate=observed_rate, count=len(idx)))
    return bins


@dataclass
class EvaluationResult:
    sample_size: int
    positive_count: int
    confusion: ConfusionCounts
    precision: float | None
    recall: float | None
    f1: float | None
    pr_auc: float | None
    roc_auc: float | None
    brier_score: float | None
    calibration: list[CalibrationBin] = field(default_factory=list)


def evaluate(
    y_true: list[int], y_scores: list[float], *, threshold: float = 0.5, n_calibration_bins: int = 5
) -> EvaluationResult:
    """`y_scores` are model probabilities/scores in `[0, 1]`; `y_pred`
    for the confusion-matrix-derived metrics is thresholded at
    `threshold` internally, so callers only ever pass one score array."""
    y_pred = [1 if s >= threshold else 0 for s in y_scores]
    counts = confusion_counts(y_true, y_pred)
    return EvaluationResult(
        sample_size=len(y_true),
        positive_count=sum(y_true),
        confusion=counts,
        precision=precision_score(counts),
        recall=recall_score(counts),
        f1=f1_score(counts),
        pr_auc=pr_auc(y_true, y_scores),
        roc_auc=roc_auc(y_true, y_scores),
        brier_score=brier_score(y_true, y_scores),
        calibration=calibration_bins(y_true, y_scores, n_bins=n_calibration_bins),
    )


SUFFICIENT_DATA_QUALITIES = frozenset({"SUFFICIENT_DATA"})
LIMITED_DATA_QUALITIES = frozenset({"LIMITED_DATA", "INSUFFICIENT_DATA"})


@dataclass
class GroupedEvaluationResult:
    """Milestone item 41: sufficient- and limited-data entities are never
    pooled into one number that hides how much of the "good" performance
    came from data-rich entities."""

    overall: EvaluationResult
    sufficient_data: EvaluationResult | None
    limited_data: EvaluationResult | None


def evaluate_by_data_quality(
    y_true: list[int], y_scores: list[float], data_qualities: list[str], *, threshold: float = 0.5
) -> GroupedEvaluationResult:
    if not (len(y_true) == len(y_scores) == len(data_qualities)):
        raise ValueError("y_true, y_scores, and data_qualities must have the same length.")

    def _subset(predicate):
        idx = [i for i, q in enumerate(data_qualities) if predicate(q)]
        if not idx:
            return None
        return evaluate([y_true[i] for i in idx], [y_scores[i] for i in idx], threshold=threshold)

    return GroupedEvaluationResult(
        overall=evaluate(y_true, y_scores, threshold=threshold),
        sufficient_data=_subset(lambda q: q in SUFFICIENT_DATA_QUALITIES),
        limited_data=_subset(lambda q: q in LIMITED_DATA_QUALITIES),
    )
