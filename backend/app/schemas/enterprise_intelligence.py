"""HTTP response shapes for the enterprise intelligence API
(`app/api/v1/intelligence.py`'s `GET .../intelligence/enterprise` and
`GET .../intelligence/sites/{site_id}`) — SIE Milestone 22: Enterprise
Intelligence & Risk Analytics Foundation v0.1, item 14. Mirrors
`app/intelligence/enterprise_intelligence_service.py`'s own dataclasses
field-for-field (the same internal-domain-object/API-schema split
`app/schemas/intelligence.py` already establishes for the rest of this
package).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class EnterpriseIndicatorRead(BaseModel):
    key: str
    label: str
    value: int
    category: str
    period_start: datetime
    period_end: datetime
    window_days: int
    previous_value: int
    absolute_change: int
    percentage_change: float | None
    trend_direction: str | None
    unavailable_reason: str | None
    calculation_version: str


class EnterpriseTrendRead(BaseModel):
    classification: str
    metric: str
    current_value: int
    previous_value: int
    absolute_change: int
    percentage_change: float | None
    current_period_start: datetime
    current_period_end: datetime
    previous_period_start: datetime
    previous_period_end: datetime
    calculation_version: str


class RecurrencePatternRead(BaseModel):
    pattern_key: str
    scope: str
    site_id: uuid.UUID
    site_label: str
    event_type: str
    event_subtype: str | None
    count: int
    first_seen: datetime
    last_seen: datetime
    window_start: datetime
    window_end: datetime
    window_days: int
    supporting_event_ids: list[uuid.UUID]
    classification: str
    calculation_version: str


class ConcentrationContributorRead(BaseModel):
    dimension: str
    key: str
    label: str
    count: int
    total: int
    percentage: float
    classification: str
    calculation_version: str


class RiskScoreComponentRead(BaseModel):
    key: str
    label: str
    raw_score: float
    weight: float
    normalized_weight: float
    contribution: float


class RiskScoreRead(BaseModel):
    score: float | None
    classification: str | None
    version: str
    components: list[RiskScoreComponentRead]
    insufficient_data_reason: str | None


class ExplanationItemRead(BaseModel):
    code: str
    message: str
    value: float | int | None
    baseline: float | int | None
    contribution: float | None
    evidence_reference: str


class DataSufficiencyRead(BaseModel):
    status: str
    event_count: int


class ProvenanceRead(BaseModel):
    organization_id: uuid.UUID
    scope: str
    entity_id: uuid.UUID | None
    as_of: datetime
    window_start: datetime
    window_end: datetime
    window_days: int
    generated_at: datetime
    event_count: int
    evidence_sample_event_ids: list[uuid.UUID]
    total_supporting_events: int
    calculation_versions: dict[str, str]


class PredictiveContextRead(BaseModel):
    prediction_id: uuid.UUID
    prediction_time: datetime
    outcome: str
    risk_score: float | None
    probability: float | None
    risk_category: str | None
    model_version: str | None


class ActionsContextRead(BaseModel):
    open_action_count: int
    overdue_action_count: int
    high_priority_action_count: int


class EnterpriseIntelligenceRead(BaseModel):
    scope: str
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    data_sufficiency: DataSufficiencyRead
    deterministic_risk: RiskScoreRead
    trend: EnterpriseTrendRead
    indicators: list[EnterpriseIndicatorRead]
    patterns: list[RecurrencePatternRead]
    concentrations: list[ConcentrationContributorRead]
    explanations: list[ExplanationItemRead]
    provenance: ProvenanceRead
    predictive_context: PredictiveContextRead | None = None
    actions_context: ActionsContextRead | None = None
