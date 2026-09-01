"""Model stability analysis — Model Validation & Governance v0.1, item
17.

**A model that works only in one historical period, one site, or one
data-quality band should not automatically be approved (item 17's own
instruction).** Every function here slices a scored set of
`TrainingExample`s along one dimension (time period, site, or data
quality) and reports `app/predictions/metrics.py::evaluate()`'s full
metrics *per slice* — never one pooled number that could hide a slice
where the model performs badly. `summarize_variability()` then reports
how much a given metric actually swings across slices, so "unstable" is
a number, not an impression.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.predictions.dataset import TrainingExample
from app.predictions.metrics import EvaluationResult, evaluate

DEFAULT_N_TIME_PERIODS = 3


@dataclass
class StabilitySlice:
    dimension: str  # "time_period" | "site" | "data_quality"
    key: str
    metrics: EvaluationResult | None
    skipped_reason: str | None = None


@dataclass
class StabilityReport:
    dimension: str
    slices: list[StabilitySlice] = field(default_factory=list)


@dataclass
class VariabilitySummary:
    metric_name: str
    values: list[float]
    mean: float | None
    stdev: float | None
    minimum: float | None
    maximum: float | None


def _slice_report(dimension: str, groups: dict[str, tuple[list[int], list[float]]]) -> StabilityReport:
    slices: list[StabilitySlice] = []
    for key, (y_true, y_scores) in groups.items():
        if len(set(y_true)) < 1 or not y_true:
            slices.append(StabilitySlice(dimension=dimension, key=key, metrics=None, skipped_reason="NO_DATA"))
            continue
        slices.append(StabilitySlice(dimension=dimension, key=key, metrics=evaluate(y_true, y_scores)))
    return StabilityReport(dimension=dimension, slices=slices)


def analyze_stability_over_time(
    examples: list[TrainingExample], scores: list[float], *, n_periods: int = DEFAULT_N_TIME_PERIODS
) -> StabilityReport:
    """Splits `examples` into `n_periods` equal-sized, chronologically
    ordered slices by `as_of` — never a random split, consistent with
    every other temporal operation in this package."""
    if len(examples) != len(scores):
        raise ValueError("examples and scores must have the same length.")
    ordered = sorted(zip(examples, scores), key=lambda pair: pair[0].as_of)
    n = len(ordered)
    if n == 0:
        return StabilityReport(dimension="time_period", slices=[])

    groups: dict[str, tuple[list[int], list[float]]] = {}
    chunk_size = max(1, -(-n // n_periods))  # ceil division
    for period_index in range(n_periods):
        chunk = ordered[period_index * chunk_size : (period_index + 1) * chunk_size]
        if not chunk:
            continue
        start = chunk[0][0].as_of.date()
        end = chunk[-1][0].as_of.date()
        key = f"period_{period_index + 1}_{start}_{end}"
        groups[key] = ([e.label for e, _ in chunk], [s for _, s in chunk])

    return _slice_report("time_period", groups)


def analyze_stability_by_site(examples: list[TrainingExample], scores: list[float]) -> StabilityReport:
    if len(examples) != len(scores):
        raise ValueError("examples and scores must have the same length.")
    groups: dict[str, tuple[list[int], list[float]]] = {}
    for example, score in zip(examples, scores):
        key = str(example.entity_id)
        y_true, y_scores = groups.setdefault(key, ([], []))
        y_true.append(example.label)
        y_scores.append(score)
    return _slice_report("site", groups)


def analyze_stability_by_data_quality(examples: list[TrainingExample], scores: list[float]) -> StabilityReport:
    if len(examples) != len(scores):
        raise ValueError("examples and scores must have the same length.")
    groups: dict[str, tuple[list[int], list[float]]] = {}
    for example, score in zip(examples, scores):
        key = example.data_quality
        y_true, y_scores = groups.setdefault(key, ([], []))
        y_true.append(example.label)
        y_scores.append(score)
    return _slice_report("data_quality", groups)


def summarize_variability(report: StabilityReport, *, metric_name: str) -> VariabilitySummary:
    values = [
        getattr(s.metrics, metric_name)
        for s in report.slices
        if s.metrics is not None and getattr(s.metrics, metric_name, None) is not None
    ]
    return VariabilitySummary(
        metric_name=metric_name,
        values=values,
        mean=statistics.fmean(values) if values else None,
        stdev=statistics.pstdev(values) if len(values) > 1 else (0.0 if values else None),
        minimum=min(values) if values else None,
        maximum=max(values) if values else None,
    )


__all__ = [
    "DEFAULT_N_TIME_PERIODS",
    "StabilityReport",
    "StabilitySlice",
    "VariabilitySummary",
    "analyze_stability_by_data_quality",
    "analyze_stability_by_site",
    "analyze_stability_over_time",
    "summarize_variability",
]
