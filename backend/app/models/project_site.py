"""ProjectSite — SIE Milestone 35: Organizational & Operational Scope
Foundation v0.1. The join table letting a `Project` span multiple
`Site`s and a `Site` host multiple `Project`s (item 4) — mirrors
`RiskAssessmentFindingAction`'s own established "tenant-scoped link
table, `ON DELETE CASCADE` both ends, unique pair, provenance on who
linked it, unlink is a hard delete" shape almost exactly (see that
model's own docstring for the precedent this follows).

**Tenant integrity (item 4's own explicit requirement) — enforced at
the service layer, the same way every other cross-reference in this
codebase is.** A plain foreign key cannot express "same organization_id
as this row"; `app/services/project_site_service.py::link_project_site()`
resolves both `project_id` and `site_id` scoped to the caller's own
authorized `organization_id` (404 if either belongs to a different
organization, or does not exist at all — never a 403, mirroring every
other tenant-scoped reference resolution in this codebase) *before*
this row is ever created, so a project belonging to Organization A can
never be linked to a site belonging to Organization B.

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

from sqlalchemy import ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectSite(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "project_sites"
    __table_args__ = (
        UniqueConstraint("project_id", "site_id", name="uq_project_sites_project_site"),
        Index("ix_project_sites_org_project", "organization_id", "project_id"),
        Index("ix_project_sites_org_site", "organization_id", "site_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )

    # Exactly one of these is set, mirroring RiskAssessmentFindingAction's
    # own convention -- who (human or machine) created this link.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship()  # noqa: F821
    site: Mapped["Site"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProjectSite id={self.id!s} project_id={self.project_id!s} site_id={self.site_id!s}>"


__all__ = ["ProjectSite"]
