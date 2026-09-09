"""IntelligenceLearningCandidate — SIE Milestone 39: Learning Candidate
Foundation. The governed bridge answering *"may this verified
operational experience be considered by future learning?"* — the
missing link the loop has needed since SIE Milestone 38's
`IntelligenceOutcomeVerification`:

    POST /intelligence/decisions        -> IntelligenceDecision (M34)
        -> POST /intelligence/outcomes  -> IntelligenceOutcome (M37)
            -> POST .../verifications   -> IntelligenceOutcomeVerification (M38)
                -> POST /intelligence/learning-candidates
                                         -> IntelligenceLearningCandidate (this model)
                    -> POST .../governance-decisions
                                         -> IntelligenceLearningCandidateGovernanceDecision

**Still not the SIE learning engine (M39 spec §1-2, §12).** This
milestone establishes the architecture and governance boundary at the
entry to `LEARN` — nothing here trains, retrains, or adjusts a model;
nothing here changes a threshold, a risk score, prediction logic,
ontology, terminology, or any intelligence rule. See
`docs/LEARNING_CANDIDATE_V0_1.md` for the full account, including the
explicit statement that `M40` (organizational memory) and `M41`
(learning integration) remain out of scope.

**A verified outcome is evidence that something happened; a learning
candidate is a governed representation that this verified experience
*may* be useful for future learning (M39 spec §3).** These are kept
separate deliberately: creating a candidate never mutates the
originating `IntelligenceOutcome` or `IntelligenceOutcomeVerification`
row — both stay exactly as immutable as M37/M38 already made them.

**Eligibility vs. acceptance — never conflated (M39 spec §8).**
*Eligibility* is a deterministic, always-recomputable system check:
"is this verified outcome technically eligible to become a learning
candidate?" — reuses
`app/services/intelligence_outcome_verification_service.py::
evaluate_learning_eligibility()` verbatim as the one write-time gate
(`app/services/intelligence_learning_candidate_service.py::
create_learning_candidate()`), never forked or duplicated (spec §6's
own explicit instruction). *Acceptance* is a separate governance
decision a human makes about a candidate that already exists — see
`IntelligenceLearningCandidateGovernanceDecision` below. A verified
outcome can be technically eligible (and therefore have a candidate
row) without that candidate ever being `ACCEPTED`.

**Verification requirement (M39 spec §6).** A candidate may only be
created from an outcome whose *resolved current* verification
(`app/services/intelligence_outcome_verification_service.py::
resolve_current_verification()`, unchanged, unforked) is `VERIFIED` —
`INSUFFICIENT_EVIDENCE`, `DISPUTED`, or no verification at all are all
rejected (422) at creation time, never silently coerced into eligible.

**Provenance — required, schema-hardened, never detachable (M39 spec
§5).** `outcome_id` and `verification_id` are both `NOT NULL`,
referenced via *composite* foreign keys — `(outcome_id,
organization_id) -> intelligence_outcomes(id, organization_id)` and
`(verification_id, organization_id) -> intelligence_outcome_
verifications(id, organization_id)` — mirroring `intelligence_
outcomes`'/`intelligence_outcome_verifications`' own SIE Milestone
37/38 composite-FK hardening exactly (safe here: both relationships are
`ON DELETE CASCADE`, no `SET NULL` conflict). `intelligence_outcome_
verifications` gains a new `UNIQUE(id, organization_id)` constraint in
this same migration to support the second one (identical precedent to
`intelligence_outcomes`' own SIE Milestone 38 constraint, and
`intelligence_decisions`' own SIE Milestone 37 constraint before that).
`verification_id` is deliberately *pinned* to the exact row that made
this candidate eligible at creation time — never re-pointed later, even
if a subsequent verification row is recorded for the same outcome (an
outcome can only ever have one candidate, per the uniqueness constraint
below, so this is a fixed historical fact, not a value that needs to
track "whatever the latest verification currently says").

**Decision/intervention/site/evidence context — read via the existing
join pattern, never denormalized onto this row (M39 spec §11's "do not
create an unrestricted generic JSON dumping ground," resolved by
reusing the identical `_to_read()`-style composition
`app/api/v1/intelligence_outcomes.py` already established for
`IntelligenceOutcomeRead`/`IntelligenceOutcomeVerificationRead`,
rather than copying fields).** Unlike `IntelligenceDecision`'s own
snapshot of "what SIE said" (necessary there because the *computation*
producing an `AttentionItem` is never persisted anywhere else),
`IntelligenceOutcome` and `IntelligenceOutcomeVerification` are already
immutable, already-persisted rows — a live read through `outcome_id`/
`verification_id` returns the identical classification/`outcome_at`/
`evidence_event_ids`/`decision_id`/`site_id` forever, so denormalizing
any of it here would be pure redundancy, not a temporal-integrity
requirement. `app/api/v1/intelligence_learning_candidates.py`'s own
read/list/state endpoints compose this context live, exactly mirroring
`IntelligenceOutcomeRead.decision`/`.linked_action` today.

**Evidence revalidation — computed live, never stored (M39 spec §20).**
"Verified at time T" (the pinned `verification_id`, fixed forever) is
kept distinct from "currently revalidated" (a live
`evaluate_outcome_evidence()` recomputation, exposed only by
`GET .../learning-candidates/{id}/state`, never persisted on this row)
— reuses M38's own machinery verbatim, no elaborate new verification
system.

**Idempotent by construction (M39 spec §15).** `UNIQUE(organization_id,
outcome_id)` — at most one `IntelligenceLearningCandidate` per outcome,
ever. Mirrors `ProjectSite`'s own "(project_id, site_id) is unique —
linking twice is a no-op, the existing row is returned, no duplicate
created" precedent exactly: a repeat `POST /intelligence/
learning-candidates` for the same `outcome_id` returns the
already-existing row rather than erroring or duplicating. This is a
genuine, DB-enforced natural key — stronger than, and independent of,
the `Idempotency-Key` HTTP header support the create endpoint also
offers (mirroring every other write route in this codebase), which
additionally guarantees exact response replay on a retried request.

**Immutable — append-only, exactly like `IntelligenceOutcome`/
`IntelligenceOutcomeVerification` (§10).** No route ever issues an
`UPDATE` against this table. There is no `PUT`/`PATCH`/`DELETE`
endpoint. Governance decisions about a candidate are recorded on the
separate `IntelligenceLearningCandidateGovernanceDecision` table below
— never by mutating this row.

**Actor governance and tenant scoping** — identical shape to
`IntelligenceOutcome`/`IntelligenceOutcomeVerification`: exactly one of
`created_by_user_id`/`created_by_api_client_id` is set, derived from
`RequestContext`, never accepted as client input. `request_id` mirrors
`AuditLog.request_id` exactly. `OrganizationScopedMixin`, `ON DELETE
CASCADE` on `organization_id`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.intelligence_learning_candidate_enums import IntelligenceLearningCandidateGovernanceStatus


class IntelligenceLearningCandidate(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_learning_candidates"
    __table_args__ = (
        Index("ix_intelligence_learning_candidates_org_outcome", "organization_id", "outcome_id"),
        Index("ix_intelligence_learning_candidates_org_verification", "organization_id", "verification_id"),
        # M39 spec §15 -- idempotent-by-construction natural key, see
        # module docstring's own "Idempotent by construction" section.
        UniqueConstraint("organization_id", "outcome_id", name="uq_intelligence_learning_candidates_org_outcome"),
        # Enables a genuine, DB-enforced composite foreign key from
        # IntelligenceLearningCandidateGovernanceDecision.candidate_id --
        # identical precedent to intelligence_outcomes'/intelligence_
        # outcome_verifications' own UNIQUE(id, organization_id)
        # constraints (SIE Milestones 37/38).
        UniqueConstraint("id", "organization_id", name="uq_intelligence_learning_candidates_id_organization_id"),
        # M39 spec §5/§19 -- composite FKs, mirroring intelligence_
        # outcomes'/intelligence_outcome_verifications' own SIE
        # Milestone 37/38 hardening (safe here: ON DELETE CASCADE, no
        # SET NULL conflict).
        ForeignKeyConstraint(
            ["outcome_id", "organization_id"],
            ["intelligence_outcomes.id", "intelligence_outcomes.organization_id"],
            ondelete="CASCADE",
            name="fk_learning_candidates_outcome_id_organization_id",
        ),
        ForeignKeyConstraint(
            ["verification_id", "organization_id"],
            ["intelligence_outcome_verifications.id", "intelligence_outcome_verifications.organization_id"],
            ondelete="CASCADE",
            name="fk_learning_candidates_verification_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` on either -- their references are the
    # composite `ForeignKeyConstraint`s above.
    outcome_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: Pinned to the exact verification row that made this candidate
    #: eligible at creation time -- see module docstring's own
    #: "Provenance" section for why this is never re-pointed later.
    verification_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    #: The originating HTTP request's id -- mirrors `AuditLog.request_id`/
    #: `IntelligenceOutcomeVerification.request_id` exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # `overlaps=` silences SQLAlchemy's "will copy column
    # organization_id ... conflicts with relationship(s)" warning --
    # expected and correct here, identical reasoning to
    # `IntelligenceOutcomeVerification.organization`/`.outcome` (see
    # that model's own docstring): `organization`, `outcome`, and
    # `verification` all legitimately reference this row's own
    # `organization_id` column.
    organization: Mapped["Organization"] = relationship(overlaps="outcome,verification")  # noqa: F821
    outcome: Mapped["IntelligenceOutcome"] = relationship(overlaps="organization,verification")  # noqa: F821
    verification: Mapped["IntelligenceOutcomeVerification"] = relationship(  # noqa: F821
        overlaps="organization,outcome"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntelligenceLearningCandidate id={self.id!s} organization_id={self.organization_id!s} "
            f"outcome_id={self.outcome_id!s} verification_id={self.verification_id!s}>"
        )


class IntelligenceLearningCandidateGovernanceDecision(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    """One human governance judgment (`ACCEPTED`/`REJECTED`) about one
    `IntelligenceLearningCandidate` — append-only, exactly like
    `IntelligenceOutcomeVerification` is to `IntelligenceOutcome` (M39
    spec §9-10). No route ever issues an `UPDATE`/`DELETE` against this
    table either. A reviewer changing their mind is a **second** row
    referencing the same `candidate_id` — never an in-place edit.
    `GET .../learning-candidates/{id}/governance-decisions`, ordered
    newest-first, *is* that history. The resolved *current* governance
    state for one candidate is the single most recent row by
    `created_at DESC, id DESC` — never an aggregate or a vote, mirroring
    `app/services/intelligence_outcome_verification_service.py::
    resolve_current_verification()`'s own identical rule, applied here
    by `app/services/intelligence_learning_candidate_service.py::
    resolve_current_governance()`. The *absence* of any row for a
    candidate is its own, distinct, initial ("pending") state — see
    `app/models/intelligence_learning_candidate_enums.py`'s own
    docstring for why that state has no enum member of its own.

    **`decided_at` is server-derived (`default=utcnow`), unlike
    `IntelligenceOutcome.outcome_at`/`IntelligenceOutcomeVerification.
    verified_at`.** A governance ACCEPT/REJECT is made in the moment of
    the API call — there is no "I decided this earlier and am filing it
    late" concept for a governance action the way there genuinely is for
    a field-reported outcome or a site-visit verification, so no
    separate backdating discipline is needed here; this mirrors
    `IntelligenceDecision.decided_at`'s own identical reasoning.
    """

    __tablename__ = "intelligence_learning_candidate_governance_decisions"
    __table_args__ = (
        Index(
            "ix_intelligence_learning_candidate_gov_decisions_org_candidate",
            "organization_id",
            "candidate_id",
        ),
        # M39 spec §18-19 -- composite FK, mirroring the identical
        # SIE Milestone 37/38 hardening technique (safe here: ON DELETE
        # CASCADE, no SET NULL conflict). Requires
        # intelligence_learning_candidates' own UNIQUE(id,
        # organization_id) constraint, added in this same migration.
        ForeignKeyConstraint(
            ["candidate_id", "organization_id"],
            ["intelligence_learning_candidates.id", "intelligence_learning_candidates.organization_id"],
            ondelete="CASCADE",
            name="fk_learning_candidate_gov_decisions_candidate_id_org_id",
        ),
    )

    # No inline `ForeignKey(...)` -- its reference is the composite
    # `ForeignKeyConstraint` above.
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    status: Mapped[IntelligenceLearningCandidateGovernanceStatus] = mapped_column(
        SAEnum(
            IntelligenceLearningCandidateGovernanceStatus,
            name="intelligence_learning_candidate_governance_status",
            native_enum=True,
        ),
        nullable=False,
    )
    #: Required, non-empty (enforced at the schema layer) -- "why this
    #: governance judgment," mirrors `IntelligenceOutcomeVerification.
    #: rationale`'s own "a governance record with no stated reason is
    #: not a complete record" rule.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    organization: Mapped["Organization"] = relationship(overlaps="candidate")  # noqa: F821
    candidate: Mapped["IntelligenceLearningCandidate"] = relationship(overlaps="organization")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntelligenceLearningCandidateGovernanceDecision id={self.id!s} "
            f"organization_id={self.organization_id!s} candidate_id={self.candidate_id!s} status={self.status!s}>"
        )


__all__ = ["IntelligenceLearningCandidate", "IntelligenceLearningCandidateGovernanceDecision"]
