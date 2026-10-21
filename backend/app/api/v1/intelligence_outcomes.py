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

**Human callers only for the two write routes.** Outcome and Verification
records are human-authored only (owner decision, 2026-10-21;
`sie-contract` 0.7.0). A machine (API-client) caller is refused with 403
before anything else happens, even though it may hold
`INTELLIGENCE_DECISION_WRITE` for Decisions. Read routes are unchanged.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_context import RequestContext, require_context_permission
from app.integrations.commercial_core import commercial_core_client
from app.services.permissions import Permission

router = APIRouter(prefix="/intelligence", tags=["intelligence-outcomes"])


def _unavailable():
    raise commercial_core_client.unavailable("Intelligence outcome tracking/verification")


_authorize_write = require_context_permission(Permission.INTELLIGENCE_DECISION_WRITE)

_HUMAN_ONLY_WRITE_RESPONSES = {
    403: {
        "description": (
            "Missing `intelligence:decision_write` in the organization, or the caller is an API client: "
            "outcomes and verifications can only be recorded by a human user."
        )
    }
}


def _require_human_writer(context: RequestContext = Depends(_authorize_write)) -> RequestContext:
    """Normal permission check first (so an unauthorized caller still gets
    the usual 403 and audit entry), then refuse any machine caller: an
    Outcome or Verification must be recorded by a person."""
    if context.is_machine:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Outcomes and verifications can only be recorded by a human user, not an API client.",
        )
    return context


@router.post("/outcomes", status_code=201, responses=_HUMAN_ONLY_WRITE_RESPONSES)
def create_intelligence_outcome(
    context: RequestContext = Depends(_require_human_writer),
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


@router.post("/outcomes/{outcome_id}/verifications", status_code=201, responses=_HUMAN_ONLY_WRITE_RESPONSES)
def create_outcome_verification(
    outcome_id: uuid.UUID,
    context: RequestContext = Depends(_require_human_writer),
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
