"""Intelligence Outcomes API — SIE Milestone 37/38.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The services
this router delegated to (`app/services/intelligence_outcome_service.py`,
`intelligence_outcome_verification_service.py`) have been extracted to
the private Commercial Core repository -- field-outcome tracking and its
evidence-based verification are part of the private learning loop. Every
route is preserved (path, method, permission requirement) but returns
HTTP 501. See docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `IntelligenceOutcome`/`IntelligenceOutcomeVerification`
database models and their enums are not deleted -- same deferred
database-boundary rationale as `intelligence_decisions.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.integrations.commercial_core import commercial_core_client
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence-outcomes"])


def _unavailable():
    raise commercial_core_client.unavailable("Intelligence outcome tracking/verification")


@router.post("/outcomes", status_code=201)
def create_intelligence_outcome(
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/outcomes")
def list_intelligence_outcomes(
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/outcomes/{outcome_id}")
def get_intelligence_outcome(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.post("/outcomes/{outcome_id}/verifications", status_code=201)
def create_outcome_verification(
    outcome_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/outcomes/{outcome_id}/verifications")
def list_outcome_verifications(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/outcomes/{outcome_id}/verification-state")
def get_outcome_verification_state(
    outcome_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()
