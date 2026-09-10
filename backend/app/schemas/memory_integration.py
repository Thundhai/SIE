"""HTTP response shapes for
`GET /api/v1/intelligence/memory-context`,
`GET /api/v1/intelligence/sites/{site_id}/memory-context`, and
`GET /api/v1/intelligence/decisions/{decision_id}/memory-context` —
SIE Milestone 41: Learning Integration & Intelligence Adaptation
Architecture. Mirrors `app/intelligence/memory_integration.py`'s own
dataclass shapes exactly -- pure read-time composition, no request body
(these are GET-only, no client-fabricatable input beyond the same
organization_id/as_of/project_id query parameters every other
intelligence read route already accepts).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.organizational_memory_enums import OrganizationalMemoryType


class IntegratedMemoryRead(BaseModel):
    memory_id: uuid.UUID
    memory_type: OrganizationalMemoryType
    title: str
    memory_content: str
    rationale: str
    memory_created_at: datetime
    learning_candidate_id: uuid.UUID
    outcome_id: uuid.UUID
    verification_id: uuid.UUID
    outcome_site_id: uuid.UUID | None
    applicability_basis: str
    governance_status: str
    governance_is_explicit: bool
    governance_decided_at: datetime | None


class MemoryIntegrationContextRead(BaseModel):
    scope: str
    organization_id: uuid.UUID
    entity_id: uuid.UUID | None
    project_id: uuid.UUID | None
    as_of: datetime
    generated_at: datetime
    items: list[IntegratedMemoryRead]
    total: int
    page: int
    page_size: int
    calculation_version: str


class DecisionMemoryIntegrationContextRead(MemoryIntegrationContextRead):
    """The decision-traceability shape (SIE Milestone 41 spec §10/§20):
    identical to `MemoryIntegrationContextRead`, plus the exact decision
    fields the reconstruction was derived from -- so a caller never has
    to separately fetch `GET /intelligence/decisions/{id}` just to learn
    what `scope`/`site_id`/`as_of` this reconstruction used."""

    decision_id: uuid.UUID
    decision_scope: str
    decision_site_id: uuid.UUID | None
    decision_intelligence_as_of: datetime


__all__ = ["IntegratedMemoryRead", "MemoryIntegrationContextRead", "DecisionMemoryIntegrationContextRead"]
