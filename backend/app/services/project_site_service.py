"""Project/Site relationship service — SIE Milestone 35: Organizational
& Operational Scope Foundation v0.1. The one write path for `ProjectSite`
rows — mirrors `app/services/risk_assessment_service.py`'s own
finding/action link-management shape (`resolve_action_reference()` +-
create-if-absent) applied to Project/Site instead of Finding/Action.

**Tenant integrity (item 4/item 8's own explicit requirement).**
`link_project_site()` resolves *both* `project_id` and `site_id` scoped
to the caller's own authorized `organization_id` before creating
anything — a project or site belonging to a different organization is
indistinguishable from a nonexistent one (404, never 403), so a link
between tenants can never be created no matter what the caller supplies.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project_site import ProjectSite
from app.models.site import Site
from app.services.project_service import resolve_project_reference


def _resolve_owned_site(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    site = db.execute(select(Site).where(Site.id == site_id, Site.organization_id == organization_id)).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site_id not found in this organization.")
    return site


def link_project_site(
    db: Session,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    created_by_api_client_id: uuid.UUID | None,
) -> tuple[ProjectSite, bool]:
    """Create (or return the existing) `ProjectSite` link.

    Both `project_id` and `site_id` are resolved against `organization_id`
    first — a project or site belonging to a different organization
    raises 404 before any row is touched, so tenant isolation is
    structural, not merely checked after the fact. Returns
    `(row, created)` — `created=False` when the pair was already linked
    (idempotent by construction, mirrors
    `RiskAssessmentFindingAction`'s own precedent — see that model's own
    docstring)."""
    resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    _resolve_owned_site(db, organization_id=organization_id, site_id=site_id)

    existing = db.execute(
        select(ProjectSite).where(
            ProjectSite.organization_id == organization_id,
            ProjectSite.project_id == project_id,
            ProjectSite.site_id == site_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    row = ProjectSite(
        organization_id=organization_id,
        project_id=project_id,
        site_id=site_id,
        created_by_user_id=created_by_user_id,
        created_by_api_client_id=created_by_api_client_id,
    )
    db.add(row)
    db.flush()
    return row, True


def unlink_project_site(db: Session, *, organization_id: uuid.UUID, project_id: uuid.UUID, site_id: uuid.UUID) -> bool:
    """Hard-deletes the link if it exists. Returns whether a row was
    actually removed (the API layer 404s when it wasn't — mirrors every
    other "unlink" route in this codebase)."""
    resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    row = db.execute(
        select(ProjectSite).where(
            ProjectSite.organization_id == organization_id,
            ProjectSite.project_id == project_id,
            ProjectSite.site_id == site_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def list_sites_for_project(db: Session, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> list[Site]:
    resolve_project_reference(db, organization_id=organization_id, project_id=project_id)
    rows = db.execute(
        select(Site)
        .join(ProjectSite, ProjectSite.site_id == Site.id)
        .where(ProjectSite.organization_id == organization_id, ProjectSite.project_id == project_id)
        .order_by(Site.name)
    ).scalars().all()
    return list(rows)


def list_projects_for_site(db: Session, *, organization_id: uuid.UUID, site_id: uuid.UUID):
    from app.models.project import Project  # local import: avoids a project<->project_site import cycle at module load

    _resolve_owned_site(db, organization_id=organization_id, site_id=site_id)
    rows = db.execute(
        select(Project)
        .join(ProjectSite, ProjectSite.project_id == Project.id)
        .where(ProjectSite.organization_id == organization_id, ProjectSite.site_id == site_id)
        .order_by(Project.name)
    ).scalars().all()
    return list(rows)


def project_site_ids(db: Session, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> list[uuid.UUID]:
    """The current (not point-in-time) set of site ids a project is
    associated with — see `ProjectSite`'s own docstring for why this is
    always "as of now", regardless of any `as_of` the caller is
    otherwise reasoning about."""
    rows = db.execute(
        select(ProjectSite.site_id).where(
            ProjectSite.organization_id == organization_id, ProjectSite.project_id == project_id
        )
    ).scalars().all()
    return list(rows)


__all__ = [
    "link_project_site",
    "unlink_project_site",
    "list_sites_for_project",
    "list_projects_for_site",
    "project_site_ids",
]
