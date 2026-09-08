"""Project service — SIE Milestone 35: Organizational & Operational
Scope Foundation v0.1. Create/get/list reuse `TenantScopedRepository`
exactly like `SiteService` (`app/services/site_service.py`) — Project is
an operational-scope entity of the same shape as Site, so its basic CRUD
follows the identical, already-established pattern.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.project import ProjectCreate
from app.services.base import TenantScopedRepository


class ProjectService(TenantScopedRepository[Project, ProjectCreate]):
    def __init__(self) -> None:
        super().__init__(Project)


project_service = ProjectService()


def resolve_project_reference(db: Session, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Like `risk_assessment_service.resolve_action_reference()` — a
    project id belonging to a different organization (or a nonexistent
    one) is a 404, never a 403, mirroring every other tenant-scoped
    reference resolution in this codebase."""
    project = db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == organization_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found in this organization.")
    return project


__all__ = ["ProjectService", "project_service", "resolve_project_reference"]
