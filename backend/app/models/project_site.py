"""ProjectSite — SIE Milestone 35: Organizational & Operational Scope
Foundation v0.1; strengthened by SIE Milestone 35A: Canonical Project
Attribution Correction. The join table letting a `Project` span
multiple `Site`s and a `Site` host multiple `Project`s (item 4) —
mirrors `RiskAssessmentFindingAction`'s own established "tenant-scoped
link table, `ON DELETE CASCADE` both ends, unique pair, provenance on
who linked it, unlink is a hard delete" shape almost exactly (see that
model's own docstring for the precedent this follows).

**Tenant integrity — now enforced at both the schema and service
layers (SIE Milestone 35A correction).** M35's own first cut relied on
the service layer alone (`app/services/project_site_service.py::
link_project_site()`, still the one write path, still resolving both
`project_id`/`site_id` scoped to the caller's authorized
`organization_id` before any row is created) and described a
cross-tenant row as "structurally impossible" — true of that one write
path, but not of the schema itself, which only had independent,
single-column foreign keys to `projects.id`/`sites.id`. A direct
database write or a future, buggy code path bypassing the service layer
could previously still create an inconsistent row.

This migration (`0023`) closes that gap with a genuine, DB-enforced
constraint: `Site`/`Project` each gained a `UNIQUE(id, organization_id)`
constraint (see their own models), and `project_id`/`site_id` here are
now referenced via *composite* foreign keys —
`(project_id, organization_id) -> projects(id, organization_id)` and
`(site_id, organization_id) -> sites(id, organization_id)` — so
Postgres itself rejects any row whose `organization_id` does not match
both the referenced project's and site's own `organization_id`. This is
no longer merely application-checked; it is schema-enforced, and
`tests/test_migrations.py::test_project_sites_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level`
proves it by attempting a direct, service-layer-bypassing insert against
real PostgreSQL and asserting it raises `IntegrityError`.

**Why the identical technique is not used for `SafetyEvent.project_id`
(SIE Milestone 35A's new column).** A composite `ON DELETE SET NULL`
foreign key nulls *every* column in the constraint when the referenced
row is deleted — including `organization_id`, which is `NOT NULL` on
every tenant-owned table. Deleting a `Project` would then attempt to
null `SafetyEvent.organization_id` too, violating that `NOT NULL`
constraint and making the `Project` undeletable instead of cleanly
clearing the event's own attribution. `project_id`/`site_id` here avoid
that conflict because both use `ON DELETE CASCADE` (the whole row is
removed, never partially nulled) — so the composite technique is safe
here but not on `SafetyEvent.project_id`, which keeps a single-column
foreign key and relies on the validated write path
(`app/services/safety_event_project_service.py::attribute_event_to_project()`)
for tenant consistency instead. See that module's own docstring.

**`ON DELETE CASCADE` on both `project_id` and `site_id`.** Unlike
`SafetyAction.site_id` (`SET NULL` — the action itself must survive its
site being removed), this row's *entire meaning* is "this project is
associated with this site" — it has no meaning independent of both
still existing, so it is removed along with either.

**Point-in-time integrity (item 7) — explicit, deliberate limitation.**
This table records only the *current* project/site relationship set; it
has no history table, no valid-from/valid-to columns, and no undo-by-
soft-delete. Unlinking a site permanently deletes the row (mirrors
`RiskAssessmentFindingAction`'s own "unlink is a hard delete" precedent
— `AuditLog` still records the unlink event itself, just not a
queryable "what was true as of instant X" reconstruction). Any code
that reads `ProjectSite` (e.g. the `operational_scope.project.site_ids`
label in `GET /api/v1/intelligence/context`) is reading *today's*
membership regardless of the `as_of` the surrounding intelligence
request itself specifies — this is documented on that response field
directly, not merely here, so a caller reading a historical
`as_of` response is never misled into believing `site_ids` reflects
that same historical instant. If a future milestone needs true
point-in-time project/site reconstruction, it requires a dedicated
history mechanism (mirroring `RiskAssessmentHistory`'s own precedent) —
deliberately not built speculatively in this one.

**Uniqueness.** `(project_id, site_id)` is unique — linking the same
site to the same project twice is a no-op (the existing row is
returned, no duplicate created), matching `RiskAssessmentFindingAction`'s
own idempotent-by-construction precedent.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectSite(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "project_sites"
    __table_args__ = (
        UniqueConstraint("project_id", "site_id", name="uq_project_sites_project_site"),
        Index("ix_project_sites_org_project", "organization_id", "project_id"),
        Index("ix_project_sites_org_site", "organization_id", "site_id"),
        # SIE Milestone 35A: composite foreign keys, not plain
        # single-column ones -- see module docstring's "Tenant
        # integrity" section for exactly what this now guarantees at
        # the schema level.
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            ondelete="CASCADE",
            name="fk_project_sites_project_id_organization_id",
        ),
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            ondelete="CASCADE",
            name="fk_project_sites_site_id_organization_id",
        ),
    )

    # No inline `ForeignKey(...)` on these two columns -- their
    # references are the composite `ForeignKeyConstraint`s above.
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # Exactly one of these is set, mirroring RiskAssessmentFindingAction's
    # own convention -- who (human or machine) created this link.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    # `overlaps=` silences SQLAlchemy's "will copy column organization_id
    # ... conflicts with relationship(s)" warning -- expected and
    # correct here: both composite FKs legitimately reference this
    # row's own `organization_id` column (that is the entire point of
    # the composite-FK tenant guarantee -- see module docstring), not
    # an accidental overlap.
    project: Mapped["Project"] = relationship(overlaps="site")  # noqa: F821
    site: Mapped["Site"] = relationship(overlaps="project")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProjectSite id={self.id!s} project_id={self.project_id!s} site_id={self.site_id!s}>"


__all__ = ["ProjectSite"]
