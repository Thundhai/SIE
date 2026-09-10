"""Minimum data requirements — Model Validation & Governance v0.1, item
7: whether a dataset even has enough data to responsibly attempt
training/validation, checked *before* any model is fit.

**INITIAL GOVERNANCE DEFAULT, not a universal industry threshold**
(item 7's own instruction) — every field on `DataSufficiencyThresholds`
is a documented starting point a caller may override; nothing here
claims to be validated against real-world safety-outcome base rates.

    DatasetVersion + TrainingExample[]
        -> check_minimum_requirements()
        -> DataRequirementsResult(status=SUFFICIENT | INSUFFICIENT_DATA, ...)

`SUFFICIENT` is not a claim the resulting model will perform well — only
that there is enough data to responsibly try. `training.py` (not yet
wired to call this automatically — see that module's own docstring) is
expected to check this before committing to a training run; nothing here
runs training itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.dataset_version import DatasetVersion
from app.predictions.dataset import TrainingExample
from app.predictions.enums import ModelValidationStatus

DEFAULT_MIN_HISTORICAL_DAYS = 180
DEFAULT_MIN_SITES = 2
DEFAULT_MIN_POSITIVE_LABELS = 5
DEFAULT_MIN_PREDICTION_WINDOWS = 20
DEFAULT_MIN_EXPOSURE_COVERAGE = 0.5
DEFAULT_MIN_COMPLETENESS = 0.85  # 1 - (missing_site_rate), a proxy for overall record completeness


@dataclass
class DataSufficiencyThresholds:
    """INITIAL GOVERNANCE DEFAULT — see module docstring."""

    min_historical_days: int = DEFAULT_MIN_HISTORICAL_DAYS
    min_sites: int = DEFAULT_MIN_SITES
    min_positive_labels: int = DEFAULT_MIN_POSITIVE_LABELS
    min_prediction_windows: int = DEFAULT_MIN_PREDICTION_WINDOWS
    min_exposure_coverage: float = DEFAULT_MIN_EXPOSURE_COVERAGE
    min_completeness: float = DEFAULT_MIN_COMPLETENESS


@dataclass
class RequirementCheck:
    name: str
    passed: bool
    required: float
    actual: float
    detail: str = ""


@dataclass
class DataRequirementsResult:
    status: str  # ModelValidationStatus
    checks: list[RequirementCheck] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[RequirementCheck]:
        return [c for c in self.checks if not c.passed]


def check_minimum_requirements(
    *,
    dataset_version: DatasetVersion,
    examples: list[TrainingExample] | None = None,
    thresholds: DataSufficiencyThresholds | None = None,
) -> DataRequirementsResult:
    thresholds = thresholds or DataSufficiencyThresholds()
    examples = examples or []

    historical_days = (dataset_version.date_range_end - dataset_version.date_range_start).days
    sites = dataset_version.entity_count
    positive_labels = sum(1 for e in examples if e.label == 1)
    prediction_windows = len({e.as_of for e in examples}) if examples else 0

    quality_report = dataset_version.quality_report or {}
    completeness = quality_report.get("completeness", {})
    missing_exposure_rate = completeness.get("missing_exposure_rate")
    exposure_coverage = (1.0 - missing_exposure_rate) if missing_exposure_rate is not None else 0.0
    missing_site_rate = completeness.get("missing_site_rate")
    record_completeness = (1.0 - missing_site_rate) if missing_site_rate is not None else 0.0

    checks = [
        RequirementCheck(
            name="minimum_historical_duration",
            passed=historical_days >= thresholds.min_historical_days,
            required=thresholds.min_historical_days,
            actual=historical_days,
            detail="Days spanned by the dataset's own date range.",
        ),
        RequirementCheck(
            name="minimum_number_of_sites",
            passed=sites >= thresholds.min_sites,
            required=thresholds.min_sites,
            actual=sites,
        ),
        RequirementCheck(
            name="minimum_exposure_coverage",
            passed=exposure_coverage >= thresholds.min_exposure_coverage,
            required=thresholds.min_exposure_coverage,
            actual=round(exposure_coverage, 4),
            detail="Fraction of sites with at least one WORKFORCE/EXPOSURE_HOURS record.",
        ),
        RequirementCheck(
            name="minimum_completeness",
            passed=record_completeness >= thresholds.min_completeness,
            required=thresholds.min_completeness,
            actual=round(record_completeness, 4),
            detail="1 - missing_site_rate, from the dataset's own quality report.",
        ),
    ]

    if examples:
        checks.append(
            RequirementCheck(
                name="minimum_positive_labels",
                passed=positive_labels >= thresholds.min_positive_labels,
                required=thresholds.min_positive_labels,
                actual=positive_labels,
                detail="Training examples with label=1 (a qualifying incident occurred within the horizon).",
            )
        )
        checks.append(
            RequirementCheck(
                name="minimum_prediction_windows",
                passed=prediction_windows >= thresholds.min_prediction_windows,
                required=thresholds.min_prediction_windows,
                actual=prediction_windows,
                detail="Distinct as_of dates across the training examples.",
            )
        )

    status = ModelValidationStatus.SUFFICIENT.value if all(c.passed for c in checks) else ModelValidationStatus.INSUFFICIENT_DATA.value
    return DataRequirementsResult(status=status, checks=checks)


__all__ = [
    "DEFAULT_MIN_COMPLETENESS",
    "DEFAULT_MIN_EXPOSURE_COVERAGE",
    "DEFAULT_MIN_HISTORICAL_DAYS",
    "DEFAULT_MIN_POSITIVE_LABELS",
    "DEFAULT_MIN_PREDICTION_WINDOWS",
    "DEFAULT_MIN_SITES",
    "DataRequirementsResult",
    "DataSufficiencyThresholds",
    "RequirementCheck",
    "check_minimum_requirements",
]
