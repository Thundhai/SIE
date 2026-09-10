"""IntelligenceLearningCandidateGovernanceStatus — SIE Milestone 39:
Learning Candidate Foundation. The one, closed, governance-decision
vocabulary for a learning candidate — mirrors
`IntelligenceOutcomeVerificationStatus`'s own "genuinely typed, native
Postgres enum, not free text" precedent
(`app/models/intelligence_outcome_verification_enums.py`).

Deliberately small (M39 spec §8: "do not blindly implement states if
they create unnecessary workflow") — two values, not the full
ELIGIBLE/ACCEPTED/REJECTED/SUPERSEDED example the spec itself offers as
one option among several. `ELIGIBLE` is not a stored value here at all:
whether a verified outcome is *eligible* to become a candidate is a
live, deterministic, always-recomputable system check
(`app/services/intelligence_learning_candidate_service.py::
create_learning_candidate()` reuses M38's own
`evaluate_learning_eligibility()` as a write-time gate) — never a
governance state a human sets, so it has no place in this vocabulary
(see `app/models/intelligence_learning_candidate.py`'s own docstring
for the full "eligibility vs. acceptance" account, per spec §8's own
explicit instruction not to conflate the two). `SUPERSEDED` is likewise
omitted: nothing in this milestone's scope produces a "this candidate
replaces an earlier one" transition, and inventing that mechanics here
would be exactly the "build as much as possible" scope creep §28
warns against — a later milestone can add it if a genuine trigger for
it appears.
"""

from enum import Enum


class IntelligenceLearningCandidateGovernanceStatus(str, Enum):
    """A human's own explicit governance judgment about one
    `IntelligenceLearningCandidate` — never inferred, never automatic.
    The *absence* of any governance-decision row for a candidate is a
    distinct, and the initial, state ("pending" — not itself a member of
    this enum, mirroring `IntelligenceOutcomeClassification.
    NO_OUTCOME_RECORDED`'s own "absence is not the same as an explicit
    row" precedent, taken one step further here: there isn't even a
    value for it, since the absence of a row already answers the
    question unambiguously). Adding a member is a deliberate, reviewed
    code change, not routine data entry."""

    #: A human with governance authority admits this candidate into the
    #: future learning pipeline (M40/M41 — not built by this milestone).
    ACCEPTED = "ACCEPTED"
    #: A human with governance authority declines to admit this
    #: candidate — never implies the underlying outcome/verification
    #: was wrong, only that this experience should not (yet, or ever)
    #: feed future learning.
    REJECTED = "REJECTED"


__all__ = ["IntelligenceLearningCandidateGovernanceStatus"]
