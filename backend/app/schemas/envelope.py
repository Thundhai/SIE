"""Standard response envelope — Intelligence Platform Integration &
Enterprise API v0.1, item 10.

**Applied to new response shapes only, never retroactively wrapping an
existing one** (item 35's "do not break existing v1 consumers" —
changing `PredictionRead`'s or `AnalyticsSummaryRead`'s top-level JSON
shape to `{"data": {...}, ...}` would silently break every existing
caller that parses today's unwrapped body). Every *existing* v1 endpoint
instead gets this same contract's metadata additively, via response
headers (`X-Request-Id` — see `app/core/request_id.py`) and, for errors,
the additive `error` object (see `app/core/errors.py`) — never a body
shape change. `ResponseEnvelope` here is what a genuinely *new* endpoint
introduced from this milestone onward uses (e.g.
`GET /predictions/{entity_id}/history`), and is available for any future
v2 surface to use uniformly from the start.

    {
      "data": <the endpoint's own real response payload>,
      "status": "SUCCESS",
      "request_id": "...",
      "timestamp": "...",
      "data_quality": "GOOD" | "LIMITED" | "INSUFFICIENT" | "STALE" | null,
      "provenance": {...} | null
    }

**"Do not force fields into responses when they are meaningless"** (item
10's own instruction) — `data_quality` and `provenance` are both
`Optional`/nullable, and `build_envelope()` below only ever sets them
when the endpoint actually has something meaningful to say; a `None`
here is never rendered as a false claim of certainty.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    data: T
    status: str = "SUCCESS"
    request_id: str | None = None
    timestamp: datetime
    data_quality: str | None = None
    provenance: dict[str, Any] | None = None


def build_envelope(
    data: T,
    *,
    request_id: str | None,
    data_quality: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> ResponseEnvelope[T]:
    return ResponseEnvelope[T](
        data=data,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc),
        data_quality=data_quality,
        provenance=provenance,
    )
