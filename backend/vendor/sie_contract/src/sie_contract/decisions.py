"""Decision references -- factual governance records, not reasoning.

A decision is a human's (or, per Thundhai/SIE's existing architecture,
occasionally a machine caller's) own recorded response to an
AttentionItemDTO -- "what was decided, when, by whom" is an audit fact,
not "how Commercial Core thinks". `rationale` is the *human's own*
free-text explanation of their decision, not an algorithmic output, so
it is included here deliberately (unlike, say, a predictive model's
confidence score).

This module intentionally does not attempt outcome/verification/
learning-candidate/organizational-memory DTOs -- those are the private
learning loop's own governance records (see
`../../docs/BOUNDARY_DECISIONS.md` Section 6) and remain
`REVIEW_REQUIRED` pending a deliberate future pass, not merely
duplicated here because the internal schema already exists.

**0.5.0: added `scope`/`site_id`/`attention_category`/
`attention_priority`/`attention_title`.** None of these are a new
exposure -- every one is already public today via `AttentionItemDTO`
(see `attention.py`), which this decision's own `attention_reference`
already points back to. Carrying a snapshot of them here spares a
consumer a second, correlating Attention fetch merely to show "what
signal was this decision about" next to the decision itself. What
stays deliberately absent is unchanged: `calculation_version`,
evidence detail, and any linked-action/site-label join remain out of
this contract -- see `../../docs/BOUNDARY_DECISIONS.md` Section 13 for
this decision recorded in full.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.attention import AttentionPriority, AttentionScope
from sie_contract.tenancy import ActorType


class DecisionReferenceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    attention_reference: str = Field(..., description="Echoes the AttentionItemDTO.reference this decision concerns.")
    scope: AttentionScope = Field(..., description="Echoes the AttentionItemDTO.scope this decision concerns.")
    site_id: uuid.UUID | None = Field(default=None, description="Echoes the AttentionItemDTO.site_id this decision concerns -- None when scope is organization-wide.")
    attention_category: str = Field(..., description="Echoes the AttentionItemDTO.category this decision concerns -- open vocabulary, same as that field.")
    attention_priority: AttentionPriority = Field(..., description="Echoes the AttentionItemDTO.priority this decision concerns.")
    attention_title: str = Field(..., description="Echoes the AttentionItemDTO.title this decision concerns.")
    decision_type: str = Field(..., description="Open vocabulary owned by Commercial Core, e.g. 'ACKNOWLEDGE', 'DISMISS', 'ESCALATE' -- current known values documented in BOUNDARY_DECISIONS.md, informational only.")
    rationale: str = Field(..., description="The deciding actor's own free-text explanation -- human-authored, not algorithmic output.")
    decided_at: datetime = Field(..., description="UTC.")
    actor_type: ActorType
    actor_id: uuid.UUID


class DecisionListResultDTO(BaseModel):
    """A page of `DecisionReferenceDTO` -- the same "envelope, never a
    bare list" shape `AttentionResultDTO`/`AnalyticsSignalsResultDTO`
    already establish for a collection result, applied here so a
    consumer can page through a signal's (or an organization's)
    decision history. Mirrors `common.Page[T]`'s own field names
    (`items`/`total`/`page`/`page_size`) exactly, specialized rather
    than parametrized so `DecisionReferenceDTO`'s own `frozen=True`
    construction stays simple for callers to build."""

    model_config = ConfigDict(frozen=True)

    items: list[DecisionReferenceDTO] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
