"""Internal dataclasses for the ingestion pipeline — distinct from
`app/schemas/intelligence.py` (the Pydantic HTTP request/response
shapes), the same internal-domain-object/API-schema split already used
throughout this codebase (`app/retrieval/results.py`/`app/schemas/retrieval.py`,
`app/rag/results.py`/`app/schemas/rag.py`).

    RawSafetyEventPayload (whatever a caller sent, unvalidated)
        -> validate_payload() -> ValidationResult
        -> normalize_payload() -> NormalizedSafetyEvent
        -> SafetyEventIngestionService -> SafetyEvent row
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawSafetyEventPayload:
    """Exactly what an external caller sent, before any validation or
    normalization — every field optional, since "missing" is itself a
    condition `validate_payload()` must be able to report rather than a
    `TypeError` a caller has to avoid. `event_time`/`period_end`/
    `reported_time` are left as `str | datetime | None` — normalization
    parses whichever a caller sent (see `app/intelligence/normalization.py`).
    """

    event_type: str | None = None
    event_subtype: str | None = None
    event_time: str | datetime | None = None
    period_end: str | datetime | None = None
    reported_time: str | datetime | None = None
    site_id: str | uuid.UUID | None = None
    location: str | None = None
    project: str | None = None
    department: str | None = None
    contractor: str | None = None
    activity: str | None = None
    severity: str | None = None
    potential_severity: str | None = None
    status: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    source_system: str | None = None
    source_record_id: str | None = None

    def as_source_value(self) -> dict[str, Any]:
        """The exact payload as received, for `SafetyEvent.source_value`
        — milestone item 14's "keep source_value / normalized_value"
        requirement. Plain field-by-field, not `dataclasses.asdict`, so a
        `datetime` object a caller passed in directly still serializes to
        JSON cleanly."""
        return {
            "event_type": self.event_type,
            "event_subtype": self.event_subtype,
            "event_time": _isoformat(self.event_time),
            "period_end": _isoformat(self.period_end),
            "reported_time": _isoformat(self.reported_time),
            "site_id": str(self.site_id) if self.site_id else None,
            "location": self.location,
            "project": self.project,
            "department": self.department,
            "contractor": self.contractor,
            "activity": self.activity,
            "severity": self.severity,
            "potential_severity": self.potential_severity,
            "status": self.status,
            "description": self.description,
            "attributes": self.attributes,
            "source_system": self.source_system,
            "source_record_id": self.source_record_id,
        }


def _isoformat(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation finding — milestone item 12's own
    example list (`MISSING_EVENT_TIME`, `INVALID_SEVERITY`,
    `IMPOSSIBLE_DATE`, ...) is exactly `code`'s vocabulary; see
    `app/intelligence/validation.py`."""

    code: str
    message: str
    blocking: bool  # True: this issue alone forces QUARANTINED/rejection


@dataclass
class ValidationResult:
    status: str  # DataQualityStatus value, or "REJECTED" (no row can be stored at all)
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class NormalizedSafetyEvent:
    """The fully validated, normalized event, ready to write to
    `SafetyEvent` — every field here maps onto that model's own column
    one-to-one. Never constructed for a `ValidationResult.status ==
    "REJECTED"` payload (see `app/intelligence/ingestion_service.py`)."""

    organization_id: uuid.UUID
    event_type: str
    event_subtype: str | None
    event_time: datetime
    period_end: datetime | None
    reported_time: datetime | None
    site_id: uuid.UUID | None
    location: str | None
    project: str | None
    department: str | None
    contractor: str | None
    activity: str | None
    severity: str | None
    potential_severity: str | None
    status: str | None
    description: str | None
    attributes: dict[str, Any]
    source_system: str
    source_record_id: str
    source_value: dict[str, Any]
