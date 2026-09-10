"""IntelligenceOutcomeClassification — SIE Milestone 37: Field Outcome
Foundation. The one, closed, outcome vocabulary — mirrors
`IntelligenceDecisionType`'s own "genuinely typed, native Postgres enum,
not free text" precedent (`app/models/intelligence_decision_enums.py`):
what happened after an intervention is exactly the kind of small,
closed classification this codebase already reserves a native enum for.

Deliberately small (§3 of the milestone spec: "do not invent a huge
taxonomy") — four values, not an open-ended effectiveness scale.
"""

from enum import Enum


class IntelligenceOutcomeClassification(str, Enum):
    """The milestone's own minimum vocabulary, verbatim. Adding a member
    is a deliberate, reviewed code change, not routine data entry —
    mirrors every other native-enum vocabulary in this codebase."""

    #: The intervention resolved the condition the attention/decision
    #: concerned.
    EFFECTIVE = "EFFECTIVE"
    #: The intervention had some effect but did not fully resolve the
    #: condition.
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"
    #: The intervention did not resolve the condition.
    INEFFECTIVE = "INEFFECTIVE"
    #: An explicit human statement that an outcome could not be
    #: established (e.g. no follow-up was possible, or the evidence is
    #: inconclusive) — **never** used automatically merely because no
    #: outcome has been entered yet (see
    #: `app/models/intelligence_outcome.py`'s own docstring: an
    #: `IntelligenceOutcome` row is never created automatically at all,
    #: so this value is only ever a human's own explicit choice, the
    #: same way the other three are). The absence of any
    #: `IntelligenceOutcome` row is a different, and more common, state
    #: than a row that exists and says this.
    NO_OUTCOME_RECORDED = "NO_OUTCOME_RECORDED"


__all__ = ["IntelligenceOutcomeClassification"]
