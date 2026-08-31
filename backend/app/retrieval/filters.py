"""RetrievalFilters — the metadata-filtering half of a retrieval request.

Deliberately a plain dataclass, not tied to the HTTP schema
(`app/schemas/retrieval.py`) or to any one caller — `RetrievalService`
and the evaluation harness (`tests/evaluation/`) both build one of these
directly. `organization_id` is **not** a field here: which
organization's knowledge a search may see is an authorization decision
made by the caller before `RetrievalService.search()` is ever invoked
(see that method's `allowed_organization_id` parameter), never a filter
value taken at face value from a request body — see the README's tenant
isolation section for why that distinction matters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from app.models.enums import ContentType, VerificationStatus


@dataclass(frozen=True)
class RetrievalFilters:
    """All fields optional — an unset field applies no filter. The
    milestone's full target filter set (organization/global scope is
    handled separately, see module docstring):
    """

    source_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    content_type: ContentType | None = None
    industry_sector: str | None = None
    jurisdiction: str | None = None
    verification_status: VerificationStatus | None = None
    effective_date_from: date | None = None
    effective_date_to: date | None = None

    def as_dict(self) -> dict:
        """Only the filters actually set — used for
        `RetrievalResponse.filters_applied`, so a client can see exactly
        what was applied without a wall of nulls."""
        return {
            key: (value.value if hasattr(value, "value") else str(value))
            for key, value in vars(self).items()
            if value is not None
        }
