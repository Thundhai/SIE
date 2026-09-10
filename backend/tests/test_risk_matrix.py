"""SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1 —
`app/risk_assessment/risk_matrix.py`. Pure unit tests (no database),
covering item 28's "Risk calculation" test list in full.
"""

import pytest

from app.models.risk_assessment_enums import RiskAssessmentRiskBand
from app.risk_assessment.risk_matrix import (
    InvalidRiskScaleValueError,
    calculate_risk,
    classify_risk_score,
)


def test_one_by_one_is_the_minimum_score_and_low():
    rating = calculate_risk(1, 1)
    assert rating.score == 1
    assert rating.classification == RiskAssessmentRiskBand.LOW.value


def test_five_by_five_is_the_maximum_score_and_critical():
    rating = calculate_risk(5, 5)
    assert rating.score == 25
    assert rating.classification == RiskAssessmentRiskBand.CRITICAL.value


def test_the_milestones_own_worked_example_is_reproduced_exactly():
    rating = calculate_risk(4, 4)
    assert rating.score == 16
    assert rating.classification == RiskAssessmentRiskBand.HIGH.value


@pytest.mark.parametrize(
    "score,expected",
    [
        (1, "LOW"), (4, "LOW"),
        (5, "MODERATE"), (9, "MODERATE"),
        (10, "HIGH"), (16, "HIGH"),
        (17, "CRITICAL"), (25, "CRITICAL"),
    ],
)
def test_every_band_boundary(score, expected):
    assert classify_risk_score(score).value == expected


def test_deterministic_repeated_calculation():
    first = calculate_risk(3, 4)
    second = calculate_risk(3, 4)
    assert first == second


@pytest.mark.parametrize("likelihood", [0, -1, 6, 100])
def test_invalid_likelihood_is_rejected(likelihood):
    with pytest.raises(InvalidRiskScaleValueError):
        calculate_risk(likelihood, 3)


@pytest.mark.parametrize("consequence", [0, -1, 6, 100])
def test_invalid_consequence_is_rejected(consequence):
    with pytest.raises(InvalidRiskScaleValueError):
        calculate_risk(3, consequence)


def test_calculation_version_is_recorded_and_versioned():
    rating = calculate_risk(2, 2)
    assert rating.calculation_version == "risk-assessment-v1"


def test_the_calculation_is_a_simple_product_not_a_lookup_table_surprise():
    for likelihood in range(1, 6):
        for consequence in range(1, 6):
            rating = calculate_risk(likelihood, consequence)
            assert rating.score == likelihood * consequence
