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

**`operational_scope` (SIE Milestone 35: Organizational & Operational
Scope Foundation v0.1) — a label, never a second computation.** Set only
when the caller supplies `project_id` on `GET .../context` or
`GET .../sites/{site_id}/context` (`app/api/v1/intelligence.py`); `None`
otherwise, so every pre-M35 caller's response is byte-for-byte
unchanged. `level` always states exactly what `deterministic`/
`observed`/`predictive` were actually computed over — `"ORGANIZATION"`
or `"SITE"`, the same `scope` this endpoint already accepts — never
`"PROJECT"`: this milestone does not implement multi-site project-level
intelligence aggregation (see `docs/OPERATIONAL_SCOPE_FOUNDATION_V0_1.md`'s
"Limitations" section), so `operational_scope.project` is always a
*label* identifying which project this call also concerns, never a
claim that the numbers above were filtered to that project's sites.
`project.site_ids` is the project's *current* `ProjectSite` membership
at the moment of this API call — not reconstructed as of `as_of` (see
`app/models/project_site.py`'s own "point-in-time integrity" section);
a historical `as_of` request's `project.site_ids` reflects today's
relationships, never that historical instant's.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

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


class OperationalScopeSiteRead(BaseModel):
    id: uuid.UUID
    name: str


class OperationalScopeProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    status: str
    site_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="The project's CURRENT associated site ids -- not reconstructed as of `as_of`. "
        "See this module's own docstring.",
    )


class OperationalScopeRead(BaseModel):
    level: str = "ORGANIZATION | SITE -- what deterministic/observed/predictive were actually computed over"
    site: OperationalScopeSiteRead | None = None
    project: OperationalScopeProjectRead | None = None


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
    operational_scope: OperationalScopeRead | None = None


__all__ = [
    "ObservedFindingRead",
    "ObservedActionRead",
    "ObservedFactRead",
    "PredictiveSignalRead",
    "KnowledgeEvidenceRead",
    "OperationalScopeSiteRead",
    "OperationalScopeProjectRead",
    "OperationalScopeRead",
    "FieldIntelligenceContextRead",
]
