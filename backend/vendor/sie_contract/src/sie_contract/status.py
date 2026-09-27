"""A generic health/availability descriptor -- not present in
Thundhai/SIE's existing schemas today (there is no internal analog to
redact from); designed fresh for this contract to answer one question an
external integration legitimately needs and none of the existing
internal schemas answer directly: "is intelligence currently available
for this organization at all, and which categories?" -- without
revealing why in mechanistic terms.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IntelligenceOverallStatus(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class IntelligenceStatusDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    overall_status: IntelligenceOverallStatus
    categories_available: list[str] = Field(default_factory=list, description="Open vocabulary of category names currently producing output for this organization.")
    computed_at: datetime = Field(..., description="UTC.")
