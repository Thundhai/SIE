"""Attention -- the canonical example this milestone was scoped around.

Mirrors the *observable shape* of Thundhai/SIE's existing
`AttentionItemRead` (app/schemas/attention.py) and the internal
`AttentionItem` dataclass (app/intelligence/attention.py, private),
deliberately re-derived rather than copied -- see
`../../docs/BOUNDARY_DECISIONS.md` Section 6 for the field-by-field
reasoning. In particular:

- `category` and `priority` are kept (an external consumer legitimately
  needs to know *what kind* of attention item this is and *how urgent*)
  as an open-vocabulary `str` and a closed `AttentionPriority` enum
  respectively.
- `title`/`explanation`/`limitation` are kept -- these are already the
  user-facing, natural-language observable output, not an internal
  mechanism.
- `evidence` is re-typed from the internal `AttentionEvidence` dataclass
  (which carries `calculation_version` and raw `entity_ids`/`event_ids`)
  to a list of `EvidenceReference` -- calculation_version is an internal
  implementation-versioning detail, and raw internal ids are replaced by
  typed, resolvable references.
- `reference` is kept as-is: it was *already* designed (SIE Milestone 34)
  as "the smallest deterministic reference necessary" for a caller to
  echo back later -- it is already a contract-shaped field, not an
  internal detail.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.common import AsOfWindow, EvidenceReference


class AttentionPriority(str, Enum):
    """Closed set -- unlike `category`, this vocabulary is small,
    stable, and a consumer's rendering (e.g. color-coding) legitimately
    depends on it being exhaustive."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AttentionCategoryStatus(str, Enum):
    EVALUATED = "EVALUATED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class AttentionScope(str, Enum):
    ORGANIZATION = "organization"
    SITE = "site"


class AttentionItemDTO(BaseModel):
    """One observable attention item. See module docstring for exactly
    which internal fields were deliberately left out."""

    model_config = ConfigDict(frozen=True)

    reference: str = Field(..., description="Stable, deterministic, opaque reference this item can be echoed back by (e.g. to record a DecisionReferenceDTO against it). Never a random id.")
    category: str = Field(..., description="Open vocabulary -- see README 'Open vs. closed vocabularies'. Current known values documented in BOUNDARY_DECISIONS.md, informational only.")
    priority: AttentionPriority
    title: str
    explanation: str
    scope: AttentionScope
    site_id: uuid.UUID | None = None
    as_of: AsOfWindow
    evidence: list[EvidenceReference] = Field(default_factory=list)
    limitation: str | None = Field(default=None, description="A user-facing caveat, e.g. 'insufficient data for the full window' -- not an internal error code.")


class AttentionCategoryStatusDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    status: AttentionCategoryStatus
    reason: str | None = None
    item_count: int = Field(..., ge=0)


class AttentionResultDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    scope: AttentionScope
    entity_id: uuid.UUID | None = Field(default=None, description="The site_id when scope=SITE; None when scope=ORGANIZATION.")
    as_of: AsOfWindow
    items: list[AttentionItemDTO] = Field(default_factory=list)
    category_status: list[AttentionCategoryStatusDTO] = Field(default_factory=list)
