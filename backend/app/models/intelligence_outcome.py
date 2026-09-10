"""IntelligenceOutcome — SIE Milestone 37: Field Outcome Foundation. The
first durable record of *what happened after* a human decision/
intervention — the missing link the loop has needed since SIE Milestone
34:

    GET /intelligence/attention          -> AttentionItem (M33, never persisted)
        -> human reviews it, decides
        -> POST /intelligence/decisions  -> IntelligenceDecision (M34)
                                          -> optionally references an existing SafetyAction
        -> POST /intelligence/outcomes   -> IntelligenceOutcome row (this model)

**A ground-truth capture layer, not the SIE learning engine.** This
milestone only records what a human observed/reported happened; no
model retraining, feature generation, prediction update, or automatic
risk/attention recalculation reads this table. See
`docs/FIELD_OUTCOME_FOUNDATION_V0_1.md` for the full "what an outcome
is / is not" account and the explicit statement that `... -> OUTCOME ->
LEARN` remains outside this milestone.

**An outcome is not an action, and is never created automatically.**
`SafetyAction`/`SafetyActionHistory` (SIE Milestone 17) record *what
intervention was performed*; this table records *what happened as a
result* — a distinct governed concept, mirroring the milestone spec's
own worked example (Attention -> Decision(ACT) -> SafetyAction ->
Outcome(EFFECTIVE) -> Evidence). No route anywhere in this codebase
creates an `IntelligenceOutcome` row except the one explicit
`POST /intelligence/outcomes` a human or authorized machine client
calls — never inferred from `SafetyAction.status` transitioning to
`COMPLETED`/`CANCELLED` (closure does not prove effectiveness — see
`app/models/safety_action.py`'s own "Closure semantics" section, which
this milestone deliberately does not touch), and never inferred from
the absence of a subsequent `SafetyEvent` at the same site.

**Immutable — append-only, exactly like `IntelligenceDecision` (§6).**
No route ever issues an `UPDATE` against this table. There is no
`PUT`/`PATCH` endpoint, and none is planned for this milestone: if a
later verification needs to correct or supersede a previously recorded
outcome (e.g. "recorded INEFFECTIVE on day 3, but a day-30 follow-up
confirms EFFECTIVE"), the governed mechanism is a **second**
`IntelligenceOutcome` row referencing the same `decision_id` — never an
in-place edit. `GET /intelligence/outcomes?decision_id=...`, ordered
newest-first by `outcome_at`, *is* that correction history — identical
reasoning to `IntelligenceDecision`'s own "the append-only sequence of
rows sharing one `attention_reference` is the decision history"
(§9's "smallest durable mechanism that preserves auditability": no
separate `IntelligenceOutcomeHistory`/correction table is needed,
because there is no single row that is ever mutated). The initial M37
implementation deliberately favors this simple append-only model over a
correction workflow with its own status/supersession fields — see
`docs/FIELD_OUTCOME_FOUNDATION_V0_1.md` for that decision recorded
explicitly, per the milestone spec's own instruction to document it.

**`outcome_at` vs. `created_at` — two distinct timestamps, never
conflated (§7).** `outcome_at` is the real-world instant the outcome
became observable/was established (e.g. the date of a follow-up
inspection) — always caller-supplied, since only the reporting human
can know it; `created_at` (`TimestampMixin`) is when this row was
written to the database, which is very often later than `outcome_at`
(the whole reason the two must be distinct columns — a decision's own
`decided_at`, by contrast, has no such gap, since a decision is made at
the moment it is recorded, so `IntelligenceDecision` did not need this
split). `app/api/v1/intelligence_outcomes.py`'s own point-in-time list
filter checks **both** `outcome_at <= as_of` and `created_at <= as_of`
— mirroring `app/intelligence/temporal.py::events_as_of()`'s own
`event_time`/`ingestion_time` dual-timestamp discipline exactly (never
a second, competing temporal framework — see that module's own
docstring): the first guarantees the outcome had genuinely happened by
`as_of`; the second guarantees it was already *known* by `as_of` (a
backdated `outcome_at` entered after the fact must not leak into an
earlier historical reconstruction merely because its own `outcome_at`
predates `as_of`).

**Decision relationship — required, tenant-hardened at the schema
level (§4).** `decision_id` is `NOT NULL`: an outcome never exists as
an arbitrary, unrelated record — it is always the record of what
happened after one specific `IntelligenceDecision`. Referenced via a
*composite* foreign key,
`(decision_id, organization_id) -> intelligence_decisions(id,
organization_id)` (mirrors `project_sites`'/`project_site_history`'s
own SIE Milestone 35A/36 composite-FK hardening technique exactly, safe
here because `ON DELETE CASCADE` applies — no `SET NULL` conflict; see
`app/models/project_site_history.py`'s own docstring for why that
technique is *not* used below for `linked_action_id`/`site_id`) — so
PostgreSQL itself rejects an `IntelligenceOutcome` row whose
`organization_id` does not match its referenced decision's own, not
merely a service-layer check. `intelligence_decisions` gained a new
`UNIQUE(id, organization_id)` constraint in this same migration to
support it (identical precedent to `sites`/`projects`' own SIE
Milestone 35A constraint).

**Action relationship — optional, deliberately not schema-hardened
(§5).** `linked_action_id` may be `NULL`: a human may decide to act
operationally outside the `SafetyAction` mechanism entirely and later
report the result (`Decision -> Outcome` with no `SafetyAction` in
between is a legitimate, first-class case — this milestone never forces
every outcome through the action model). When supplied, it is a plain,
single-column foreign key to `safety_actions.id`, `ON DELETE SET NULL`
— **not** a composite one, for the identical reason
`IntelligenceDecision.linked_action_id` itself already is not composite
either: a composite FK combined with `ON DELETE SET NULL` would null
*every* column in the constraint together, including `organization_id`,
which is `NOT NULL` here. Tenant consistency for this reference is
therefore enforced by the one governed write path
(`app/services/intelligence_outcome_service.py::record_outcome()`,
via `app.services.risk_assessment_service.resolve_action_reference()`
— the exact same reused check `IntelligenceDecision`'s own
`linked_action_id` and `RiskAssessmentFinding`'s own finding-action
linking already share) rather than a schema-level guarantee — an
accepted, documented limitation matching an already-established
precedent, not a new gap this milestone introduces.

**Site — optional, independently supplied, not derived from the
decision (§2, §11).** `site_id` may differ from (or be absent when)
the referenced decision's own `site_id` is set — this milestone does
not enforce that the two match, the same "independently supplied,
service-layer tenant-validated" shape `IntelligenceDecision.site_id`
itself already has. No project attribution is added anywhere on this
table (§11's own "do not automatically add project attribution... unless
genuinely required" instruction) — if a future milestone needs
project-scoped outcomes, the honest derivation path is `decision_id ->
IntelligenceDecision.site_id` (or `linked_action_id -> SafetyAction.
source_event_id -> SafetyEvent.attributed_project_id`, when that chain
exists) evaluated explicitly at read time, never a new duplicated
`project_id` column inferred automatically from `ProjectSite`
co-location (which SIE Milestone 35A already established can never
prove genuine attribution — see that migration's own docstring).

**Evidence — a governed reference, not a new subsystem (§8).**
`summary` (required) is the human's own account of why they believe
this outcome occurred; `evidence_event_ids` (optional, bounded) is a
reference list of existing `SafetyEvent` ids (e.g. a follow-up
observation event) — mirrors `IntelligenceDecision.evidence_event_ids`'s
own exact shape ("a reference list, never a copy of the referenced
rows' content"). Each id, when supplied, is validated at write time via
`app.services.safety_action_service.validate_source_event_reference()`
(the same existing "does this `SafetyEvent` id belong to this
organization" check `SafetyAction.source_event_id` already reuses) — no
new evidence-ingestion engine, no new provenance table.

**Actor governance (§9) and tenant scoping** — identical shape to
`IntelligenceDecision`: exactly one of `recorded_by_user_id`/
`recorded_by_api_client_id` is set, derived from `RequestContext`,
never accepted as client input; `request_id` mirrors `AuditLog.
request_id`/`IntelligenceDecision.request_id` exactly.
`OrganizationScopedMixin`, `ON DELETE CASCADE` on `organization_id` — an
outcome has no meaning independent of the organization it belongs to.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.intelligence_outcome_enums import IntelligenceOutcomeClassification

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class IntelligenceOutcome(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "intelligence_outcomes"
    __table_args__ = (
        Index("ix_intelligence_outcomes_org_decision", "organization_id", "decision_id"),
        Index("ix_intelligence_outcomes_org_action", "organization_id", "linked_action_id"),
        Index("ix_intelligence_outcomes_org_site", "organization_id", "site_id"),
        Index("ix_intelligence_outcomes_org_outcome_at", "organization_id", "outcome_at"),
        # SIE Milestone 38 -- enables a genuine, DB-enforced composite
        # foreign key from IntelligenceOutcomeVerification.outcome_id,
        # mirroring intelligence_decisions' own identical SIE Milestone
        # 37 constraint. See
        # app/models/intelligence_outcome_verification.py's own
        # docstring.
        UniqueConstraint("id", "organization_id", name="uq_intelligence_outcomes_id_organization_id"),
        # SIE Milestone 37 -- see module docstring's "Decision
        # relationship" section: mirrors project_sites'/
        # project_site_history's own composite-FK hardening (safe here:
        # ON DELETE CASCADE, no SET NULL conflict).
        ForeignKeyConstraint(
            ["decision_id", "organization_id"],
            ["intelligence_decisions.id", "intelligence_decisions.organization_id"],
            ondelete="CASCADE",
            name="fk_intelligence_outcomes_decision_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` -- its reference is the composite
    # `ForeignKeyConstraint` above.
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    # SIE Milestone 37 -- deliberately a plain, single-column FK, not
    # composite; see module docstring's "Action relationship" section
    # for why (the identical SET NULL/NOT NULL conflict
    # SafetyEvent.attributed_project_id and IntelligenceDecision.
    # linked_action_id already document).
    linked_action_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("safety_actions.id", ondelete="SET NULL"), nullable=True
    )

    classification: Mapped[IntelligenceOutcomeClassification] = mapped_column(
        SAEnum(IntelligenceOutcomeClassification, name="intelligence_outcome_classification", native_enum=True),
        nullable=False,
    )
    #: Required, non-empty (enforced at the schema layer,
    #: `IntelligenceOutcomeCreate.summary`) -- "why do we believe this
    #: outcome occurred," mirrors `IntelligenceDecision.rationale`'s own
    #: "a record with no stated reason is not a complete record" rule.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    #: See module docstring's "Evidence" section. `NULL`/empty is valid
    #: -- not every outcome has directly-referenceable event evidence.
    evidence_event_ids: Mapped[list | None] = mapped_column(_JSONType, nullable=True)

    #: The real-world instant this outcome became observable/was
    #: established -- see module docstring's "outcome_at vs. created_at"
    #: section. Always caller-supplied; never defaulted to "now" the way
    #: `IntelligenceDecision.decided_at` is (a decision is made at the
    #: moment it is recorded; an outcome is very often reported well
    #: after it actually happened).
    outcome_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Actor governance (exactly one of these two is set, never both) -------------------
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    #: The originating HTTP request's id -- mirrors `AuditLog.request_id`/
    #: `IntelligenceDecision.request_id` exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # `overlaps=` silences SQLAlchemy's "will copy column
    # organization_id ... conflicts with relationship(s)" warning --
    # expected and correct here: both `organization` (via the plain
    # OrganizationScopedMixin FK) and `decision` (via the composite FK
    # above) legitimately reference this row's own `organization_id`
    # column, identical reasoning to `ProjectSite`'s own `project`/`site`
    # relationships (see that model's own docstring).
    organization: Mapped["Organization"] = relationship(overlaps="decision")  # noqa: F821
    decision: Mapped["IntelligenceDecision"] = relationship(overlaps="organization")  # noqa: F821
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    linked_action: Mapped["SafetyAction | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntelligenceOutcome id={self.id!s} organization_id={self.organization_id!s} "
            f"decision_id={self.decision_id!s} classification={self.classification!s}>"
        )


__all__ = ["IntelligenceOutcome"]
