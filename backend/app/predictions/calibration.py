"""Calibration validation — Model Validation & Governance v0.1, items
14-15.

**If the model produces probabilities, they are validated before ever
being labeled "probability" anywhere a user sees them.**
`ModelRegistryEntry.calibration_validated` — the single flag that gates
`Prediction.probability` (see that model's own docstring) — must never
be set to `True` without first calling `validate_calibration()` here and
getting back `ProbabilityStatus.CALIBRATED`.

    y_true, y_scores (validation or test split)
        -> reliability curve (app/predictions/metrics.py::calibration_bins(), reused)
        -> Brier score (reused)
        -> Expected Calibration Error (ECE) -- the weighted-average gap
           between each bin's mean predicted score and its actual
           observed positive rate
        -> CalibrationResult(status=CALIBRATED | UNCALIBRATED, ...)

**Never claims calibration from a tiny sample (item 15).** Fewer than
`min_sample_size` scored examples and `validate_calibration()` returns
`UNCALIBRATED` outright, regardless of how good the numbers look —
"directionally consistent on 8 data points" is not a calibration claim
this codebase is willing to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.predictions.enums import ProbabilityStatus
from app.predictions.metrics import CalibrationBin, brier_score, calibration_bins

# --- INITIAL GOVERNANCE DEFAULT thresholds ---------------------------------------------
DEFAULT_MAX_ECE_FOR_CALIBRATED = 0.10
DEFAULT_MIN_SAMPLE_SIZE_FOR_CALIBRATION_CLAIM = 30
DEFAULT_CALIBRATION_BINS = 5


def expected_calibration_error(bins: list[CalibrationBin]) -> float | None:
    """The count-weighted average `|predicted_mean - observed_rate|`
    across non-empty bins — `None` if every bin is empty (nothing to
    compute from)."""
    total = sum(b.count for b in bins)
    if total == 0:
        return None
    weighted_gap = sum(
        abs(b.predicted_mean - b.observed_rate) * b.count
        for b in bins
        if b.count and b.predicted_mean is not None and b.observed_rate is not None
    )
    return weighted_gap / total


@dataclass
class CalibrationResult:
    status: str  # ProbabilityStatus
    sample_size: int
    brier_score: float | None
    expected_calibration_error: float | None
    bins: list[CalibrationBin] = field(default_factory=list)
    reason: str = ""


def validate_calibration(
    y_true: list[int],
    y_scores: list[float],
    *,
    n_bins: int = DEFAULT_CALIBRATION_BINS,
    max_ece_for_calibrated: float = DEFAULT_MAX_ECE_FOR_CALIBRATED,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE_FOR_CALIBRATION_CLAIM,
) -> CalibrationResult:
    sample_size = len(y_true)
    if sample_size < min_sample_size:
        return CalibrationResult(
            status=ProbabilityStatus.UNCALIBRATED.value,
            sample_size=sample_size,
            brier_score=None,
            expected_calibration_error=None,
            bins=[],
            reason=f"Sample size {sample_size} is below the minimum ({min_sample_size}) required to claim calibration.",
        )
    if len(set(y_true)) < 2:
        return CalibrationResult(
            status=ProbabilityStatus.UNCALIBRATED.value,
            sample_size=sample_size,
            brier_score=brier_score(y_true, y_scores),
            expected_calibration_error=None,
            bins=[],
            reason="Only one class present -- calibration is undefined without both outcomes observed.",
        )

    bins = calibration_bins(y_true, y_scores, n_bins=n_bins)
    ece = expected_calibration_error(bins)
    brier = brier_score(y_true, y_scores)

    if ece is not None and ece <= max_ece_for_calibrated:
        status = ProbabilityStatus.CALIBRATED.value
        reason = f"Expected Calibration Error {ece:.4f} is within the {max_ece_for_calibrated} threshold."
    else:
        status = ProbabilityStatus.UNCALIBRATED.value
        reason = (
            f"Expected Calibration Error {ece:.4f} exceeds the {max_ece_for_calibrated} threshold."
            if ece is not None
            else "Expected Calibration Error could not be computed (no populated bins)."
        )

    return CalibrationResult(
        status=status, sample_size=sample_size, brier_score=brier, expected_calibration_error=ece, bins=bins, reason=reason,
    )


__all__ = [
    "DEFAULT_CALIBRATION_BINS",
    "DEFAULT_MAX_ECE_FOR_CALIBRATED",
    "DEFAULT_MIN_SAMPLE_SIZE_FOR_CALIBRATION_CLAIM",
    "CalibrationResult",
    "expected_calibration_error",
    "validate_calibration",
]
