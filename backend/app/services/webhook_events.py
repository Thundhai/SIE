"""Outbound event abstraction — Intelligence Platform Integration &
Enterprise API v0.1, item 31.

**Interface only. No delivery mechanism exists in this milestone** — no
HTTP callouts, no retry queue, no signature verification, no Kafka/event
bus. This module documents the *shape* future outbound events will take
and the one seam (`WebhookDispatcher`) a real delivery implementation
would plug into, mirroring how `app/ingestion/ocr.py` and
`app.llm.provider`'s documented-but-unbuilt extension points already
work elsewhere in this codebase (an interface a later milestone
implements, not a promise this one keeps).

    domain event occurs (e.g. a ModelReviewFlag is created)
        -> OutboundEvent(name=..., organization_id=..., payload={...})
        -> WebhookDispatcher.dispatch(event)   -- NoOpWebhookDispatcher today
        -> [future: HTTP POST to a registered per-organization endpoint,
            signed, retried, with a delivery-attempt log]

Named events this codebase's own domains would plausibly emit, once a
real dispatcher exists (documented now so a future subscriber knows
what vocabulary to expect; **none of these are actually emitted
anywhere today** — see `NoOpWebhookDispatcher`):

    risk.signal.created       -- app/intelligence/signals.py detects a new RiskSignal
    prediction.available      -- app/predictions/predictor.py records a PREDICTED outcome
    model.review.required     -- app/predictions/drift.py flags a model (MODEL_REVIEW_REQUIRED)
    knowledge.updated         -- a KnowledgeDocumentVersion is created

`payload` would carry only what the corresponding read API already
returns to an authorized caller for that resource — never a new
information-disclosure surface, and never a feature vector, raw event
description, or other sensitive content (the same restraint
`app/services/audit_service.py`'s own metadata already practices).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


class WebhookEventName:
    """The vocabulary this module documents — see module docstring for
    what each name would mean and which domain would emit it."""

    RISK_SIGNAL_CREATED = "risk.signal.created"
    PREDICTION_AVAILABLE = "prediction.available"
    MODEL_REVIEW_REQUIRED = "model.review.required"
    KNOWLEDGE_UPDATED = "knowledge.updated"


@dataclass(frozen=True)
class OutboundEvent:
    name: str
    organization_id: uuid.UUID | None
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookDispatcher(Protocol):
    """The one seam a real delivery implementation (HTTP callouts with
    per-organization registered endpoints, signing, retry/backoff, a
    delivery-attempt audit trail) would implement. Nothing in this
    codebase currently constructs anything other than
    `NoOpWebhookDispatcher` below."""

    def dispatch(self, event: OutboundEvent) -> None: ...


class NoOpWebhookDispatcher:
    """The only implementation that exists today. Deliberately inert —
    calling `dispatch()` documents the call site's intent for a future
    milestone without this one silently pretending to deliver anything.
    """

    def dispatch(self, event: OutboundEvent) -> None:
        return None


def get_webhook_dispatcher() -> WebhookDispatcher:
    return _dispatcher


_dispatcher: WebhookDispatcher = NoOpWebhookDispatcher()
