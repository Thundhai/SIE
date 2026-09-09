"""OrganizationalMemory — SIE Milestone 40: Organizational Memory
Architecture. The durable, governed knowledge layer answering *"what
does this organization remember from verified operational experience?"*
-- the missing link the loop has needed since SIE Milestone 39's
`IntelligenceLearningCandidate`:

    POST /intelligence/decisions            -> IntelligenceDecision (M34)
        -> POST /intelligence/outcomes      -> IntelligenceOutcome (M37)
            -> POST .../verifications       -> IntelligenceOutcomeVerification (M38)
                -> POST .../learning-candidates
                                             -> IntelligenceLearningCandidate (M39)
                    -> POST .../governance-decisions (ACCEPTED)
                                             -> IntelligenceLearningCandidateGovernanceDecision (M39)
                        -> POST /intelligence/organizational-memory
                                             -> OrganizationalMemory (this model)
                            -> POST .../governance-decisions
                                             -> OrganizationalMemoryGovernanceDecision

**Still not the mechanism that changes SIE's intelligence (M40 spec
§1-2, §4).** This milestone establishes the architecture for durable,
governed organizational knowledge -- nothing here trains, retrains, or
adjusts a model; nothing here changes a threshold, a risk score,
prediction logic, ontology, terminology, or any intelligence rule. See
`docs/ORGANIZATIONAL_MEMORY_V0_1.md` for the full account, including the
explicit statement that `M41` (learning integration -- *how* SIE
actually uses this remembered knowledge) remains out of scope.

**Organizational memory is not a copy of everything that happened (M40
spec §2).** It is not an incident register, not an automatic ML
training dataset, not a generic JSON archive, and not created
automatically from every outcome or every accepted learning candidate.
Every `OrganizationalMemory` row is the direct, explicit result of one
`POST /intelligence/organizational-memory` call, made by an authorized
actor who has chosen to compose a specific, explicit knowledge
statement (`memory_content`) from a specific, already-`ACCEPTED`
learning candidate. Nothing infers, generates, or summarizes that
statement automatically -- no LLM is invoked anywhere in this
milestone's write path (M40 spec §9).

**The governance boundary is enforced in the write path, not merely
documented (M40 spec §5).** A memory may only be created from a
learning candidate whose *resolved current* governance decision
(`app/services/intelligence_learning_candidate_service.py::
resolve_current_governance()`, unchanged, unforked) is `ACCEPTED`.
`REJECTED`, pending (no governance decision at all), or a candidate that
does not exist/belongs to another organization are all rejected (404 or
422) at creation time -- see
`app/services/organizational_memory_service.py::
create_organizational_memory()`.

**Memory vs. learning candidate -- never conflated (M40 spec §6).**
`IntelligenceLearningCandidate`/its governance decision answer "may
this verified experience be considered for future learning, and has a
human accepted it as such?" `OrganizationalMemory` answers a
categorically different question: "what durable organizational
knowledge does the organization choose to remember from this accepted
experience?" The two are kept on entirely separate tables; creating a
memory never mutates the originating candidate or its governance
history.

**Provenance -- required, schema-hardened, one hop of context by
reference (M40 spec §7, §10).** `learning_candidate_id` is `NOT NULL`,
referenced via a *composite* foreign key `(learning_candidate_id,
organization_id) -> intelligence_learning_candidates(id,
organization_id)` -- mirroring `intelligence_learning_candidates`' own
SIE Milestone 39 composite-FK hardening exactly (safe here:
`ON DELETE CASCADE`, no `SET NULL` conflict). No outcome/verification
content is denormalized onto this row -- exactly like M39's own decision
not to denormalize onto `IntelligenceLearningCandidate` (both
`IntelligenceOutcome` and `IntelligenceOutcomeVerification` are already
immutable, already-persisted rows, so a live join through the candidate
always returns the same values forever). `app/api/v1/organizational_
memory.py`'s own read/list/state endpoints compose the full traceable
chain (memory -> candidate -> outcome + verification) live via
`db.get()` joins, exactly mirroring `IntelligenceLearningCandidateRead`'s
own established pattern -- a user can always answer "why does SIE
remember this?" by following that one response.

**Idempotent by construction (M40 spec §15).** `UNIQUE(organization_id,
learning_candidate_id)` -- at most one `OrganizationalMemory` per
accepted learning candidate, ever, mirroring
`IntelligenceLearningCandidate`'s own `UNIQUE(organization_id,
outcome_id)` precedent exactly: a repeat `POST /intelligence/
organizational-memory` for the same `learning_candidate_id` returns the
already-existing row rather than erroring or duplicating. This reflects
a deliberate design choice: one accepted candidate represents one
governed experience, and that experience earns exactly one canonical
memory record (which may itself later be elaborated via a governance
decision, e.g. `RETRACTED`, but never duplicated as a second, competing
memory row for the same candidate). This is a genuine, DB-enforced
natural key -- stronger than, and independent of, the `Idempotency-Key`
HTTP header support the create endpoint also offers.

**Immutable -- append-only, exactly like `IntelligenceOutcome`/
`IntelligenceLearningCandidate` (M40 spec §11).** No route ever issues
an `UPDATE` against this table. There is no `PUT`/`PATCH`/`DELETE`
endpoint, and none is planned -- the knowledge statement a memory
records is a historical fact about what the organization chose to
remember at creation time, not a living document. If a memory later
turns out to be outdated or wrong, that is itself recorded as a new,
append-only governance-decision row (`OrganizationalMemoryGovernanceDecision`,
below) -- never as a silent edit or deletion of the original statement.

**Actor governance and tenant scoping** -- identical shape to
`IntelligenceLearningCandidate`: exactly one of `created_by_user_id`/
`created_by_api_client_id` is set, derived from `RequestContext`, never
accepted as client input. `request_id` mirrors `AuditLog.request_id`
exactly. `OrganizationScopedMixin`, `ON DELETE CASCADE` on
`organization_id`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.organizational_memory_enums import OrganizationalMemoryGovernanceStatus, OrganizationalMemoryType


class OrganizationalMemory(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "organizational_memories"
    __table_args__ = (
        Index("ix_organizational_memories_org_candidate", "organization_id", "learning_candidate_id"),
        Index("ix_organizational_memories_org_memory_type", "organization_id", "memory_type"),
        # M40 spec §15 -- idempotent-by-construction natural key, see
        # module docstring's own "Idempotent by construction" section.
        UniqueConstraint(
            "organization_id", "learning_candidate_id", name="uq_organizational_memories_org_candidate"
        ),
        # Enables a genuine, DB-enforced composite foreign key from
        # OrganizationalMemoryGovernanceDecision.memory_id -- identical
        # precedent to intelligence_learning_candidates' own
        # UNIQUE(id, organization_id) constraint (SIE Milestone 39).
        UniqueConstraint("id", "organization_id", name="uq_organizational_memories_id_organization_id"),
        # M40 spec §5/§10 -- composite FK, mirroring intelligence_
        # learning_candidates' own SIE Milestone 39 hardening technique
        # (safe here: ON DELETE CASCADE, no SET NULL conflict).
        ForeignKeyConstraint(
            ["learning_candidate_id", "organization_id"],
            ["intelligence_learning_candidates.id", "intelligence_learning_candidates.organization_id"],
            ondelete="CASCADE",
            name="fk_organizational_memories_candidate_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` -- its reference is the composite
    # `ForeignKeyConstraint` above.
    learning_candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    memory_type: Mapped[OrganizationalMemoryType] = mapped_column(
        SAEnum(OrganizationalMemoryType, name="organizational_memory_type", native_enum=True), nullable=False
    )
    #: A short, human-scannable label -- never the full knowledge
    #: statement itself (that is `memory_content`, below).
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    #: The explicit, human-authored knowledge statement this memory
    #: exists to preserve -- never LLM-generated (module docstring's own
    #: "Organizational memory is not ... automatic" section). Required,
    #: non-empty (enforced at the schema layer).
    memory_content: Mapped[str] = mapped_column(Text, nullable=False)
    #: Why this specific statement was judged worth remembering --
    #: mirrors `IntelligenceOutcomeVerification.rationale`'s own "a
    #: governance record with no stated reason is not a complete record"
    #: rule. Required, non-empty.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    #: The originating HTTP request's id -- mirrors `AuditLog.request_id`/
    #: `IntelligenceLearningCandidate.request_id` exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # `overlaps=` silences SQLAlchemy's "will copy column
    # organization_id ... conflicts with relationship(s)" warning --
    # expected and correct here, identical reasoning to
    # `IntelligenceLearningCandidate.organization`/`.outcome`/
    # `.verification` (see that model's own docstring).
    organization: Mapped["Organization"] = relationship(overlaps="learning_candidate")  # noqa: F821
    learning_candidate: Mapped["IntelligenceLearningCandidate"] = relationship(  # noqa: F821
        overlaps="organization"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OrganizationalMemory id={self.id!s} organization_id={self.organization_id!s} "
            f"learning_candidate_id={self.learning_candidate_id!s} memory_type={self.memory_type!s}>"
        )


class OrganizationalMemoryGovernanceDecision(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    """One human governance judgment (`ACTIVE`/`RETRACTED`) about one
    `OrganizationalMemory` -- append-only, exactly like
    `IntelligenceLearningCandidateGovernanceDecision` is to
    `IntelligenceLearningCandidate` (M40 spec §11). No route ever issues
    an `UPDATE`/`DELETE` against this table either. A reviewer later
    retracting (or reinstating) a memory is a **second** row referencing
    the same `memory_id` -- never an in-place edit.
    `GET .../organizational-memory/{id}/governance-decisions`, ordered
    newest-first, *is* that history. The resolved *current* governance
    state for one memory is the single most recent row by `created_at
    DESC, id DESC` -- never an aggregate or a vote, mirroring
    `app/services/intelligence_learning_candidate_service.py::
    resolve_current_governance()`'s own identical rule, applied here by
    `app/services/organizational_memory_service.py::
    resolve_current_memory_governance()`. The *absence* of any row for a
    memory is its own, distinct, implicit `ACTIVE` state -- see
    `app/models/organizational_memory_enums.py`'s own docstring for why
    that differs from M39's own "absence = pending" convention.

    **`decided_at` is server-derived (`default=utcnow`), unlike
    `IntelligenceOutcome.outcome_at`/`IntelligenceOutcomeVerification.
    verified_at`.** A governance ACTIVE/RETRACTED action is made in the
    moment of the API call -- there is no "I decided this earlier and am
    filing it late" concept for a governance action, mirroring
    `IntelligenceLearningCandidateGovernanceDecision.decided_at`'s own
    identical reasoning.
    """

    __tablename__ = "organizational_memory_governance_decisions"
    __table_args__ = (
        Index(
            "ix_organizational_memory_gov_decisions_org_memory",
            "organization_id",
            "memory_id",
        ),
        # M40 spec §11 -- composite FK, mirroring the identical SIE
        # Milestone 39 hardening technique (safe here: ON DELETE CASCADE,
        # no SET NULL conflict). Requires organizational_memories' own
        # UNIQUE(id, organization_id) constraint, added in this same
        # migration.
        ForeignKeyConstraint(
            ["memory_id", "organization_id"],
            ["organizational_memories.id", "organizational_memories.organization_id"],
            ondelete="CASCADE",
            name="fk_organizational_memory_gov_decisions_memory_id_org_id",
        ),
    )

    # No inline `ForeignKey(...)` -- its reference is the composite
    # `ForeignKeyConstraint` above.
    memory_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    status: Mapped[OrganizationalMemoryGovernanceStatus] = mapped_column(
        SAEnum(
            OrganizationalMemoryGovernanceStatus,
            name="organizational_memory_governance_status",
            native_enum=True,
        ),
        nullable=False,
    )
    #: Required, non-empty -- "why this governance judgment," mirrors
    #: `IntelligenceLearningCandidateGovernanceDecision.rationale`'s own
    #: rule.
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

    organization: Mapped["Organization"] = relationship(overlaps="memory")  # noqa: F821
    memory: Mapped["OrganizationalMemory"] = relationship(overlaps="organization")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<OrganizationalMemoryGovernanceDecision id={self.id!s} "
            f"organization_id={self.organization_id!s} memory_id={self.memory_id!s} status={self.status!s}>"
        )


__all__ = ["OrganizationalMemory", "OrganizationalMemoryGovernanceDecision"]
