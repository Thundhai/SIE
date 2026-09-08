"""HTTP response shapes for `GET /api/v1/intelligence/attention` and
`GET /api/v1/intelligence/sites/{site_id}/attention` — SIE Milestone 33:
Intelligence Attention & Delivery. Mirrors
`app/intelligence/attention.py`'s own dataclasses field-for-field, the
same internal-domain-object/API-schema split
`app/schemas/enterprise_intelligence.py`/`app/schemas/field_intelligence_context.py`
already establish.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AttentionEvidenceRead(BaseModel):
    source: str
    calculation_version: str | None
    entity_ids: list[uuid.UUID]
    event_ids: list[uuid.UUID]


class AttentionItemRead(BaseModel):
    category: str = (
        "DETERIORATING_TREND | SIGNIFICANT_ANOMALY | RECURRING_PATTERN | ELEVATED_RISK | "
        "PREDICTIVE_RISK | UNRESOLVED_FINDING | OVERDUE_ACTIONS | EVIDENCE_GAP"
    )
    priority: str = "LOW | MODERATE | HIGH | CRITICAL"
    title: str
    explanation: str
    scope: str
    site_id: uuid.UUID | None
    site_label: str | None
    as_of: datetime
    window_days: int
    evidence: AttentionEvidenceRead
    limitation: str | None


class AttentionCategoryStatusRead(BaseModel):
    category: str
    status: str = "EVALUATED | UNAVAILABLE | NOT_EVALUATED"
    reason: str | None
    item_count: int


class AttentionResultRead(BaseModel):
    scope: str
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    as_of: datetime
    window_days: int
    generated_at: datetime
    items: list[AttentionItemRead]
    category_statuses: list[AttentionCategoryStatusRead]
    calculation_versions: dict[str, str]


__all__ = [
    "AttentionEvidenceRead",
    "AttentionItemRead",
    "AttentionCategoryStatusRead",
    "AttentionResultRead",
]
