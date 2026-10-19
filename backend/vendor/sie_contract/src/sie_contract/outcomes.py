"""Outcomes and Verification -- factual governance records, not the
learning loop (`sie-contract` 0.6.0).

An `IntelligenceOutcome` ("what happened after a decision") and an
`IntelligenceOutcomeVerification` ("was that outcome judged trustworthy")
are, like `IntelligenceDecision` before them, factual governance
records -- "what was recorded, when, by whom" is an audit fact, not "how
Commercial Core thinks". This module exposes exactly those facts and
nothing else.

**Not exclusively human-authored.** The recording/verifying actor is
`actor_type: ActorType` (`HUMAN` or `MACHINE`) + an opaque `actor_id`,
identical to `DecisionReferenceDTO`'s own convention -- mirrored here
deliberately rather than invented fresh. The internal models this
module's DTOs represent (`app/models/intelligence_outcome.py`'s
`recorded_by_user_id`/`recorded_by_api_client_id`,
`intelligence_outcome_verification.py`'s
`verified_by_user_id`/`verified_by_api_client_id`) already carry the
identical "exactly one of a user or an API client" shape
`IntelligenceDecision` itself uses, and the live Decisions write route
(`app/api/v1/intelligence_decisions.py::_actor_from_context()` in
Public SIE) already authorizes a machine (API-client) caller through
the same `Permission.INTELLIGENCE_DECISION_WRITE` gate the
(currently-stubbed) Outcomes/Verification routes also declare -- there
is no narrower, Outcome/Verification-specific restriction anywhere in
the authorization path. A factual record is "what was recorded, by
whom" regardless of whether that recorder was a person or an
authorized machine caller; this module does not assume or claim the
narrower case.

**What stays out, deliberately (see `../../docs/BOUNDARY_DECISIONS.md`
Section 14 for the full record of this exception).** The private
learning loop remains excluded: evidence-evaluation mechanics
(`EvidenceEvaluation`/`EvidenceStatus` -- *how* evidence is judged, not
*what* was recorded), the learning-eligibility gate
(`LearningEligibility`), and any combined verification-state
composition (`IntelligenceOutcomeVerificationStateRead`'s own shape) are
not mirrored here. A future contract version may expose a narrow,
separately-designed subset of these -- not decided by this module.

**Append-only, exactly like `DecisionReferenceDTO` (see `decisions.py`).**
There is no update/PATCH DTO here and none is planned: a correction is a
new record referencing the same `decision_id`/`outcome_id`, never an
in-place edit. This module cannot enforce that on its own (a DTO has no
behavior) -- the actual append-only guarantee lives in Commercial Core's
own write paths (`app/services/intelligence_outcome_service.py`,
`app/services/intelligence_outcome_verification_service.py`), which
never issue an `UPDATE` against either table. These DTOs simply never
offer a shape that would invite one.

**`NO_OUTCOME_RECORDED` is a value, never a default.** Mirrors
`app/models/intelligence_outcome_enums.py::IntelligenceOutcomeClassification`'s
own explicit instruction: this is the recording actor's affirmative
statement that no outcome could be established, constructed only when a real
`OutcomeReferenceDTO` instance is built with that classification. The
absence of any `OutcomeReferenceDTO` for a given decision is a different,
and far more common, state -- this module has no way to represent
"missing" as a value, which is the point: a caller that has no outcome
simply has no `OutcomeReferenceDTO`, not one carrying this classification.

**`recorded_at` vs. `outcome_at`/`verified_at` -- the same two-timestamp
discipline `IntelligenceOutcome`/`IntelligenceOutcomeVerification`
already establish internally.** `outcome_at`/`verified_at` is the
real-world instant the event/review happened (always caller-supplied on
the internal write path); `recorded_at` is when the record was
persisted (`created_at` on the internal model). The two are never
assumed equal and a consumer must not conflate them.

**Evidence restricted to `EvidenceType.SAFETY_EVENT` only, for this
release.** `EvidenceReference` itself supports six evidence types (see
`common.py`), but an Outcome's own internal `evidence_event_ids` field
is exclusively a `SafetyEvent` reference list -- no other evidence type
is meaningful for this domain today. Validated explicitly (not merely
documented) so a producer cannot accidentally widen this release's own
exposure by attaching an unsupported evidence type.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sie_contract.common import EvidenceReference, EvidenceType
from sie_contract.tenancy import ActorType


def _require_timezone_aware(value: datetime, *, field_name: str) -> datetime:
    """Shared by every datetime field in this module -- a naive
    datetime is ambiguous about which timezone it means, and this
    contract documents (README "Compatibility expectations") every
    timestamp as UTC, always explicit.

    **Checks both halves of Python's own "aware" definition, not just
    `tzinfo is None`.** Per the `datetime` module's own documentation, a
    datetime is aware only if `tzinfo is not None` *and*
    `tzinfo.utcoffset(dt)` does not return `None` -- a `tzinfo` object
    that is merely non-`None` but whose `utcoffset()` itself returns
    `None` is still naive for every real timezone-comparison purpose
    (pydantic/Python will not raise on construction, but any later
    comparison or arithmetic against it does). An earlier version of
    this validator checked only the first half; this checks both.

    **Does not require the UTC offset specifically.** This package has
    no existing precedent for enforcing UTC-only at the validator level
    -- `AsOfWindow`'s and `DecisionReferenceDTO.decided_at`'s own
    "UTC." field descriptions are a documented convention/expectation
    for a well-behaved producer, not a runtime-enforced restriction
    anywhere else in `sie_contract`. Rejecting a genuinely timezone-aware
    non-UTC offset here would be a stricter, inconsistent rule
    introduced only for this module, and a real breaking change for any
    caller that supplies a non-UTC offset today. This validator
    therefore accepts any timezone-aware datetime with a resolvable
    offset -- naive or ill-defined only is rejected -- and callers
    should still follow the documented UTC convention; the value's own
    offset is never normalized or rewritten, so the representation a
    caller supplies is exactly what round-trips back out."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be a timezone-aware datetime with a resolvable UTC offset "
            f"(tzinfo set and tzinfo.utcoffset() not None), not naive."
        )
    return value


class OutcomeClassification(str, Enum):
    """Mirrors `app/models/intelligence_outcome_enums.py::
    IntelligenceOutcomeClassification`'s four values -- a contract-owned
    enum, deliberately not importing that internal type (see module
    docstring and `../../docs/BOUNDARY_DECISIONS.md` Section 4's
    "zero Commercial Core internal imports" rule). Adding a member is a
    deliberate, coordinated contract-versioning event, not routine data
    entry -- same closed-vocabulary treatment `AttentionPriority`/
    `IntelligenceOutcomeVerificationStatus` (below) already get."""

    EFFECTIVE = "EFFECTIVE"
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"
    INEFFECTIVE = "INEFFECTIVE"
    #: An explicit statement by the recording actor that an outcome
    #: could not be established -- never used merely because no outcome has been
    #: entered yet. See module docstring's "NO_OUTCOME_RECORDED is a
    #: value, never a default" section.
    NO_OUTCOME_RECORDED = "NO_OUTCOME_RECORDED"


class OutcomeVerificationStatus(str, Enum):
    """Mirrors `app/models/intelligence_outcome_verification_enums.py::
    IntelligenceOutcomeVerificationStatus`'s three values -- a
    contract-owned enum, not an import of that internal type (same
    rule as `OutcomeClassification` above)."""

    VERIFIED = "VERIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DISPUTED = "DISPUTED"


class OutcomeReferenceDTO(BaseModel):
    """One observable, factual Outcome record. See module docstring for
    exactly which internal fields (evidence-evaluation detail, learning
    eligibility) were deliberately left out, and why this is not
    exclusively human-authored."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    decision_id: uuid.UUID = Field(..., description="The IntelligenceDecision this outcome reports the result of.")
    classification: OutcomeClassification
    summary: str = Field(..., min_length=1, max_length=4000, description="The recording actor's own account of why they believe this outcome occurred.")
    site_id: uuid.UUID | None = Field(default=None, description="Optional, independently supplied -- need not match decision_id's own site_id.")
    linked_action_id: uuid.UUID | None = Field(default=None, description="An existing SafetyAction id, when the recording actor chose to act through one. A Decision -> Outcome with no SafetyAction in between is equally legitimate.")
    evidence: list[EvidenceReference] = Field(default_factory=list, description="Restricted to EvidenceType.SAFETY_EVENT references only -- see module docstring.")
    outcome_at: datetime = Field(..., description="Timezone-aware, documented as UTC by this contract's convention (see the shared timezone validator's own docstring for exactly what is and isn't enforced). The real-world instant this outcome became observable/was established -- distinct from recorded_at.")
    recorded_at: datetime = Field(..., description="Timezone-aware, documented as UTC by this contract's convention. When this record was persisted -- distinct from outcome_at, which is very often earlier.")
    actor_type: ActorType
    actor_id: uuid.UUID = Field(..., description="Opaque reference to the recording actor -- aligned with DecisionReferenceDTO's identical actor_type/actor_id convention.")

    @field_validator("evidence")
    @classmethod
    def _evidence_restricted_to_safety_event(cls, value: list[EvidenceReference]) -> list[EvidenceReference]:
        for reference in value:
            if reference.evidence_type is not EvidenceType.SAFETY_EVENT:
                raise ValueError(
                    f"OutcomeReferenceDTO.evidence only accepts EvidenceType.SAFETY_EVENT references "
                    f"in this contract release, got {reference.evidence_type!r}."
                )
        return value

    @field_validator("outcome_at")
    @classmethod
    def _outcome_at_timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, field_name="outcome_at")

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, field_name="recorded_at")


class OutcomeListResultDTO(BaseModel):
    """A page of `OutcomeReferenceDTO`. Specialized rather than
    parametrized over `common.Page[T]` -- identical reasoning to
    `DecisionListResultDTO` (see `decisions.py`): mirrors `Page[T]`'s
    own field names (`items`/`total`/`page`/`page_size`) exactly, kept
    as its own concrete class so this DTO's `frozen=True` construction
    stays simple for callers, matching the one precedent this contract
    already established for a list envelope rather than introducing a
    second, inconsistent pagination shape."""

    model_config = ConfigDict(frozen=True)

    items: list[OutcomeReferenceDTO] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


class OutcomeVerificationReferenceDTO(BaseModel):
    """One observable, factual Verification record -- the recording
    actor's own judgment about whether a recorded `OutcomeReferenceDTO`
    is trustworthy. See module docstring for exactly which internal
    fields (evidence-evaluation detail, learning eligibility) were
    deliberately left out, why there is no combined verification-state
    DTO in this release, and why this is not exclusively human-authored."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    outcome_id: uuid.UUID = Field(..., description="The OutcomeReferenceDTO this verification judges.")
    status: OutcomeVerificationStatus
    rationale: str = Field(..., min_length=1, max_length=4000, description="The recording actor's own explanation for this verification judgment.")
    verified_at: datetime = Field(..., description="Timezone-aware, documented as UTC by this contract's convention. The real-world instant the recording actor reviewed the outcome/evidence -- distinct from recorded_at.")
    recorded_at: datetime = Field(..., description="Timezone-aware, documented as UTC by this contract's convention. When this record was persisted -- distinct from verified_at, which is very often earlier.")
    actor_type: ActorType
    actor_id: uuid.UUID = Field(..., description="Opaque reference to the verifying actor -- same convention as OutcomeReferenceDTO.actor_id.")

    @field_validator("verified_at")
    @classmethod
    def _verified_at_timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, field_name="verified_at")

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, field_name="recorded_at")


class OutcomeVerificationListResultDTO(BaseModel):
    """A page of `OutcomeVerificationReferenceDTO`. Same specialized-
    envelope convention as `OutcomeListResultDTO`/`DecisionListResultDTO`
    above -- see `OutcomeListResultDTO`'s own docstring."""

    model_config = ConfigDict(frozen=True)

    items: list[OutcomeVerificationReferenceDTO] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


__all__ = [
    "OutcomeClassification",
    "OutcomeVerificationStatus",
    "OutcomeReferenceDTO",
    "OutcomeListResultDTO",
    "OutcomeVerificationReferenceDTO",
    "OutcomeVerificationListResultDTO",
]
