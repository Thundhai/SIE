"""HTTP request/response shapes for the predictions API
(`app/api/v1/predictions.py`). Distinct from the internal domain
dataclasses in `app/predictions/*.py` — the same
internal-domain-object/API-schema split used throughout this codebase
(see `app/schemas/intelligence.py`'s own docstring).

**Input security (milestone item 45).** `PredictionRequest` carries only
`organization_id` (trusted from the authenticated context, not really
"input" — see `app/api/v1/predictions.py`) and `entity_id` — a client
can never supply a feature value, a risk score, or a label. There is no
field for any of those on this model; adding one would be the security
regression this docstring is here to prevent.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.predictions.spec import SAFETY_LANGUAGE_NOTE


class PredictionRequest(BaseModel):
    entity_id: uuid.UUID
    # Optional -- defaults to "now" server-side. Accepting this at all
    # (rather than only ever using utcnow()) is what makes predict_as_of's
    # backtesting use documented as the same code path a live request
    # takes; it is never a chance for a client to inject a feature value,
    # a label, or a risk score -- only a timestamp.
    as_of: datetime | None = None


class FeatureContributionRead(BaseModel):
    feature_name: str
    contribution: float
    direction: str
    raw_value: float | None
    is_missing: bool
    association_note: str


class ExplanationRead(BaseModel):
    top_positive: list[FeatureContributionRead]
    top_negative: list[FeatureContributionRead]
    method: str
    disclaimer: str


class PredictionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    prediction_time: datetime
    horizon_days: int
    outcome: str
    abstention_reason: str | None
    risk_score: float | None
    probability: float | None
    risk_category: str | None
    model_id: uuid.UUID | None
    model_version: str | None
    feature_snapshot_id: uuid.UUID | None
    data_quality: str
    explanation: ExplanationRead | None
    created_at: datetime
    # Milestone's own required safety language (item 29/49) -- present on
    # every response, not just ones a UI author remembered to add it to.
    safety_language_note: str = SAFETY_LANGUAGE_NOTE
