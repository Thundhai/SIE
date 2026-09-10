"""ProjectSiteHistory — SIE Milestone 36: Project/Site Temporal Scope
Integrity. An immutable, append-only audit trail of every
`ProjectSite` membership transition — mirrors
`RiskAssessmentHistory`/`SafetyActionHistory`/
`SafetyEventProjectAttributionHistory`'s own established shape almost
exactly: `LINKED`/`UNLINKED` in place of those tables' own
domain-specific `change_type`/`action` values, `created_at` as the sole
ordering/effective-time signal (no separate `effective_at`, no
sequence tiebreaker — none of those three precedents has one either).

**Why this table exists (the remaining gap after SIE Milestone 35B).**
M35B made `SafetyEvent`'s own project *attribution* point-in-time
correct. `ProjectSite` *membership* — "which sites does this project
currently operate at" — remained current-state only: `project_sites`
has no history, so a historical `as_of` query asking "was Project P
associated with Site S at instant T" could only ever answer with
*today's* `project_sites` row, which is wrong the moment that
membership has ever changed. This table is the fix, applied narrowly
to exactly that one question — see
`app/intelligence/temporal.py::is_project_site_associated_as_of()`/
`project_site_ids_as_of()` for the reconstruction query this enables,
and `docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md` §11 for the full
account.

**Distinct from `SafetyEventProjectAttributionHistory` — do not
confuse the two.** `ProjectSite`/`ProjectSiteHistory` answer "did this
project operate at this site" (a *candidate-set*/operational-scope
question); `SafetyEvent.attributed_project_id`/
`SafetyEventProjectAttributionHistory` answer "does this specific
event belong to this project" (an *attribution* question). SIE
Milestone 35A's own central fix was establishing that the first can
never answer the second — this table strengthens the first
temporally, and changes nothing about that boundary: nothing here, or
anywhere reading it, ever attributes an event to a project merely
because `ProjectSiteHistory` says the project operated at the event's
site. `attribute_event_to_project()`'s own site-consistency check
(`app/services/safety_event_project_service.py`) deliberately continues
reading *current* `project_sites` state (via `project_site_ids()`), not
this history table — see that service's own docstring for why: it is a
write-time business rule ("can this attribution be created right now"),
not a historical reconstruction, so it is unaffected by this milestone.

**`project_sites` is unchanged and remains the fast, current-state
answer** every current-operations read already uses (`project_site_ids()`,
`list_sites_for_project()`, `list_projects_for_site()`, the site-
consistency check above, the existing `/projects/{id}/sites` API
surface). This table is the one additional place point-in-time
reconstruction happens — current-state reads are never routed through
it, so their performance is unaffected by this milestone (see
`app/intelligence/temporal.py`'s own module docstring for the
CURRENT-vs-HISTORICAL split this mirrors from `SafetyEvent.
attributed_project_id` + `SafetyEventProjectAttributionHistory`).

**Tenant integrity — composite foreign keys, mirroring `project_sites`'
own SIE Milestone 35A hardening exactly** (not the single-column
exception `SafetyEventProjectAttributionHistory.project_id` uses):
`(project_id, organization_id) -> projects(id, organization_id)` and
`(site_id, organization_id) -> sites(id, organization_id)`, both
`ON DELETE CASCADE`. Unlike `SafetyEvent.attributed_project_id` (a
plain, single-column, `ON DELETE SET NULL` column that composite FKs
are architecturally incompatible with — see that model's own
docstring), nothing on this table needs `SET NULL` semantics: every
column here can safely cascade, exactly like `project_sites` itself,
so the identical composite-FK technique applies cleanly with no
exception needed. Postgres itself therefore rejects any
`project_site_history` row whose `organization_id` does not match both
the referenced project's and site's own — not merely
application-checked — proven by
`tests/test_migrations.py::test_project_site_history_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level`.

**Immutable by convention, not a database trigger** — the same
guarantee every other history table in this codebase relies on: no
route ever issues `UPDATE`/`DELETE` against this table; every row is
written once, by
`app/services/project_site_service.py::link_project_site()`/
`unlink_project_site()`, in the same transaction as the `ProjectSite`
row's own creation/deletion, and never touched again. A history row is
written only on an actual transition — linking an already-linked pair,
or unlinking an already-unlinked pair, is a true no-op (mirrors
`ProjectSite`'s own pre-existing idempotency precedent, now also
extended to "no history noise" exactly as
`SafetyEventProjectAttributionHistory` established for event
attribution).

**Same-microsecond ordering — an explicit, accepted limitation, not a
silent gap.** `created_at`'s ordering resolution is whatever the
database clock provides (microsecond, in practice); two writes to the
same `(project_id, site_id)` pair's membership landing in the same
microsecond are not resolved deterministically here. No autoincrement/
sequence tiebreaker column exists anywhere in this schema (every table
uses a UUID primary key), and neither `RiskAssessmentHistory`,
`SafetyActionHistory`, nor `SafetyEventProjectAttributionHistory`
carries one either — this table follows that same established
convention rather than inventing new machinery for a scenario this
narrow (it requires two concurrent link/unlink requests against the
identical pair, already an inherently racy scenario the write path's
own single-row semantics do not otherwise guard against).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, UUIDPrimaryKeyMixin, utcnow


class ProjectSiteHistoryAction:
    """Known `action` values — a typo-guard convenience, not an enforced
    enum, mirroring `SafetyEventProjectAttributionAction`'s own
    established reasoning exactly."""

    LINKED = "LINKED"
    UNLINKED = "UNLINKED"


class ProjectSiteHistory(UUIDPrimaryKeyMixin, OrganizationScopedMixin, Base):
    __tablename__ = "project_site_history"
    __table_args__ = (
        # The one index the point-in-time reconstruction queries in
        # app/intelligence/temporal.py actually need: "this project's
        # rows for a given site, ordered by when they took effect."
        Index("ix_project_site_history_project_site_created", "project_id", "site_id", "created_at"),
        # SIE Milestone 36 -- see module docstring's "Tenant integrity"
        # section: mirrors project_sites' own composite foreign keys,
        # not SafetyEventProjectAttributionHistory's single-column one
        # (nothing here needs SET NULL semantics).
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            ondelete="CASCADE",
            name="fk_project_site_history_project_id_organization_id",
        ),
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            ondelete="CASCADE",
            name="fk_project_site_history_site_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` on these two columns -- their
    # references are the composite `ForeignKeyConstraint`s above.
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # A plain string, not a native enum -- see ProjectSiteHistoryAction's
    # own docstring.
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    # Exactly one of these is set, mirroring ProjectSite's own
    # created_by_user_id/created_by_api_client_id convention.
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # The originating HTTP request's id -- mirrors AuditLog.request_id /
    # SafetyEventProjectAttributionHistory.request_id exactly.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # This row's own effective-time boundary -- see module docstring's
    # "same-microsecond ordering" section.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # `overlaps=` silences SQLAlchemy's "will copy column organization_id
    # ... conflicts with relationship(s)" warning -- expected and
    # correct here, identical reasoning to ProjectSite's own two
    # composite-FK relationships (see that model's own docstring): both
    # composite FKs legitimately reference this row's own
    # organization_id column.
    project: Mapped["Project"] = relationship(overlaps="site")  # noqa: F821
    site: Mapped["Site"] = relationship(overlaps="project")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProjectSiteHistory id={self.id!s} project_id={self.project_id!s} "
            f"site_id={self.site_id!s} action={self.action!r} created_at={self.created_at!s}>"
        )


__all__ = ["ProjectSiteHistory", "ProjectSiteHistoryAction"]
