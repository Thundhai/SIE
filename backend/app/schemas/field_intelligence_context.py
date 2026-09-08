"""HTTP response shapes for `GET /api/v1/intelligence/context` — SIE
Milestone 32: Field Intelligence Context Composition v0.1. Mirrors
`app/intelligence/context_composition.py`'s own dataclasses field-for-
field, the same internal-domain-object/API-schema split
`app/schemas/enterprise_intelligence.py` already establishes for
`compute_enterprise_intelligence()`.

Four top-level sections — `observed`, `deterministic`, `predictive`,
`knowledge` — never merged into one flattened shape (see
`context_composition.py`'s own docstring, restating
`SIE_FIELD_INTELLIGENCE_CONTEXT_V0_1.md` §7's "never merged into one
undifferentiated feed" rule). `deterministic` reuses
`EnterpriseIntelligenceRead` verbatim (via composition, not
inheritance) rather than redefining indicators/trend/anomaly/etc. a
second time.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.enterprise_intelligence import (
    ActionsContextRead,
    EnterpriseIntelligenceRead,
    PredictiveContextRead,
)
from app.schemas.retrieval import RetrievalResultRead


class ObservedFindingRead(BaseModel):
    finding_id: uuid.UUID
    title: str
    status: str
    risk_area_label: str
    inherent_risk_classification: str | None
    residual_risk_classification: str | None
    assessment_id: uuid.UUID
    site_id: uuid.UUID | None
    created_at: datetime


class ObservedActionRead(BaseModel):
    action_id: uuid.UUID
    title: str
    status: str
    priority: str
    due_date: datetime | None
    site_id: uuid.UUID | None


class ObservedFactRead(BaseModel):
    outcome: str = "OK | UNAVAILABLE"
    unavailable_reason: str | None
    event_count: int
    evidence_sample_event_ids: list[uuid.UUID]
    open_finding_count: int
    open_finding_sample: list[ObservedFindingRead]
    open_finding_control_count: int
    actions: ActionsContextRead | None
    open_action_sample: list[ObservedActionRead]


class PredictiveSignalRead(BaseModel):
    outcome: str = "AVAILABLE | NOT_AVAILABLE | EXCLUDED_GENERATED_AFTER_AS_OF"
    value: PredictiveContextRead | None


class KnowledgeEvidenceRead(BaseModel):
    outcome: str = "RESULTS | NO_RELEVANT_EVIDENCE | NOT_QUERIED | UNAVAILABLE"
    unavailable_reason: str | None
    query: str | None
    results: list[RetrievalResultRead]
    result_count: int


class FieldIntelligenceContextRead(BaseModel):
    scope: str
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    generated_at: datetime
    observed: ObservedFactRead
    deterministic: EnterpriseIntelligenceRead
    predictive: PredictiveSignalRead
    knowledge: KnowledgeEvidenceRead
    calculation_versions: dict[str, str]


__all__ = [
    "ObservedFindingRead",
    "ObservedActionRead",
    "ObservedFactRead",
    "PredictiveSignalRead",
    "KnowledgeEvidenceRead",
    "FieldIntelligenceContextRead",
]
