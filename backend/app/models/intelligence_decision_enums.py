"""IntelligenceDecisionType — SIE Milestone 34: Human Decision &
Intervention Trace. The one, closed, human-decision vocabulary — mirrors
`RiskAssessmentStatus`/`FindingStatus`/`ActionStatus`'s own "the decision
itself must be typed/enumerated" precedent (a native Postgres enum, not
a plain string): a human decision about intelligence is exactly the kind
of genuinely-typed status this codebase already reserves a native enum
for, distinct from the free-text `rationale` that always accompanies it.

Deliberately does **not** reuse or extend `AttentionCategory`
(`app/intelligence/attention.py`) or `RiskClassification`
(`app/intelligence/enums.py`) -- those are SIE's own signal vocabulary
("what SIE said"); this is the separate, human vocabulary ("what the
human decided"). §6 of the milestone spec is explicit that these must
never collapse into one taxonomy: SIE's priority is preserved verbatim
on the decision record (`IntelligenceDecision.attention_priority`),
completely independent of whatever the human here decides.
"""

from enum import Enum


class IntelligenceDecisionType(str, Enum):
    """The milestone's own minimum vocabulary, verbatim -- kept small and
    closed on purpose (§2's own "do not introduce vague free-text status
    values"). Adding a member is a deliberate, reviewed code change
    (mirrors every other native-enum vocabulary in this codebase), not
    routine data entry."""

    #: The human is responding to this signal by raising or linking an
    #: intervention (see `IntelligenceDecision.linked_action_id`) --
    #: never automatic; see that field's own docstring.
    ACT = "ACT"
    #: The human reviewed the signal and explicitly chose not to act on
    #: it -- e.g. "existing control verified effective" (§6's own
    #: worked example). Authoritative over SIE's own priority: SIE may
    #: have said HIGH, the human may still record DO_NOT_ACT.
    DO_NOT_ACT = "DO_NOT_ACT"
    #: Acknowledged, revisit later -- not a decision to act or not act
    #: yet.
    DEFER = "DEFER"
    #: The underlying condition is already being handled by something
    #: outside this one signal (e.g. a different, already-open action
    #: or assessment) -- distinct from DO_NOT_ACT ("chose not to") and
    #: from ACT ("responding now").
    ALREADY_ADDRESSED = "ALREADY_ADDRESSED"
    #: The human judges the signal does not actually warrant attention
    #: (e.g. a false positive, or context SIE could not see) --
    #: distinct from DO_NOT_ACT, which accepts the signal as real but
    #: chooses not to act on it.
    NOT_RELEVANT = "NOT_RELEVANT"


__all__ = ["IntelligenceDecisionType"]
