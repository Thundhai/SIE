"""Deterministic likelihood x consequence risk matrix — SIE Milestone 25:
Enterprise Risk Assessment Foundation v0.1, items 9-10, 13.

    likelihood (1-5) x consequence (1-5) = risk score (1-25)
        -> band (LOW/MODERATE/HIGH/CRITICAL, settings.RISK_ASSESSMENT_*_MAX)

**Fully transparent, no learned weights.** Every number in `RiskRating`
is directly inspectable — this is arithmetic and a lookup table, not a
model. Applied identically to inherent risk (before controls) and
residual risk (after controls, item 13) — the same function, called
twice with different likelihood/consequence inputs; there is no second,
competing calculation for either.

**Never a percentage-reduction claim (item 13).** This module has no
function that computes "controls reduced risk by X%" — residual risk is
always an *independently supplied* likelihood/consequence pair, never
derived mathematically from inherent risk and a control-effectiveness
value. See `app/models/risk_assessment.py`'s own docstring for where
that independence is enforced at the data-model level.

**`inherent_risk_score`/`inherent_risk_classification` are not
`enterprise-risk-v1` (item 10).** `app/intelligence/risk_score.py` is a
0-100 bounded, five-weighted-component score over recent event volume —
a completely different question ("how much recent activity, weighted, do
we see") from this matrix's own ("given a human/governed likelihood and
consequence judgment, what risk band does that represent"). The two
scores are never combined, never compared numerically, and
`RiskAssessmentRiskBand` is a distinct enum from `RiskClassification`
specifically so a "16/HIGH" matrix rating is never confused with a
"62/HIGH" `enterprise-risk-v1` score — see
`app/models/risk_assessment_enums.py`'s own docstring.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.models.risk_assessment_enums import RiskAssessmentRiskBand

RISK_ASSESSMENT_CALCULATION_VERSION = "risk-assessment-v1"

MIN_SCALE_VALUE = 1
MAX_SCALE_VALUE = 5


class InvalidRiskScaleValueError(ValueError):
    """Raised when a likelihood or consequence value is outside the
    governed 1-5 scale (item 28's own "invalid likelihood"/"invalid
    consequence" test cases) -- never silently clamped or coerced."""


@dataclass
class RiskRating:
    likelihood: int
    consequence: int
    score: int
    classification: str  # RiskAssessmentRiskBand value
    calculation_version: str = RISK_ASSESSMENT_CALCULATION_VERSION


def _validate_scale_value(value: int, *, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not (MIN_SCALE_VALUE <= value <= MAX_SCALE_VALUE):
        raise InvalidRiskScaleValueError(
            f"{field_name} must be an integer between {MIN_SCALE_VALUE} and {MAX_SCALE_VALUE} (got {value!r})."
        )


def classify_risk_score(score: int) -> RiskAssessmentRiskBand:
    """`score` is total, `1 <= score <= 25` for a value produced by
    `calculate_risk()` below -- exposed standalone (like
    `app/intelligence/recurrence.py::classify_recurrence()`'s own
    precedent) so every band boundary is directly, individually
    testable."""
    if score <= settings.RISK_ASSESSMENT_LOW_MAX:
        return RiskAssessmentRiskBand.LOW
    if score <= settings.RISK_ASSESSMENT_MODERATE_MAX:
        return RiskAssessmentRiskBand.MODERATE
    if score <= settings.RISK_ASSESSMENT_HIGH_MAX:
        return RiskAssessmentRiskBand.HIGH
    return RiskAssessmentRiskBand.CRITICAL


def calculate_risk(likelihood: int, consequence: int) -> RiskRating:
    """The one, deterministic `risk-assessment-v1` calculation --
    `likelihood x consequence`, classified via `classify_risk_score()`.
    Used identically for inherent risk and (independently) for residual
    risk -- see module docstring."""
    _validate_scale_value(likelihood, field_name="likelihood")
    _validate_scale_value(consequence, field_name="consequence")
    score = likelihood * consequence
    return RiskRating(
        likelihood=likelihood,
        consequence=consequence,
        score=score,
        classification=classify_risk_score(score).value,
    )


__all__ = [
    "RISK_ASSESSMENT_CALCULATION_VERSION",
    "MAX_SCALE_VALUE",
    "MIN_SCALE_VALUE",
    "InvalidRiskScaleValueError",
    "RiskRating",
    "calculate_risk",
    "classify_risk_score",
]
