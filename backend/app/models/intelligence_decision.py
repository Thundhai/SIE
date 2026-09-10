"""IntelligenceDecision — SIE Milestone 34: Human Decision & Intervention
Trace. The first durable write in the SIE intelligence workflow
(M30-M33 were architecture/read-only): a governed record of *"when SIE
brought something to my attention, what did I decide, why, and what
intervention resulted"* — human decision provenance, never SIE making
the decision itself.

    GET /intelligence/attention          -> AttentionItem (M33, never persisted)
        -> human reviews it, decides
        -> POST /intelligence/decisions  -> IntelligenceDecision row (this model)
                                          -> optionally references an existing
                                             SafetyAction (linked_action_id)

**What SIE said vs. what the human decided — two separate, never-merged
fact sets on the same row (§6).** The `attention_*`/`intelligence_*`/
`calculation_version`/`evidence_*` columns are SIE's own signal, snapshot
at decision time, server-derived and never client-trusted (see
`app/services/intelligence_decision_service.py::resolve_attention_item()`
— they are re-derived from a fresh, `as_of`-pinned
`compose_attention()` call, never accepted as raw client input). The
`decision`/`rationale`/`decided_by_*`/`decided_at` columns are the
human's own, separate fact. SIE's priority is never recalculated or
overwritten by what the human decides, and the human's decision is never
inferred from SIE's priority — a HIGH-priority signal can carry a
`DO_NOT_ACT` decision on the very same row, both facts intact.

**Not a Field Intelligence Context snapshot.** This table stores the
small, bounded set of scalar/short-list fields listed above — never a
copy of the full M32 `FieldIntelligenceContextResult` or the full M33
`AttentionResult`. `attention_reference` is the durable link back to
*which* signal this was (see `app/intelligence/attention.py::
build_attention_reference()`'s own docstring for why it is deterministic
rather than a random opaque id); the underlying computation itself is
never persisted, only replayable (an `as_of`-pinned `compose_attention()`
call is deterministic given the same historical data, per M32/M33's own
point-in-time discipline).

**Immutable — the row is never updated after creation.** No route in
`app/api/v1/intelligence_decisions.py` ever issues an `UPDATE` against
this table (mirrors `RiskAssessmentHistory`/`SafetyActionHistory`'s own
"immutable by convention, no route accepts it as editable input"
guarantee). A human who changes their mind records a **new** row with
the same `attention_reference` — the append-only sequence of rows
sharing one `attention_reference`, ordered by `decided_at`, *is* the
decision history (§9's own "smallest durable mechanism that preserves
auditability": no separate `IntelligenceDecisionHistory` table is
needed, because there is no single row that ever changes — a second
table would only ever hold a 1:1, permanently-redundant mirror of this
one's own `CREATED` event). "Original decision → subsequent decision →
who changed it → when → why" is answered by
`GET /intelligence/decisions?attention_reference=...`, newest first;
nothing is ever silently overwritten or destroyed. The platform-wide
`AuditLog` (`AuditAction.INTELLIGENCE_DECISION_RECORDED`) is written
alongside every row, exactly as every other domain write in this
codebase already does.

**Tenant-scoped** (`OrganizationScopedMixin`), `ON DELETE CASCADE` on
`organization_id` — a decision has no meaning independent of the
organization it belongs to, the same reasoning every other genuinely
tenant-owned table in this schema already follows.

**`linked_action_id` is optional and never automatic** (§5, §10 — "do
not automatically create an action merely because the decision is
ACT"). Set only when the human explicitly supplies an existing
`SafetyAction.id` in the request body, validated with
`app.services.risk_assessment_service.resolve_action_reference()` (the
same tenant-ownership check `app/api/v1/risk_assessments.py`'s own
finding-action linking already reuses) — never a second action-creation
or action-linking mechanism. `ON DELETE SET NULL`: the decision record
must never disappear merely because the action it once named is later
deleted (no route deletes a `SafetyAction` today, but the schema-level
guarantee mirrors every other `..._id` reference to it in this codebase).
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.intelligence_decision_enums import IntelligenceDecisionType

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class IntelligenceDecision(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_decisions"
    __table_args__ = (
        Index("ix_intelligence_decisions_org_attention_ref", "organization_id", "attention_reference"),
        Index("ix_intelligence_decisions_org_site", "organization_id", "site_id"),
        Index("ix_intelligence_decisions_org_decided_at", "organization_id", "decided_at"),
        Index("ix_intelligence_decisions_org_linked_action", "organization_id", "linked_action_id"),
        # SIE Milestone 37 -- enables a genuine, DB-enforced composite
        # foreign key from IntelligenceOutcome.decision_id, mirroring
        # sites'/projects' own identical SIE Milestone 35A constraint.
        # See app/models/intelligence_outcome.py's own docstring.
        UniqueConstraint("id", "organization_id", name="uq_intelligence_decisions_id_organization_id"),
    )

    # --- Scope -----------------------------------------------------------------------------
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: "organization" | "site" -- echoes the `compose_attention()` scope
    #: the human was viewing; a plain string like every other
    #: scope/classification field copied from an intelligence
    #: computation in this codebase (mirrors
    #: `RiskAssessmentFinding.inherent_risk_classification`'s own
    #: "closed vocabulary enforced by the producing layer, not a second
    #: DB-native enum" convention).
    scope: Mapped[str] = mapped_column(String(20), nullable=False)

    # --- What SIE said (server-derived snapshot, never client-trusted) --------------------
    #: See `app/intelligence/attention.py::build_attention_reference()`.
    attention_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    attention_category: Mapped[str] = mapped_column(String(50), nullable=False)  # AttentionCategory value
    attention_priority: Mapped[str] = mapped_column(String(20), nullable=False)  # RiskClassification value
    attention_title: Mapped[str] = mapped_column(String(255), nullable=False)
    attention_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    intelligence_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    intelligence_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: From the attention item's own `evidence.calculation_version` --
    #: `NULL` when the underlying category carries none (e.g.
    #: `OVERDUE_ACTIONS`/`UNRESOLVED_FINDING`, whose evidence is a
    #: direct row reference, not a versioned calculation).
    calculation_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Bounded id lists (never more than the handful M33's own
    #: `_MAX_EVIDENCE_EVENT_IDS`-style caps already produce) -- a
    #: reference list, never a copy of the referenced rows' content.
    evidence_entity_ids: Mapped[list | None] = mapped_column(_JSONType, nullable=True)
    evidence_event_ids: Mapped[list | None] = mapped_column(_JSONType, nullable=True)

    # --- What the human decided (authoritative, independent of the above) -----------------
    decision: Mapped[IntelligenceDecisionType] = mapped_column(
        SAEnum(IntelligenceDecisionType, name="intelligence_decision_type", native_enum=True), nullable=False
    )
    #: Required, non-empty (enforced at the schema layer,
    #: `IntelligenceDecisionCreate.rationale`) -- the milestone's own
    #: central question is "why did they decide it," so a decision with
    #: no stated reason is not a complete record.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    linked_action_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_actions.id", ondelete="SET NULL"), nullable=True
    )

    # --- Human authority (exactly one of these two is set, never both) --------------------
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    #: The originating HTTP request's id -- mirrors `AuditLog.request_id`/
    #: `SafetyActionHistory.request_id`/`RiskAssessmentHistory.request_id`
    #: exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    linked_action: Mapped["SafetyAction | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntelligenceDecision id={self.id!s} organization_id={self.organization_id!s} "
            f"attention_reference={self.attention_reference!r} decision={self.decision!s}>"
        )


__all__ = ["IntelligenceDecision"]
