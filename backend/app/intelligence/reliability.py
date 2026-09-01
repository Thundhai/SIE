"""Data source reliability and freshness — milestone items 32-33.

Computed directly by aggregating `safety_events` grouped by
`source_system` — no separate materialized table (see
`app/models/safety_event.py`'s docstring on why `ingestion_batch_id` is
a plain column, not a foreign key into a batch-tracking table; the same
judgment applies here). This will matter more once several organizations
connect several different systems each — milestone item 33's own framing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.enums import DataQualityStatus
from app.intelligence.temporal import utcnow
from app.models.safety_event import SafetyEvent


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


@dataclass
class SourceReliability:
    source_system: str
    record_count: int
    valid_count: int
    partial_count: int
    invalid_count: int
    quarantined_count: int
    latest_event_time: datetime | None
    latest_ingestion_time: datetime | None
    is_stale: bool
    freshness_threshold_days: int


def compute_source_reliability(
    db: Session,
    *,
    organization_id: uuid.UUID,
    source_system: str | None = None,
    freshness_threshold_days: int | None = None,
    as_of: datetime | None = None,
) -> list[SourceReliability]:
    as_of = as_of or utcnow()
    freshness_threshold_days = (
        freshness_threshold_days
        if freshness_threshold_days is not None
        else settings.INTELLIGENCE_FRESHNESS_THRESHOLD_DAYS
    )

    def _count(status: str, source: str) -> int:
        stmt = select(func.count()).where(
            SafetyEvent.organization_id == organization_id,
            SafetyEvent.source_system == source,
            SafetyEvent.data_quality_status == status,
        )
        return db.execute(stmt).scalar_one()

    sources_stmt = select(SafetyEvent.source_system).where(
        SafetyEvent.organization_id == organization_id
    ).distinct()
    if source_system:
        sources_stmt = sources_stmt.where(SafetyEvent.source_system == source_system)
    sources = [row[0] for row in db.execute(sources_stmt).all()]

    results: list[SourceReliability] = []
    for source in sources:
        total = db.execute(
            select(func.count()).where(
                SafetyEvent.organization_id == organization_id, SafetyEvent.source_system == source
            )
        ).scalar_one()
        latest_event_time, latest_ingestion_time = db.execute(
            select(func.max(SafetyEvent.event_time), func.max(SafetyEvent.ingestion_time)).where(
                SafetyEvent.organization_id == organization_id, SafetyEvent.source_system == source
            )
        ).one()
        # SQLite (used by this project's ordinary test suite -- see
        # tests/conftest.py) has no native timezone-aware datetime type
        # and returns naive UTC values from a MAX() aggregate even when
        # the column itself is DateTime(timezone=True); PostgreSQL does
        # not have this quirk. Normalize defensively so this function
        # behaves identically on both.
        latest_event_time = _as_utc(latest_event_time)
        latest_ingestion_time = _as_utc(latest_ingestion_time)

        is_stale = (
            latest_ingestion_time is None
            or (as_of - latest_ingestion_time).days > freshness_threshold_days
        )

        results.append(
            SourceReliability(
                source_system=source,
                record_count=total,
                valid_count=_count(DataQualityStatus.VALID.value, source),
                partial_count=_count(DataQualityStatus.PARTIAL.value, source),
                invalid_count=_count(DataQualityStatus.INVALID.value, source),
                quarantined_count=_count(DataQualityStatus.QUARANTINED.value, source),
                latest_event_time=latest_event_time,
                latest_ingestion_time=latest_ingestion_time,
                is_stale=is_stale,
                freshness_threshold_days=freshness_threshold_days,
            )
        )
    return results
