"""Project — SIE Milestone 35: Organizational & Operational Scope
Foundation v0.1.

    Organization
       |
       +-- Sites (existing, unchanged -- app/models/site.py)
       |
       +-- Projects (new, this milestone)
              |
              +-- ProjectSite (new -- many-to-many with Site;
                                see that model's own docstring)

**Identity and relationships only (item 1's own instruction).** SIE is
an intelligence layer, not a project-management system: this model
carries a stable identity (`id`), ownership (`organization_id`), a
name, an optional human-facing `code`/reference, a closed lifecycle
`status`, and an optional free-text `description` — nothing else.
Deliberately absent, per the milestone's own explicit list: budgets,
schedules/milestones, task management, resources, procurement, and
financial information. None of those are justified by any existing or
planned SIE *intelligence* need; if a future milestone genuinely needs
one, it gets added then, with its own justification — not speculatively
here.

**Why `Site` is reused, not a new location hierarchy (item 2).**
`Site` (`app/models/site.py`) already is the physical/operational
location entity this codebase's entire event/action/risk-assessment
domain scopes against (`SafetyEvent.site_id`, `SafetyAction.site_id`,
`RiskAssessment.site_id`, ...). Nothing in this milestone's own
requirements demonstrates `Site` cannot serve that role for `Project`
too, so no second, competing `Location` entity is introduced — see
`docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md` for the full scope-semantics
writeup this milestone produces.

**Why a many-to-many `Project` <-> `Site` relationship, not a single
`site_id` column (item 4).** A project may span multiple sites (a
regional maintenance program touching several facilities) and a site
may host multiple concurrent projects — a one-to-many `site_id` column
on `Project` cannot represent either. See `ProjectSite`'s own docstring
for the join table this uses instead, and its tenant-integrity
enforcement (a project can never be linked to a site belonging to a
different organization).

**Why no `project_id` was added to `SafetyEvent`/`SafetyAction`/
`RiskAssessment`/`RiskAssessmentFinding`/`IntelligenceDecision` (item 6's
own explicit guardrail).** Every one of those already carries (or, for
`IntelligenceDecision`, resolves through `AttentionItem`) a `site_id`.
Project membership of a site is fully recoverable at query time by
joining through `ProjectSite` — indiscriminately duplicating a
`project_id` foreign key onto five more tables would (a) not be
justified by any concrete, existing intelligence computation that
needs it directly, (b) create a second, easily-inconsistent place a
project/site relationship could be represented, and (c) collide with
point-in-time integrity (item 7): a row's `project_id`, once written,
would either need its own temporal snapshot to stay historically
correct as project/site membership changes, or would silently
misrepresent history — a cost this milestone's own minimum-coupling
instruction does not justify paying today. See
`app/intelligence/context_composition.py` and `app/api/v1/intelligence.py`
(the one place `Project` *is* surfaced to intelligence output, purely as
an additive, current-state `operational_scope` label — never a new
computation engine) for the one place this milestone does connect
Project to intelligence, and why it stops there.

**Point-in-time integrity (item 7).** `ProjectSite` rows carry no
temporal versioning in this milestone — see that model's own docstring.
A `Project`'s own `status`/`name`/`code` are mutable-by-replacement in
the same "no history table" sense: this milestone adds no
`ProjectHistory` table (nothing yet reads a project's own field values
as of a past instant the way `RiskAssessment.as_of` does), so none is
built speculatively.

**Tenant scoping.** `OrganizationScopedMixin` exactly like every other
tenant-owned table — no second tenant model, no GLOBAL project.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrganizationScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.project_enums import ProjectStatus


class Project(UUIDPrimaryKeyMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_org_status", "organization_id", "status"),
        Index("ix_projects_org_code", "organization_id", "code"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Optional human-facing reference/code (e.g. "PRJ-2026-014") -- like
    # RiskAssessment.reference, never enforced unique: two organizations'
    # own external systems may both mint "PRJ-001", and even within one
    # organization uniqueness is not a property this milestone's own
    # intelligence needs require.
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status", native_enum=True),
        nullable=False,
        default=ProjectStatus.ACTIVE,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship()  # noqa: F821
    # Read-only convenience accessor over the ProjectSite join table --
    # never written through (see ProjectSite's own docstring for the one
    # write path, app/services/project_site_service.py).
    sites: Mapped[list["Site"]] = relationship(  # noqa: F821
        secondary="project_sites", viewonly=True, order_by="Site.name"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Project id={self.id!s} organization_id={self.organization_id!s} "
            f"name={self.name!r} status={self.status!s}>"
        )


__all__ = ["Project"]
