"""Intelligence Decisions API — SIE Milestone 34.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The service
this router delegated to (`app/services/intelligence_decision_service.py`)
has been extracted to the private Commercial Core repository: recording
and querying a human decision is tightly coupled to the Attention
composition it references (`attention_reference`), which is itself now
private. Every route below is preserved (path, method, permission
requirement) but returns HTTP 501 rather than a fake or partial
implementation. See docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `IntelligenceDecision` database model and its enums are
*not* deleted from Public SIE by this milestone -- see that document's
"Deferred: database boundary" section for why (this repository and
Commercial Core still share one database in the current transition
state; removing the table definition here is a separate, larger,
DB-schema decision this milestone does not make).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.integrations.commercial_core import commercial_core_client
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence-decisions"])


def _unavailable():
    raise commercial_core_client.unavailable("Intelligence decision recording/history")


@router.post("/decisions", status_code=201)
def create_intelligence_decision(
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/decisions")
def list_intelligence_decisions(
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/decisions/{decision_id}")
def get_intelligence_decision(
    decision_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/decisions/{decision_id}/memory-context")
def get_intelligence_decision_memory_context(
    decision_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()
