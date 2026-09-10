"""SafetyEvent — the canonical, cross-domain representation of one piece
of organizational safety data, from any connected source system.

**`attributed_project_id` (SIE Milestone 35A: Canonical Project
Attribution Correction) — governed, nullable, distinct from the
pre-existing free-text `project` column below.** SIE Milestone 35
introduced `Project`/`ProjectSite` (an organization owns projects; a
project may span multiple sites; a site may host multiple projects) but
initially assumed a project could be attributed to a record merely by
its `site_id` being associated with that project via `ProjectSite`.
That assumption breaks the moment a site hosts more than one project:
`site_id` alone can only narrow an event down to the *set* of projects
operating at that site, never to one specific project. `attributed_project_id`
is the fix — an explicit, governed reference, set only through
`app/services/safety_event_project_service.py::attribute_event_to_project()`
(never inferred from `ProjectSite`, never bulk-backfilled, never set by
ingestion), and the one field that actually answers "which project does
this event belong to" unambiguously, when that is known. `NULL` (the
default, and every pre-Milestone-35A row's permanent state unless
explicitly attributed later) means exactly what it always meant:
unattributed — a perfectly valid, still-fully-functional state, not an
error. See that service module's own docstring for the validation rule
(when the event has a `site_id`, the project must currently be
associated with that site — `ProjectSite` — or the attribution is
rejected) and `app/models/project.py`'s own docstring for why
`SafetyAction`/`RiskAssessment` do not receive an equivalent column in
this same correction.

**Why not the existing free-text `project` column below.** That field
predates Milestone 35 entirely, is never validated, and is never
silently reinterpreted as this governed reference — an operator or
source system may have typed "Alpha Expansion" into it years before
`Project` existed as an entity at all; conflating the two would treat
unvalidated free text as authoritative. The two coexist, unrelated,
permanently.

**Why one table, not one per domain.** The milestone spec lists eleven
data domains (incidents, near misses, observations, inspections, audits,
corrective actions, permits, training, workforce, equipment,
environmental conditions, operational context) and is explicit: *"Do not
create dozens of highly specialized tables unless there is a clear
need... The model must remain extensible."* Every domain's records share
the same analytical shape — what happened, when, where, how severe, in
what state, reported by which source — so `event_type`/`event_subtype`
(plain strings, not a native DB enum — see below) select the domain and
`attributes` (JSON) carries whatever domain-specific structured fields
that type needs (e.g. `{"hours": 10000, "headcount": 50}` for a
`WORKFORCE`/`EXPOSURE_HOURS` record, `{"equipment_id": "...",
"failure_type": "..."}` for `EQUIPMENT`). Adding a new subtype, or even a
new domain, never requires a migration.

**Why `event_type` is a plain `String`, not a native PostgreSQL enum
column.** `app/services/permissions.py` already documents this exact
tradeoff for `OrganizationMembership.role`: a closed native-enum column
is the wrong amount of structure for a vocabulary expected to grow.
`app.intelligence.enums.SafetyEventType` is the Python-side validated
vocabulary (used by `app/intelligence/validation.py`); the database
column itself stays a plain, indexed string — the same choice already
made for `KnowledgeChunk.extraction_method`'s siblings, and (not
incidentally) a defect class this codebase has already paid for once:
see migration 0005's enum-type-creation defect in the README's "Known
gaps" section.

**Idempotency (milestone item 11).** `UniqueConstraint(organization_id,
source_system, source_record_id)` is the identity a resend of the same
external record is deduplicated against — see
`app/intelligence/ingestion_service.py`. `source_content_hash` (sha256 of
`source_value`, the same `app.ingestion.hashing.sha256_hex` used
elsewhere in this codebase) is what lets that service tell an unchanged
resend (no-op) apart from a genuine update to the same record (apply in
place) without re-running full validation/normalization just to compare.

**Provenance (milestone item 7).** `source_system` / `source_record_id` /
`source_value` (the original payload, preserved — never destructively
overwritten by normalization) / `ingestion_time` / `event_time` /
`normalization_version` / `schema_version` / `ingestion_batch_id`
together let a later caller answer "what source record, from which
system, ingested when, under which transformation, produced this row" —
see `app/intelligence/results.py` for how a `RiskSignal`/`FeatureValue`
traces back through `source_event_ids` to this table, and from here to
the original source record.

**`ingestion_batch_id` is a plain UUID column, not a foreign key to a
separate `ingestion_batches` table.** One ingestion API call (single or
batch) mints one UUID and stamps it on every row it writes; batch-level
statistics (record count, validation failures, ...) are computed on
demand by aggregating `safety_events` grouped by that id (or by
`source_system` for the longer-lived reliability view — see
`app/intelligence/reliability.py`) rather than maintained in a second,
easily-inconsistent table. The same "don't add a table you can compute
from instead" judgment call this codebase already made for RAG request
audit metadata (reusing `AuditLog` rather than adding a table — see
`app/rag/rag_service.py`'s docstring).

**Privacy (milestone item 34).** `description` and select `attributes`
keys (`settings.INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS`) are treated as
sensitive — see `app/intelligence/privacy.py`: never included in
feature/signal/analytics output, never logged verbatim by default.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class SafetyEvent(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "safety_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_system",
            "source_record_id",
            name="uq_safety_events_org_source_record",
        ),
    )

    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # SIE Milestone 35A: the governed project-attribution column -- see
    # module docstring's own "attributed_project_id" section for the
    # full rationale and exactly how this differs from the pre-existing
    # free-text `project` column below. Single-column FK (not the
    # composite technique ProjectSite uses), deliberately -- see
    # app/models/project_site.py's own docstring for why a composite FK
    # is architecturally incompatible with this column's ON DELETE SET
    # NULL semantics.
    attributed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- What kind of thing this is (see module docstring) -------------------
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- Temporal (milestone items 15-16) -------------------------------------
    # event_time is the single field every temporal/feature calculation
    # filters on -- see app/intelligence/temporal.py. period_end is set
    # only for period-based records (an exposure-hours window, a permit's
    # validity period); NULL means "instantaneous", not "missing".
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reported_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    # --- Operational context (milestone item 5's "Operational Context" domain) ---
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Normalized classification fields (see app/intelligence/normalization.py) ---
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    potential_severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Free text -- sensitive, see module docstring and app/intelligence/privacy.py.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Domain-specific structured fields (exposure hours, equipment id,
    # certification expiry, ...) -- see module docstring.
    attributes: Mapped[dict] = mapped_column(_JSONType, nullable=False, default=dict)

    # --- Provenance (milestone item 7) ----------------------------------------
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # The original payload exactly as received -- never destructively
    # overwritten by normalization (milestone item 14).
    source_value: Mapped[dict | None] = mapped_column(_JSONType, nullable=True)
    source_content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    ingestion_batch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)

    # --- Enterprise Data Ingestion & Validation Foundation v0.1 additions -----
    # (item 2's generic contract, item 8's source-record versioning, item 9's
    # provenance chain) -- every one of these is optional and additive; every
    # pre-existing caller that never sets them behaves exactly as before.
    #
    # source_record_version: the external system's own version/revision
    # marker for this specific record (e.g. "1", "2", "2024-06-01T00:00:00Z")
    # -- opaque to SIE beyond the narrow, documented ordering comparison
    # `app/intelligence/ingestion_service.py::_version_ordering()` performs
    # (only when both the stored and incoming values parse as integers; see
    # that function's own docstring for the explicitly-documented limitation
    # of this "safest minimal foundation").
    source_record_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # correlation_id: an optional caller-supplied identifier linking this
    # record to a related record or upstream transaction (e.g. a permit and
    # the incident it's associated with) -- never interpreted or validated
    # by SIE itself, purely a pass-through provenance field.
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # source_schema_version: the *external system's own* payload-shape
    # version, as it declared it on this record -- distinct from
    # schema_version above (SIE's own canonical schema) and from
    # DataSource.schema_version (that source's current/expected version;
    # this column is what one specific record actually said).
    source_schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # ingestion_source_id: which registered DataSource this record is
    # attributed to, if any -- ON DELETE SET NULL because a canonical event
    # must never be deleted merely because the source describing where it
    # came from was later removed (milestone item 9: "do not create orphan
    # events" cuts the other way here -- the event survives, only the
    # attribution link is cleared).
    ingestion_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Data quality (milestone items 12-13) ---------------------------------
    data_quality_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_quality_issues: Mapped[list | None] = mapped_column(_JSONType, nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    attributed_project: Mapped["Project | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SafetyEvent id={self.id!s} organization_id={self.organization_id!s} "
            f"event_type={self.event_type!r} source={self.source_system!r}:{self.source_record_id!r}>"
        )
