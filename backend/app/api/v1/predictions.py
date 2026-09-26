"""Predictions API.

**Updated by M43-IP-03 (Public SIE Extraction / Cleanup).** The entire
`app/predictions/` package (dataset construction, training, walk-forward
backtesting, model registry, drift/calibration monitoring, governance)
has been extracted to the private Commercial Core repository -- this is
the proprietary predictive-modeling engine, unambiguously PRIVATE per
this milestone's own classification principle. Every route is preserved
(path, method, permission requirement) but returns HTTP 501. See
docs/M43_IP_03_PUBLIC_EXTRACTION.md.

The underlying `Prediction`/`PredictionOutcome`/`ModelRegistryEntry`/
`ModelApproval`/`ModelReviewFlag`/`DatasetVersion` database models are
not deleted -- same deferred database-boundary rationale documented in
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

router = APIRouter(prefix="/intelligence/predictions", tags=["predictions"])


def _unavailable():
    raise commercial_core_client.unavailable("Predictive modeling")


@router.post("", status_code=201)
def create_prediction(
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/{entity_id}")
def get_latest_prediction(
    entity_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()


@router.get("/{entity_id}/history")
def get_prediction_history(
    entity_id: uuid.UUID,
    organization_id: uuid.UUID,
    context: RequestContext = Depends(require_context_permission(Permission.PREDICTION_READ)),
    db: Session = Depends(get_db),
):
    _unavailable()
