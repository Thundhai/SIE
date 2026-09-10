"""TerminologyMappingDecision — SIE Real Enterprise Terminology & Ontology
Calibration v0.1, item 3: a persisted, versioned, auditable record of
*how a real source system's own term was decided to map (or not map) onto
SIE's canonical terminology* — never a second, competing mapping engine.

**Why this is a new table, not an extension of `HseExpertReview`.**
`app/models/hse_expert_review.py`'s own docstring is explicit that it is
"an evaluation mechanism only... nothing in this codebase reads
`HseExpertReview.outcome` and changes ingestion, mapping, or intelligence
behavior based on it." This milestone's whole point is the opposite: an
**approved** decision here *does* change what a future ingestion resolves
a term to (see `app/services/terminology_calibration_service.py`'s
`get_active_mapping()`, consulted by the calibration-aware adapter). That
is a fundamentally different guarantee than `HseExpertReview` makes, so it
needs its own model — but the existing HSE review *queue* is still reused
for visibility (`hse_expert_review_id` below links a candidate to the
queued `HseExpertReview` row a human already sees in the same place every
other pending review lives; see the service module for how the two stay
in sync without conflating their two different vocabularies).

**Lifecycle** (this milestone's own item 4):

    REVIEW_CANDIDATE -> PROPOSED -> APPROVED
                                  -> REJECTED

A row is created at `REVIEW_CANDIDATE` the moment a term is first
observed as unresolved (`UNKNOWN`/`AMBIGUOUS`) by the existing,
unmodified `terminology_review.py`. It may be mutated freely while in a
**non-terminal** state (`REVIEW_CANDIDATE`/`PROPOSED` — collectively
"PENDING", the umbrella term this milestone's own spec uses in its
data-quality rules) — but once it reaches a **terminal** state
(`APPROVED`/`REJECTED`), the row is frozen: the service layer refuses any
further mutation. A term whose already-decided mapping needs to change
later gets an entirely **new** row at the next `mapping_version` for the
same scope key (see below) — the old, terminal row is never overwritten,
so "which mapping was active as of a given moment" is always answerable
by querying history, never by trusting a single mutable "current" value.

**Scoping (item 7).** The natural key a decision applies under is
`(organization_id, source_system, domain, context, source_term,
mapping_version)` — never source_term alone. An approval for
`Organization A` / `alm-hse-xlsx` / `NearMiss` must never make
`Organization B` / `another-system` / `NearMiss` resolve to anything;
each combination gets its own, independent decision history. `context`
is the already-resolved canonical `event_type` a subtype/status decision
is scoped *under* (mirrors `TerminologyReviewEntry.context` exactly, same
reason: the same raw subtype string can mean different things under
different event types) — `None` for the `event_type` domain itself,
where there is no enclosing context to disambiguate by.

**PII.** Nothing here ever needs a worker's name or an incident
narrative — only the terminology term itself, an occurrence count, and
up to five *source_record_id* strings (an internal document identifier,
never a person) for traceability. See `example_source_record_ids`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class TerminologyMappingDecisionDomain:
    """Same four domains `terminology_review.py` already reviews —
    reused verbatim, not reinvented (item 3's own instruction: "the
    terminology domain must distinguish at least event_type/
    event_subtype... do not collapse these domains")."""

    EVENT_TYPE = "event_type"
    EVENT_SUBTYPE = "event_subtype"
    TRAINING_STATUS = "training_status"
    MAINTENANCE_STATUS = "maintenance_status"


DOMAINS = (
    TerminologyMappingDecisionDomain.EVENT_TYPE,
    TerminologyMappingDecisionDomain.EVENT_SUBTYPE,
    TerminologyMappingDecisionDomain.TRAINING_STATUS,
    TerminologyMappingDecisionDomain.MAINTENANCE_STATUS,
)


class TerminologyMappingDecisionStatus:
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


STATUSES = (
    TerminologyMappingDecisionStatus.REVIEW_CANDIDATE,
    TerminologyMappingDecisionStatus.PROPOSED,
    TerminologyMappingDecisionStatus.APPROVED,
    TerminologyMappingDecisionStatus.REJECTED,
)

#: The two non-terminal statuses — this milestone's spec section 11 calls
#: this umbrella state "PENDING" ("PENDING -> QUARANTINED"); kept as a
#: derived tuple here (never a fifth status value) for the same reason
#: `TerminologyReviewStatus.REVIEW_REQUIRED` is a flag over
#: `MappingOutcome`, not a new outcome of its own — see that module's own
#: docstring for the identical precedent.
PENDING_STATUSES = (TerminologyMappingDecisionStatus.REVIEW_CANDIDATE, TerminologyMappingDecisionStatus.PROPOSED)
TERMINAL_STATUSES = (TerminologyMappingDecisionStatus.APPROVED, TerminologyMappingDecisionStatus.REJECTED)


class TerminologyMappingDecision(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "terminology_mapping_decisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_system", "domain", "context", "source_term", "mapping_version",
            name="uq_terminology_mapping_decisions_scope_version",
        ),
    )

    # --- Scope key (item 7) ---------------------------------------------------------------
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # DOMAINS
    context: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_term: Mapped[str] = mapped_column(String(255), nullable=False)
    # Case/whitespace/punctuation-insensitive lookup key -- computed once
    # via the existing, unmodified `terminology_mapping._normalize_key()`
    # (never reimplemented here) so a scope lookup matches the exact same
    # way the static alias table itself already matches.
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # --- Versioning (item 8) ---------------------------------------------------------------
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Set when a later version's own review cycle begins for this same
    # scope key -- bookkeeping only (nothing queries this column to
    # decide eligibility; `get_active_mapping()` always looks at status +
    # mapping_version directly), kept so a reader can see at a glance that
    # this row is not the newest without a second query.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Decision content --------------------------------------------------------------------
    proposed_canonical_term: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=TerminologyMappingDecisionStatus.REVIEW_CANDIDATE, index=True
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # From the terminology review that created this candidate -- informational
    # only, never PII (a count and up to 5 internal document identifiers).
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    example_source_record_ids: Mapped[list[str]] = mapped_column(_JSONType, nullable=False, default=list)

    # --- Reviewer identity (item 9 — explicit, human, authorized) ---------------------------
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Integration with the existing HSE review queue (item 10) ---------------------------
    # Optional -- a candidate is queued for visibility in the same
    # existing HseExpertReview queue every other pending review already
    # lives in; this decision's own APPROVED/REJECTED outcome is never
    # read *from* that row (the reverse: this service *writes* a closing
    # outcome there once decided -- see terminology_calibration_service.py).
    hse_expert_review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hse_expert_reviews.id", ondelete="SET NULL"), nullable=True
    )

    # --- Provenance (item 14) ----------------------------------------------------------------
    # A snapshot of the underlying record provenance at candidate-creation
    # time (batch id, dataset label) -- mirrors HseExpertReview.provenance's
    # own "snapshot, not a live join" reasoning, so a decision remains
    # meaningful even if the batch/dataset it came from is later gone.
    provenance: Mapped[dict[str, Any]] = mapped_column(_JSONType, nullable=False, default=dict)

    organization: Mapped[Organization] = relationship()  # noqa: F821
    proposer: Mapped[User | None] = relationship(foreign_keys=[proposed_by_user_id])  # noqa: F821
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_user_id])  # noqa: F821

    @property
    def is_pending(self) -> bool:
        return self.status in PENDING_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_eligible_for_canonical_classification(self) -> bool:
        """The one boolean the ingestion-time resolver actually needs —
        item 11's own rule table, verbatim: only an APPROVED mapping is
        eligible; UNKNOWN/AMBIGUOUS/PENDING/REJECTED all remain
        quarantined."""
        return self.status == TerminologyMappingDecisionStatus.APPROVED

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TerminologyMappingDecision id={self.id!s} organization_id={self.organization_id!s} "
            f"source_system={self.source_system!r} domain={self.domain!r} source_term={self.source_term!r} "
            f"version={self.mapping_version} status={self.status!r}>"
        )


__all__ = [
    "DOMAINS",
    "PENDING_STATUSES",
    "STATUSES",
    "TERMINAL_STATUSES",
    "TerminologyMappingDecision",
    "TerminologyMappingDecisionDomain",
    "TerminologyMappingDecisionStatus",
]
