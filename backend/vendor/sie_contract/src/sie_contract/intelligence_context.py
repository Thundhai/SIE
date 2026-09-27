"""Intelligence Context -- coarse observability only.

Thundhai/SIE's internal `FieldIntelligenceContextRead` (private,
app/schemas/field_intelligence_context.py) is deep: it carries finding
samples, action samples, and a `PredictiveSignalRead.value` (a full
`PredictiveContextRead`, i.e. model output). None of that is in this
module. See `../../docs/BOUNDARY_DECISIONS.md` Section 6 for why: a
sample list is close enough to "the internal query result" that
redacting it correctly requires a deliberate design pass this milestone
does not attempt, and `PredictiveSignalRead.value` is predictive-model
output, which is out of the contract entirely (see that document's
Predictions section).

What *is* here: whether context was computed at all for each category,
and why not, when not. That is a legitimate, already-observable
integration need (a consumer deciding whether to show a category's UI
section at all) that carries none of the underlying computation.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.common import AsOfWindow


class IntelligenceContextCategoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class IntelligenceContextCategoryStatusDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str = Field(..., description="Open vocabulary, e.g. 'observed_facts', 'predictive_signal', 'organizational_memory'.")
    status: IntelligenceContextCategoryStatus
    reason: str | None = None


class IntelligenceContextSummaryDTO(BaseModel):
    """Whether intelligence context is available, per category, for one
    organization/scope/as_of -- deliberately withholds the content
    itself. See module docstring."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    scope: str = Field(..., description="'organization' | 'site' | 'project' -- matches Thundhai/SIE's existing scope vocabulary.")
    entity_id: uuid.UUID | None = None
    as_of: AsOfWindow
    categories: list[IntelligenceContextCategoryStatusDTO] = Field(default_factory=list)
