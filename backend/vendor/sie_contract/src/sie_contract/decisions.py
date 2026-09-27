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
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.tenancy import ActorType


class DecisionReferenceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    attention_reference: str = Field(..., description="Echoes the AttentionItemDTO.reference this decision concerns.")
    decision_type: str = Field(..., description="Open vocabulary owned by Commercial Core, e.g. 'ACKNOWLEDGE', 'DISMISS', 'ESCALATE' -- current known values documented in BOUNDARY_DECISIONS.md, informational only.")
    rationale: str = Field(..., description="The deciding actor's own free-text explanation -- human-authored, not algorithmic output.")
    decided_at: datetime = Field(..., description="UTC.")
    actor_type: ActorType
    actor_id: uuid.UUID
