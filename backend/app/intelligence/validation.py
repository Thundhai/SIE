"""Deterministic validation — milestone item 12. Every rule here is
explicit and rule-based (no ML, no heuristic scoring) and never silently
"fixes" a questionable value; a rule either accepts a normalized value or
records a `ValidationIssue` and leaves the original in `source_value`
untouched (see `app/intelligence/schemas.py`).

    RawSafetyEventPayload -> validate_and_normalize()
        -> (ValidationResult, NormalizedSafetyEvent | None)

`ValidationResult.status` is one of `DataQualityStatus`'s values, or the
sentinel `"REJECTED"` — the one outcome with no `NormalizedSafetyEvent`
at all (the payload is missing the minimum identity fields
`app/models/safety_event.py`'s schema requires just to store a row: an
organization, `source_system`, `source_record_id`, and `event_type`).
Everything else is stored, however degraded — milestone item 12: "do not
silently 'fix' questionable data... preserve original values."

**Classification rule:**

  * Missing `source_system`, `source_record_id`, or `event_type`
    entirely -> `"REJECTED"` (no row written at all).
  * A *blocking* issue (missing/unparseable `event_time`, an impossible
    date/duration) but the record can still be identified and stored ->
    `QUARANTINED` — stored, but excluded from every feature/indicator/
    signal calculation (see `app/intelligence/temporal.py`).
  * Only *non-blocking* issues (an unrecognized severity/event-type
    value, ...) -> `PARTIAL` — stored and used, with the issue visible.
  * No issues -> `VALID`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enums import DataQualityStatus, SafetyEventType
from app.intelligence.normalization import (
    normalize_category,
    normalize_datetime,
    normalize_severity,
    normalize_status,
)
from app.intelligence.schemas import (
    NormalizedSafetyEvent,
    RawSafetyEventPayload,
    ValidationIssue,
    ValidationResult,
)

# A record dated further into the future than this is almost certainly a
# malformed date (a typo'd year, a unit confusion), not a genuine
# forward-dated record (e.g. a scheduled inspection) -- see IMPOSSIBLE_DATE.
_MAX_FUTURE_SKEW = timedelta(days=3650)

_MAX_SOURCE_RECORD_ID_LENGTH = 255


def validate_and_normalize(
    raw: RawSafetyEventPayload, *, organization_id: uuid.UUID
) -> tuple[ValidationResult, NormalizedSafetyEvent | None]:
    issues: list[ValidationIssue] = []

    source_system = (raw.source_system or "").strip()
    source_record_id = (raw.source_record_id or "").strip()
    event_type_raw = (raw.event_type or "").strip()

    if not source_system:
        issues.append(ValidationIssue("MISSING_SOURCE_SYSTEM", "source_system is required.", True))
    source_record_id_too_long = len(source_record_id) > _MAX_SOURCE_RECORD_ID_LENGTH
    if not source_record_id:
        issues.append(
            ValidationIssue("MISSING_SOURCE_RECORD_ID", "source_record_id is required.", True)
        )
    elif source_record_id_too_long:
        # Not just "degraded" -- SafetyEvent.source_record_id is a
        # String(255) column, so a value this long cannot be stored at
        # all without truncation/corruption. Treated the same as a
        # missing identity field: REJECTED, not QUARANTINED.
        issues.append(
            ValidationIssue(
                "MALFORMED_SOURCE_RECORD_ID",
                f"source_record_id exceeds {_MAX_SOURCE_RECORD_ID_LENGTH} characters.",
                True,
            )
        )
    if not event_type_raw:
        issues.append(ValidationIssue("MISSING_EVENT_TYPE", "event_type is required.", True))

    if not source_system or not source_record_id or source_record_id_too_long or not event_type_raw:
        # Cannot even identify/store this record -- no idempotency key,
        # no domain to classify it under, or a value that would not fit
        # the column at all.
        return ValidationResult(status="REJECTED", issues=issues), None

    normalized_event_type = event_type_raw.upper()
    if normalized_event_type not in SafetyEventType.__members__:
        issues.append(
            ValidationIssue(
                "UNRECOGNIZED_EVENT_TYPE",
                f"event_type {event_type_raw!r} is not one of the recognized domains "
                "(still stored -- the model is deliberately extensible).",
                False,
            )
        )

    event_time = normalize_datetime(raw.event_time)
    if raw.event_time is None:
        issues.append(ValidationIssue("MISSING_EVENT_TIME", "event_time is required.", True))
    elif event_time is None:
        issues.append(
            ValidationIssue("INVALID_EVENT_TIME", f"event_time {raw.event_time!r} could not be parsed.", True)
        )
    else:
        now = datetime.now(timezone.utc)
        if event_time > now + _MAX_FUTURE_SKEW:
            issues.append(
                ValidationIssue(
                    "IMPOSSIBLE_DATE", f"event_time {event_time.isoformat()} is implausibly far in the future.", True
                )
            )

    period_end = normalize_datetime(raw.period_end)
    if raw.period_end is not None and period_end is None:
        issues.append(
            ValidationIssue("INVALID_PERIOD_END", f"period_end {raw.period_end!r} could not be parsed.", False)
        )
    if period_end is not None and event_time is not None and period_end < event_time:
        issues.append(
            ValidationIssue(
                "IMPOSSIBLE_DURATION", "period_end is before event_time.", True
            )
        )

    reported_time = normalize_datetime(raw.reported_time)
    if raw.reported_time is not None and reported_time is None:
        issues.append(
            ValidationIssue(
                "INVALID_REPORTED_TIME", f"reported_time {raw.reported_time!r} could not be parsed.", False
            )
        )

    normalized_severity = normalize_severity(raw.severity)
    if raw.severity is not None and normalized_severity is None:
        issues.append(
            ValidationIssue("INVALID_SEVERITY", f"severity {raw.severity!r} is not a recognized value.", False)
        )

    normalized_potential_severity = normalize_severity(raw.potential_severity)
    if raw.potential_severity is not None and normalized_potential_severity is None:
        issues.append(
            ValidationIssue(
                "INVALID_POTENTIAL_SEVERITY",
                f"potential_severity {raw.potential_severity!r} is not a recognized value.",
                False,
            )
        )

    site_id: uuid.UUID | None = None
    if raw.site_id is not None:
        try:
            site_id = raw.site_id if isinstance(raw.site_id, uuid.UUID) else uuid.UUID(str(raw.site_id))
        except ValueError:
            issues.append(ValidationIssue("INVALID_SITE_ID", f"site_id {raw.site_id!r} is not a valid UUID.", False))

    blocking = any(issue.blocking for issue in issues)
    status = (
        DataQualityStatus.QUARANTINED.value
        if blocking
        else (DataQualityStatus.PARTIAL.value if issues else DataQualityStatus.VALID.value)
    )

    # A record without a usable event_time cannot be placed on the
    # timeline at all -- fall back to reported_time, then "now", purely
    # so a row can still be *stored* (never silently dropped); this
    # record's QUARANTINED status is exactly what keeps a fabricated
    # timestamp like this out of every temporal feature calculation (see
    # app/intelligence/temporal.py).
    effective_event_time = event_time or reported_time or datetime.now(timezone.utc)

    normalized = NormalizedSafetyEvent(
        organization_id=organization_id,
        event_type=normalized_event_type,
        event_subtype=normalize_category(raw.event_subtype),
        event_time=effective_event_time,
        period_end=period_end,
        reported_time=reported_time,
        site_id=site_id,
        location=normalize_category(raw.location),
        project=normalize_category(raw.project),
        department=normalize_category(raw.department),
        contractor=normalize_category(raw.contractor),
        activity=normalize_category(raw.activity),
        severity=normalized_severity,
        potential_severity=normalized_potential_severity,
        status=normalize_status(raw.status),
        description=raw.description,
        attributes=dict(raw.attributes or {}),
        source_system=source_system,
        source_record_id=source_record_id,
        source_value=raw.as_source_value(),
    )
    return ValidationResult(status=status, issues=issues), normalized
