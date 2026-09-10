"""IntelligenceOutcomeVerificationStatus — SIE Milestone 38: Outcome
Verification & Evidence. The one, closed, verification-status vocabulary
— mirrors `IntelligenceOutcomeClassification`'s own "genuinely typed,
native Postgres enum, not free text" precedent
(`app/models/intelligence_outcome_enums.py`): whether a recorded outcome
is trustworthy enough to rely on is exactly the kind of small, closed
classification this codebase already reserves a native enum for.

Deliberately small (M38 spec §3: "do not add unnecessary states") —
three values, not an open-ended confidence scale.
"""

from enum import Enum


class IntelligenceOutcomeVerificationStatus(str, Enum):
    """A human's own explicit governance judgment about one recorded
    `IntelligenceOutcome` — never inferred, never automatic. Adding a
    member is a deliberate, reviewed code change, not routine data
    entry, mirroring every other native-enum vocabulary in this
    codebase."""

    #: A human reviewed the outcome and its evidence and accepts it as
    #: trustworthy. Writing this value is rejected at the API layer
    #: unless the outcome's own evidence deterministically evaluates as
    #: fully valid (see
    #: `app/services/intelligence_outcome_verification_service.py::
    #: evaluate_outcome_evidence()`) — a human's own affirmative
    #: judgment is necessary but not sufficient on its own.
    VERIFIED = "VERIFIED"
    #: The supplied evidence (or its absence) does not meet the bar for
    #: VERIFIED — never implies the outcome itself is wrong, only that
    #: it is not yet trustworthy enough to rely on.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    #: A human actively disagrees with the recorded outcome or its
    #: evidence (e.g. a second reviewer's field check contradicts the
    #: first report) — distinct from merely insufficient evidence.
    DISPUTED = "DISPUTED"


class EvidenceStatus(str, Enum):
    """The deterministic, structural outcome of evaluating one
    `IntelligenceOutcome`'s `evidence_event_ids` list (M38 spec §7's own
    A/B/C/D categories) — a **computed classification**, never persisted
    to any column (the evaluation is always recomputed live from current
    `SafetyEvent` rows plus the outcome's own fixed timestamps, so a
    plain Python enum is enough here; no native Postgres enum type,
    unlike `IntelligenceOutcomeVerificationStatus` above, since nothing
    ever stores this value in a row -- see
    `app/services/intelligence_outcome_verification_service.py::
    evaluate_outcome_evidence()`). Deliberately not a numeric score
    (spec: "do not introduce arbitrary weighted evidence scores")."""

    #: `evidence_event_ids` is empty or `None`.
    NO_EVIDENCE = "NO_EVIDENCE"
    #: At least one evidence id was supplied, but none of them passed
    #: validation (not found in this organization, or temporally
    #: invalid -- see the same function's own per-item checks).
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    #: A mix: at least one evidence id is valid, but at least one other
    #: is not -- not clean enough to call fully supported.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    #: Every supplied evidence id passed validation.
    VALID_EVIDENCE = "VALID_EVIDENCE"


__all__ = ["IntelligenceOutcomeVerificationStatus", "EvidenceStatus"]
