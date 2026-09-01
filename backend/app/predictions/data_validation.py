"""Real-data validation — Model Validation & Governance v0.1, items 5-6.

    SafetyEvent rows (organization, site scope, date range)
        -> completeness / consistency / duplicate / temporal-integrity /
           freshness / distribution checks
        -> DatasetQualityReport (structured, never a single collapsed score)

**Never automatically modifies questionable data (item 5's own
instruction).** This module only ever reads and reports — a record's
`data_quality_status` (already set by
`app/intelligence/ingestion_service.py` at ingestion time) is never
changed here; a dataset with a high quarantine/invalid rate is reported
as such, not silently cleaned up before training.

Used by `app/predictions/dataset_registry.py::register_dataset()` for
both `SYNTHETIC` and `REAL` datasets alike — the checks themselves don't
care which environment they're validating; only the caller's tagging
does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.enums import DataQualityStatus
from app.models.safety_event import SafetyEvent
from app.models.site import Site

OVERALL_GOOD = "GOOD"
OVERALL_LIMITED = "LIMITED"
OVERALL_INSUFFICIENT = "INSUFFICIENT"

# --- INITIAL GOVERNANCE DEFAULT thresholds ---------------------------------------------
# Configurable, documented starting points -- not a universally validated
# industry standard (milestone item 6's own instruction). A caller may
# override any of these by passing its own DataQualityThresholds.
DEFAULT_MAX_QUARANTINED_RATE_FOR_GOOD = 0.02
DEFAULT_MAX_QUARANTINED_RATE_FOR_LIMITED = 0.10
DEFAULT_MAX_MISSING_SITE_RATE_FOR_GOOD = 0.02
DEFAULT_MAX_MISSING_SITE_RATE_FOR_LIMITED = 0.15
DEFAULT_MAX_DUPLICATE_RATE_FOR_GOOD = 0.01
DEFAULT_MAX_DUPLICATE_RATE_FOR_LIMITED = 0.05
DEFAULT_STALENESS_WARNING_DAYS = 90


@dataclass
class DataQualityThresholds:
    """INITIAL GOVERNANCE DEFAULT — see module docstring. Every field is
    overridable per call; nothing here is hard-coded as a universal
    truth about what "good" safety data looks like."""

    max_quarantined_rate_for_good: float = DEFAULT_MAX_QUARANTINED_RATE_FOR_GOOD
    max_quarantined_rate_for_limited: float = DEFAULT_MAX_QUARANTINED_RATE_FOR_LIMITED
    max_missing_site_rate_for_good: float = DEFAULT_MAX_MISSING_SITE_RATE_FOR_GOOD
    max_missing_site_rate_for_limited: float = DEFAULT_MAX_MISSING_SITE_RATE_FOR_LIMITED
    max_duplicate_rate_for_good: float = DEFAULT_MAX_DUPLICATE_RATE_FOR_GOOD
    max_duplicate_rate_for_limited: float = DEFAULT_MAX_DUPLICATE_RATE_FOR_LIMITED
    staleness_warning_days: int = DEFAULT_STALENESS_WARNING_DAYS


@dataclass
class ValidationIssue:
    code: str
    message: str
    count: int = 0


@dataclass
class CompletenessReport:
    missing_site_rate: float | None
    missing_severity_rate: float | None  # among INCIDENT/NEAR_MISS records only
    sites_with_no_exposure_records: int
    total_sites: int
    missing_exposure_rate: float | None  # fraction of sites with zero exposure records


@dataclass
class FreshnessReport:
    latest_event_time: datetime | None
    latest_ingestion_time: datetime | None
    staleness_days: int | None  # days between latest_event_time and as_of
    is_stale: bool


@dataclass
class DatasetQualityReport:
    record_count: int
    valid_count: int
    partial_count: int
    quarantined_count: int
    invalid_count: int
    duplicate_record_count: int  # records sharing (source_system, source_record_id) more than once

    date_range_start: date | None
    date_range_end: date | None

    completeness: CompletenessReport
    consistency_issues: list[ValidationIssue]
    temporal_integrity_issues: list[ValidationIssue]
    freshness: FreshnessReport
    distribution_notes: list[str]

    overall_quality: str  # GOOD | LIMITED | INSUFFICIENT
    thresholds_used: DataQualityThresholds = field(default_factory=DataQualityThresholds)

    def to_dict(self) -> dict:
        """JSON-serializable form for `DatasetVersion.quality_report`.
        `asdict()` already recurses into the nested dataclasses; only the
        raw `datetime`/`date` fields need explicit stringification."""
        d = asdict(self)
        fr = d["freshness"]
        if fr["latest_event_time"] is not None:
            fr["latest_event_time"] = fr["latest_event_time"].isoformat()
        if fr["latest_ingestion_time"] is not None:
            fr["latest_ingestion_time"] = fr["latest_ingestion_time"].isoformat()
        if d["date_range_start"] is not None:
            d["date_range_start"] = d["date_range_start"].isoformat()
        if d["date_range_end"] is not None:
            d["date_range_end"] = d["date_range_end"].isoformat()
        return d


_SEVERITY_SCORED_TYPES = frozenset({"INCIDENT", "NEAR_MISS"})


def _as_utc(value: datetime) -> datetime:
    """SQLite (the test database — see tests/conftest.py) does not
    persist `tzinfo`; PostgreSQL does. A naive value read back from
    SQLite is always UTC in this codebase (every write goes through
    `app.intelligence.normalization`, which stamps UTC) — mirrors
    `app/intelligence/reliability.py::_as_utc()` and
    `app/predictions/predictor.py::_as_utc()`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def validate_dataset(
    db: Session,
    *,
    organization_id: UUID,
    site_ids: list[UUID] | None = None,
    date_range_start: datetime,
    date_range_end: datetime,
    as_of: datetime | None = None,
    thresholds: DataQualityThresholds | None = None,
) -> DatasetQualityReport:
    """Validates every `SafetyEvent` for `organization_id` (optionally
    limited to `site_ids`) within `[date_range_start, date_range_end]` —
    deliberately including `QUARANTINED`/`INVALID` records too (unlike
    `app/intelligence/temporal.py::events_as_of()`, which excludes them
    for feature computation): a quality report exists specifically to
    surface how much of the data is unusable, not to hide it."""
    as_of = as_of or datetime.now(timezone.utc)
    thresholds = thresholds or DataQualityThresholds()

    query = select(SafetyEvent).where(
        SafetyEvent.organization_id == organization_id,
        SafetyEvent.event_time >= date_range_start,
        SafetyEvent.event_time <= date_range_end,
    )
    if site_ids:
        query = query.where(SafetyEvent.site_id.in_(site_ids))
    events = list(db.execute(query).scalars().all())

    record_count = len(events)
    by_status = {s.value: 0 for s in DataQualityStatus}
    for e in events:
        by_status[e.data_quality_status] = by_status.get(e.data_quality_status, 0) + 1

    # --- Duplicates (item 5: "source system, source record ID") ------------------------
    seen: dict[tuple[str, str], int] = {}
    for e in events:
        key = (e.source_system, e.source_record_id)
        seen[key] = seen.get(key, 0) + 1
    duplicate_record_count = sum(count - 1 for count in seen.values() if count > 1)

    # --- Completeness (item 5) ----------------------------------------------------------
    missing_site_rate = (sum(1 for e in events if e.site_id is None) / record_count) if record_count else None
    severity_scoped = [e for e in events if e.event_type in _SEVERITY_SCORED_TYPES]
    missing_severity_rate = (
        (sum(1 for e in severity_scoped if not e.severity) / len(severity_scoped)) if severity_scoped else None
    )

    relevant_site_ids = site_ids
    if relevant_site_ids is None:
        relevant_site_ids = [
            row[0]
            for row in db.execute(select(Site.id).where(Site.organization_id == organization_id)).all()
        ]
    sites_with_exposure = {
        e.site_id
        for e in events
        if e.site_id is not None and e.event_type == "WORKFORCE" and e.event_subtype == "EXPOSURE_HOURS"
    }
    sites_with_no_exposure = [s for s in relevant_site_ids if s not in sites_with_exposure]
    completeness = CompletenessReport(
        missing_site_rate=round(missing_site_rate, 4) if missing_site_rate is not None else None,
        missing_severity_rate=round(missing_severity_rate, 4) if missing_severity_rate is not None else None,
        sites_with_no_exposure_records=len(sites_with_no_exposure),
        total_sites=len(relevant_site_ids),
        missing_exposure_rate=(
            round(len(sites_with_no_exposure) / len(relevant_site_ids), 4) if relevant_site_ids else None
        ),
    )

    # --- Consistency (item 5) ------------------------------------------------------------
    known_site_ids = set(relevant_site_ids)
    orphan_site_refs = [e for e in events if e.site_id is not None and e.site_id not in known_site_ids]
    consistency_issues: list[ValidationIssue] = []
    if orphan_site_refs:
        consistency_issues.append(
            ValidationIssue(
                code="SITE_REFERENCE_NOT_FOUND",
                message="Records reference a site_id that does not belong to this organization.",
                count=len(orphan_site_refs),
            )
        )

    # --- Temporal integrity (item 5) ------------------------------------------------------
    temporal_integrity_issues: list[ValidationIssue] = []
    backdated_ingestion = [e for e in events if e.ingestion_time < e.event_time]
    if backdated_ingestion:
        temporal_integrity_issues.append(
            ValidationIssue(
                code="INGESTION_TIME_BEFORE_EVENT_TIME",
                message="Record was ingested before its own event_time -- a data entry or clock error, "
                "since a record cannot be reported before it happens.",
                count=len(backdated_ingestion),
            )
        )
    reported_before_event = [
        e for e in events if e.reported_time is not None and e.reported_time < e.event_time
    ]
    if reported_before_event:
        temporal_integrity_issues.append(
            ValidationIssue(
                code="REPORTED_TIME_BEFORE_EVENT_TIME",
                message="Record's reported_time precedes its event_time.",
                count=len(reported_before_event),
            )
        )

    # --- Freshness (item 5) ---------------------------------------------------------------
    latest_event_time = max((e.event_time for e in events), default=None)
    latest_ingestion_time = max((e.ingestion_time for e in events), default=None)
    staleness_days = None
    is_stale = False
    if latest_event_time is not None:
        staleness_days = (_as_utc(as_of) - _as_utc(latest_event_time)).days
        is_stale = staleness_days > thresholds.staleness_warning_days
    freshness = FreshnessReport(
        latest_event_time=latest_event_time,
        latest_ingestion_time=latest_ingestion_time,
        staleness_days=staleness_days,
        is_stale=is_stale,
    )

    # --- Distribution (item 5) -------------------------------------------------------------
    distribution_notes = _detect_distribution_anomalies(events, _as_utc(date_range_start), _as_utc(date_range_end))

    # --- Overall (item 6: never a single collapsed score alone -- this is
    # in addition to, not instead of, every field above) --------------------
    quarantined_rate = (by_status.get("QUARANTINED", 0) / record_count) if record_count else 1.0
    invalid_rate = (by_status.get("INVALID", 0) / record_count) if record_count else 1.0
    duplicate_rate = (duplicate_record_count / record_count) if record_count else 0.0

    if record_count == 0:
        overall_quality = OVERALL_INSUFFICIENT
    elif (
        quarantined_rate + invalid_rate <= thresholds.max_quarantined_rate_for_good
        and (missing_site_rate or 0) <= thresholds.max_missing_site_rate_for_good
        and duplicate_rate <= thresholds.max_duplicate_rate_for_good
        and not is_stale
    ):
        overall_quality = OVERALL_GOOD
    elif (
        quarantined_rate + invalid_rate <= thresholds.max_quarantined_rate_for_limited
        and (missing_site_rate or 0) <= thresholds.max_missing_site_rate_for_limited
        and duplicate_rate <= thresholds.max_duplicate_rate_for_limited
    ):
        overall_quality = OVERALL_LIMITED
    else:
        overall_quality = OVERALL_INSUFFICIENT

    return DatasetQualityReport(
        record_count=record_count,
        valid_count=by_status.get("VALID", 0),
        partial_count=by_status.get("PARTIAL", 0),
        quarantined_count=by_status.get("QUARANTINED", 0),
        invalid_count=by_status.get("INVALID", 0),
        duplicate_record_count=duplicate_record_count,
        date_range_start=date_range_start.date() if isinstance(date_range_start, datetime) else date_range_start,
        date_range_end=date_range_end.date() if isinstance(date_range_end, datetime) else date_range_end,
        completeness=completeness,
        consistency_issues=consistency_issues,
        temporal_integrity_issues=temporal_integrity_issues,
        freshness=freshness,
        distribution_notes=distribution_notes,
        overall_quality=overall_quality,
        thresholds_used=thresholds,
    )


def _detect_distribution_anomalies(
    events: list[SafetyEvent], date_range_start: datetime, date_range_end: datetime
) -> list[str]:
    """A lightweight, explainable check for an unusual change in event
    frequency across the dataset's own span — splits the range into two
    halves and flags a >3x swing either way. Not a claim about *why* the
    frequency changed (worsening conditions vs. a reporting-culture shift
    vs. a data migration artifact — see `app/predictions/spec.py` item 5's
    reporting-bias note) — only that it changed enough to warrant a
    human look before training on it."""
    notes: list[str] = []
    span = date_range_end - date_range_start
    if span <= timedelta(days=2) or not events:
        return notes
    midpoint = date_range_start + span / 2

    first_half = [e for e in events if _as_utc(e.event_time) < midpoint]
    second_half = [e for e in events if _as_utc(e.event_time) >= midpoint]
    if not first_half or not second_half:
        return notes

    ratio = len(second_half) / max(len(first_half), 1)
    if ratio >= 3.0 or ratio <= (1.0 / 3.0):
        notes.append(
            f"Event frequency changed sharply between the first and second half of the date range "
            f"({len(first_half)} -> {len(second_half)} records) -- verify this reflects a real "
            f"operational change, not an ingestion gap or a reporting-culture shift."
        )

    severities = [e.severity for e in events if e.severity]
    if severities:
        unique_severities = set(severities)
        if len(unique_severities) == 1:
            notes.append(
                f"Every scored record shares the same severity value ({next(iter(unique_severities))!r}) -- "
                "check this isn't a default/placeholder value rather than a real assessment."
            )

    return notes


__all__ = [
    "OVERALL_GOOD",
    "OVERALL_INSUFFICIENT",
    "OVERALL_LIMITED",
    "CompletenessReport",
    "DataQualityThresholds",
    "DatasetQualityReport",
    "FreshnessReport",
    "ValidationIssue",
    "validate_dataset",
]
