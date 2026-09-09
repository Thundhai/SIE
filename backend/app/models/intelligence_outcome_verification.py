"""IntelligenceOutcomeVerification — SIE Milestone 38: Outcome
Verification & Evidence. The governance layer answering *"can this
recorded outcome be trusted?"* — the missing link the loop has needed
since SIE Milestone 37's `IntelligenceOutcome`:

    POST /intelligence/decisions   -> IntelligenceDecision (M34)
        -> POST /intelligence/outcomes -> IntelligenceOutcome (M37)
            -> POST /intelligence/outcomes/{id}/verifications
                                    -> IntelligenceOutcomeVerification (this model)

**A recorded outcome is not automatically truth (M38 spec §2).** M37
deliberately never judged whether a recorded outcome was trustworthy —
a human could record `EFFECTIVE` with no evidence at all, and M37 has
no opinion on that. This milestone introduces the explicit distinction
the spec draws between five separate concepts, never collapsed into one
field:

1. what a human recorded (`IntelligenceOutcome`, unchanged from M37),
2. what evidence was supplied (`IntelligenceOutcome.evidence_event_ids`,
   unchanged),
3. whether that evidence is structurally/temporally sufficient
   (`app/services/intelligence_outcome_verification_service.py::
   evaluate_outcome_evidence()` — a computed, never-persisted
   evaluation, §7),
4. whether a human verified it (`IntelligenceOutcomeVerification` — this
   row, §3),
5. whether the outcome is eligible for future learning
   (`is_learning_eligible()` — a computed gate, §10).

**Still not the SIE learning engine.** Nothing in this milestone trains,
retrains, or adjusts any model, threshold, or priority. `is_learning_
eligible()` only answers a yes/no governance question about one outcome;
no code path reads that answer to actually learn anything — that remains
a distinct, out-of-scope future milestone (M39+). See
`docs/OUTCOME_VERIFICATION_V0_1.md` for the full account.

**"VALID EVIDENCE ≠ VERIFIED OUTCOME" (§8-9) — the central rule this
model enforces jointly with its own write path.** Evidence passing
`evaluate_outcome_evidence()`'s deterministic checks is a *necessary*
but never *sufficient* condition for a `VERIFIED` row: the API layer
(`app/api/v1/intelligence_outcomes.py::create_outcome_verification()`)
rejects an attempt to write `status=VERIFIED` when the outcome's own
evidence does not evaluate as fully valid, but a human choosing not to
verify an outcome whose evidence *is* valid is equally legitimate —
nothing here auto-promotes valid evidence into a `VERIFIED` row. The
reverse never happens either: no code path infers `VERIFIED` (or any
other status) merely from evidence being present, from `SafetyAction`
closure, or from the absence of a subsequent incident.

**Immutable — append-only, exactly like `IntelligenceOutcome`/
`IntelligenceDecision` (§4).** No route ever issues an `UPDATE` against
this table. There is no `PUT`/`PATCH`/`DELETE` endpoint. A correction
(a reviewer changing their mind, or a second reviewer disagreeing) is a
**second** `IntelligenceOutcomeVerification` row referencing the same
`outcome_id` — never an in-place edit.
`GET /intelligence/outcomes/{id}/verifications`, ordered newest-first
(`created_at DESC, id DESC` — the spec's own "prefer `created_at`
ordering" instruction), *is* that correction history. The **resolved
current state** for one outcome is deterministically defined as the
single most recent row by that same ordering
(`resolve_current_verification()`) — never an aggregate, a vote, or a
weighted combination of multiple verification rows.

**`verified_at` vs. `created_at` — mirrors `IntelligenceOutcome.
outcome_at` vs. `created_at` exactly (§6).** `verified_at` is the
real-world instant a human actually reviewed the outcome/evidence
(e.g. during a site audit) — always caller-supplied, since only the
reviewer knows it, and validated to never be in the future (an
identical rule to `IntelligenceOutcome.outcome_at`'s own "an outcome
describes something that already happened" discipline). `created_at`
(`TimestampMixin`) is when this row was written, which may be later.
Unlike `events_as_of()`'s two-timestamp evidence discipline (below),
`verified_at` is **not** itself used as a third temporal anchor for
evidence validity — see the "why evidence validity is anchored to the
outcome alone" section of
`app/services/intelligence_outcome_verification_service.py::
evaluate_outcome_evidence()`'s own docstring for the explicit reasoning
recorded there, per this milestone's own documentation requirement.

**Evidence temporal integrity is anchored to the *outcome*, not to any
one verification (§5-6).** `evaluate_outcome_evidence()` checks each of
`IntelligenceOutcome.evidence_event_ids` against exactly two fixed
timestamps already on the outcome itself: `SafetyEvent.event_time <=
IntelligenceOutcome.outcome_at` (the evidence must have genuinely
happened by the time the outcome became observable — reused precedent:
this is `events_as_of()`'s own `event_time` filter, applied here with
`outcome_at` playing the role `as_of` normally plays) and
`SafetyEvent.ingestion_time <= IntelligenceOutcome.created_at` (the
evidence must have already been in the system by the time the outcome
was recorded — reused precedent: `events_as_of()`'s own `ingestion_time`
filter, with `IntelligenceOutcome.created_at` playing the role of
`as_of`). This is the same "two timestamps, not one" discipline
`app/intelligence/temporal.py::events_as_of()` already established,
reused rather than reinvented (§6's own explicit instruction) — no new
temporal framework.

**Outcome relationship — required, schema-hardened (mirrors M37's own
`decision_id` treatment exactly).** `outcome_id` is `NOT NULL`,
referenced via a composite foreign key,
`(outcome_id, organization_id) -> intelligence_outcomes(id,
organization_id)`, safe here because `ON DELETE CASCADE` applies (no
`SET NULL`/`NOT NULL organization_id` conflict — see
`app/models/intelligence_outcome.py`'s own docstring for the general
rule this follows). `intelligence_outcomes` gains a new
`UNIQUE(id, organization_id)` constraint in this same migration to
support it (identical precedent to `intelligence_decisions`' own SIE
Milestone 37 constraint, and `sites`/`projects`' own SIE Milestone 35A
constraint before that).

**Actor governance and tenant scoping** — identical shape to
`IntelligenceOutcome`/`IntelligenceDecision`: exactly one of
`verified_by_user_id`/`verified_by_api_client_id` is set, derived from
`RequestContext`, never accepted as client input. `request_id` mirrors
`AuditLog.request_id`/`IntelligenceOutcome.request_id` exactly.
`OrganizationScopedMixin`, `ON DELETE CASCADE` on `organization_id`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.intelligence_outcome_verification_enums import IntelligenceOutcomeVerificationStatus


class IntelligenceOutcomeVerification(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_outcome_verifications"
    __table_args__ = (
        Index("ix_intelligence_outcome_verifications_org_outcome", "organization_id", "outcome_id"),
        Index("ix_intelligence_outcome_verifications_org_verified_at", "organization_id", "verified_at"),
        # SIE Milestone 39 -- enables a genuine, DB-enforced composite
        # foreign key from IntelligenceLearningCandidate.verification_id,
        # mirroring intelligence_outcomes' own identical SIE Milestone
        # 38 constraint (and intelligence_decisions' own SIE Milestone
        # 37 constraint before that). See
        # app/models/intelligence_learning_candidate.py's own docstring.
        UniqueConstraint(
            "id", "organization_id", name="uq_intelligence_outcome_verifications_id_organization_id"
        ),
        # SIE Milestone 38 -- see module docstring's "Outcome
        # relationship" section: mirrors intelligence_outcomes' own
        # SIE Milestone 37 composite-FK hardening of decision_id (safe
        # here: ON DELETE CASCADE, no SET NULL conflict).
        ForeignKeyConstraint(
            ["outcome_id", "organization_id"],
            ["intelligence_outcomes.id", "intelligence_outcomes.organization_id"],
            ondelete="CASCADE",
            name="fk_outcome_verifications_outcome_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` -- its reference is the composite
    # `ForeignKeyConstraint` above.
    outcome_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    status: Mapped[IntelligenceOutcomeVerificationStatus] = mapped_column(
        SAEnum(
            IntelligenceOutcomeVerificationStatus,
            name="intelligence_outcome_verification_status",
            native_enum=True,
        ),
        nullable=False,
    )
    #: Required, non-empty (enforced at the schema layer,
    #: `IntelligenceOutcomeVerificationCreate.rationale`) -- "why this
    #: judgment," mirrors `IntelligenceOutcome.summary`'s/
    #: `IntelligenceDecision.rationale`'s own "a governance record with
    #: no stated reason is not a complete record" rule.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    #: The real-world instant a human actually reviewed the outcome/
    #: evidence -- see module docstring's "verified_at vs. created_at"
    #: section. Always caller-supplied; never defaulted to "now".
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    #: The originating HTTP request's id -- mirrors `AuditLog.request_id`/
    #: `IntelligenceOutcome.request_id` exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # `overlaps=` silences SQLAlchemy's "will copy column
    # organization_id ... conflicts with relationship(s)" warning --
    # expected and correct here, identical reasoning to
    # `IntelligenceOutcome.organization`/`.decision` (see that model's
    # own docstring): both `organization` and `outcome` legitimately
    # reference this row's own `organization_id` column.
    organization: Mapped["Organization"] = relationship(overlaps="outcome")  # noqa: F821
    outcome: Mapped["IntelligenceOutcome"] = relationship(overlaps="organization")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntelligenceOutcomeVerification id={self.id!s} organization_id={self.organization_id!s} "
            f"outcome_id={self.outcome_id!s} status={self.status!s}>"
        )


__all__ = ["IntelligenceOutcomeVerification"]
