"""Organizational Memory API — SIE Milestone 40.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The service
this router delegated to (`app/services/organizational_memory_service.py`)
has been extracted to the private Commercial Core repository --
organizational memory content and its governance are explicitly private
per this milestone's own classification principle (Section 6:
"organizational memory" -> PRIVATE). Every route is preserved (path,
method, permission requirement) but returns HTTP 501. See
docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `OrganizationalMemory` database model and its enums are
not deleted -- same deferred database-boundary rationale as
`intelligence_decisions.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.integrations.commercial_core import commercial_core_client
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["organizational-memory"])


def _unavailable():
    raise commercial_core_client.unavailable("Organizational memory")


@router.post("/organizational-memory", status_code=201)
def create_intelligence_organizational_memory(
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/organizational-memory")
def list_intelligence_organizational_memory(
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/organizational-memory/{memory_id}")
def get_intelligence_organizational_memory(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.post("/organizational-memory/{memory_id}/governance-decisions", status_code=201)
def create_organizational_memory_governance_decision(
    memory_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/organizational-memory/{memory_id}/governance-decisions")
def list_organizational_memory_governance_decisions(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/organizational-memory/{memory_id}/state")
def get_organizational_memory_state(
    memory_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()
