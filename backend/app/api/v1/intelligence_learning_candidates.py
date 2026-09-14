"""Intelligence Learning Candidates API — SIE Milestone 39.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The service
this router delegated to (`app/services/intelligence_learning_candidate_service.py`,
plus its `intelligence_outcome_verification_service` dependency) has
been extracted to the private Commercial Core repository. Learning
candidates and their governance decisions are part of the private
learning loop this milestone's governance explicitly forbids expanding
or reimplementing here. Every route is preserved (path, method,
permission requirement) but returns HTTP 501. See
docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `IntelligenceLearningCandidate` database model and its
enums are not deleted -- same deferred database-boundary rationale as
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

router = APIRouter(prefix="/intelligence", tags=["intelligence-learning-candidates"])


def _unavailable():
    raise commercial_core_client.unavailable("Intelligence learning candidates")


@router.post("/learning-candidates", status_code=201)
def create_intelligence_learning_candidate(
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/learning-candidates")
def list_intelligence_learning_candidates(
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/learning-candidates/{candidate_id}")
def get_intelligence_learning_candidate(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.post("/learning-candidates/{candidate_id}/governance-decisions", status_code=201)
def create_learning_candidate_governance_decision(
    candidate_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/learning-candidates/{candidate_id}/governance-decisions")
def list_learning_candidate_governance_decisions(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/learning-candidates/{candidate_id}/state")
def get_learning_candidate_state(
    candidate_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.INTELLIGENCE_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()
