"""DatasetVersion registry — Model Validation & Governance v0.1, items
3-4, 20.

    register_dataset(environment=SYNTHETIC|REAL, ...)
        -> app/predictions/data_validation.py::validate_dataset()  (server-computed only)
        -> DatasetVersion row (versioned, immutable once created)

**Environment is required on every call — never inferred, never
defaulted.** `register_synthetic_dataset()` and `register_real_dataset()`
are the two entry points every caller actually uses; both simply pin
`environment` and forward to `register_dataset()`, so there is no code
path that creates a dataset record without an explicit environment tag
(milestone item 3).

**Real data never touches this repository (milestone item 36).**
`register_real_dataset()` reads whatever `SafetyEvent` rows an
organization has already ingested through the existing, generic
ingestion pipeline (API or batch — see
`app/intelligence/ingestion_service.py`) — it never accepts a raw file
or a bulk payload itself, and nothing here writes real data to disk or
to a fixture file. The one thing this module persists about real data is
metadata (counts, date ranges, a quality report) — never the underlying
event content.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset_version import DatasetVersion
from app.models.site import Site
from app.predictions.data_validation import DataQualityThresholds, validate_dataset
from app.predictions.dataset import build_training_examples
from app.predictions.enums import DatasetEnvironment
from app.predictions.spec import (
    FEATURE_SET_VERSION,
    HORIZON_DAYS,
    PREDICTION_ENTITY_TYPE,
    PREDICTION_TARGET_VERSION,
)
from app.services.audit_service import AuditAction, audit_service


def _next_dataset_version(db: Session, *, organization_id: uuid.UUID, dataset_id: str) -> str:
    existing = db.execute(
        select(DatasetVersion.dataset_version).where(
            DatasetVersion.organization_id == organization_id,
            DatasetVersion.dataset_id == dataset_id,
        )
    ).scalars().all()
    highest = 0
    for v in existing:
        if v.startswith("v") and v[1:].isdigit():
            highest = max(highest, int(v[1:]))
    return f"v{highest + 1}"


def register_dataset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    dataset_id: str,
    environment: DatasetEnvironment,
    date_range_start: datetime,
    date_range_end: datetime,
    source_systems: list[str],
    site_ids: list[uuid.UUID] | None = None,
    feature_set_version: str = FEATURE_SET_VERSION,
    target_version: str = PREDICTION_TARGET_VERSION,
    prediction_horizon_days: int = HORIZON_DAYS,
    entity_type: str = PREDICTION_ENTITY_TYPE,
    thresholds: DataQualityThresholds | None = None,
    user_id: uuid.UUID | None = None,
) -> DatasetVersion:
    """Runs `validate_dataset()` itself — the quality report is always
    server-computed from this organization's own stored data, never
    accepted as caller input (milestone item 49: no client-supplied
    evaluation results)."""
    report = validate_dataset(
        db,
        organization_id=organization_id,
        site_ids=site_ids,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        thresholds=thresholds,
    )

    relevant_site_ids = site_ids
    if relevant_site_ids is None:
        relevant_site_ids = [
            row[0] for row in db.execute(select(Site.id).where(Site.organization_id == organization_id)).all()
        ]

    entry = DatasetVersion(
        organization_id=organization_id,
        dataset_id=dataset_id,
        dataset_version=_next_dataset_version(db, organization_id=organization_id, dataset_id=dataset_id),
        environment=environment.value,
        source_systems=list(source_systems),
        date_range_start=date_range_start.date() if isinstance(date_range_start, datetime) else date_range_start,
        date_range_end=date_range_end.date() if isinstance(date_range_end, datetime) else date_range_end,
        feature_set_version=feature_set_version,
        target_version=target_version,
        prediction_horizon_days=prediction_horizon_days,
        entity_type=entity_type,
        entity_count=len(relevant_site_ids),
        record_count=report.record_count,
        quality_report=report.to_dict(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    audit_service.log(
        db,
        action=AuditAction.DATASET_VALIDATED,
        resource_type="dataset_version",
        resource_id=entry.id,
        organization_id=organization_id,
        user_id=user_id,
        metadata={
            "dataset_id": dataset_id,
            "dataset_version": entry.dataset_version,
            "environment": entry.environment,
            "overall_quality": report.overall_quality,
            "record_count": report.record_count,
        },
    )
    return entry


def register_synthetic_dataset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    dataset_id: str,
    date_range_start: datetime,
    date_range_end: datetime,
    site_ids: list[uuid.UUID] | None = None,
    source_systems: list[str] | None = None,
    user_id: uuid.UUID | None = None,
) -> DatasetVersion:
    return register_dataset(
        db,
        organization_id=organization_id,
        dataset_id=dataset_id,
        environment=DatasetEnvironment.SYNTHETIC,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        source_systems=source_systems or ["synthetic-fixture"],
        site_ids=site_ids,
        user_id=user_id,
    )


def register_real_dataset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    dataset_id: str,
    date_range_start: datetime,
    date_range_end: datetime,
    source_systems: list[str],
    site_ids: list[uuid.UUID] | None = None,
    thresholds: DataQualityThresholds | None = None,
    user_id: uuid.UUID | None = None,
) -> DatasetVersion:
    """Registers a dataset built from an organization's own real,
    already-ingested `SafetyEvent` data (via the existing API/batch
    ingestion pipeline — see module docstring). `source_systems` must
    name the real system(s) the data actually came from (e.g.
    `["safelytic"]`) — never left to a synthetic-fixture default."""
    if not source_systems:
        raise ValueError("register_real_dataset() requires at least one named source_system.")
    return register_dataset(
        db,
        organization_id=organization_id,
        dataset_id=dataset_id,
        environment=DatasetEnvironment.REAL,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        source_systems=source_systems,
        site_ids=site_ids,
        thresholds=thresholds,
        user_id=user_id,
    )


def get_dataset_version(db: Session, *, organization_id: uuid.UUID, dataset_version_id: uuid.UUID) -> DatasetVersion | None:
    return db.execute(
        select(DatasetVersion).where(
            DatasetVersion.id == dataset_version_id, DatasetVersion.organization_id == organization_id
        )
    ).scalar_one_or_none()


def list_dataset_versions(db: Session, *, organization_id: uuid.UUID) -> list[DatasetVersion]:
    return list(
        db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.organization_id == organization_id)
            .order_by(DatasetVersion.created_at.desc())
        ).scalars().all()
    )


DEFAULT_WARMUP_DAYS = 60  # matches tests/fixtures/predictions/synthetic_training_dataset.py's own default
DEFAULT_CADENCE_DAYS = 15


def build_training_examples_for_dataset_version(
    db: Session,
    dataset_version: DatasetVersion,
    *,
    cadence_days: int = DEFAULT_CADENCE_DAYS,
    warmup_days: int = DEFAULT_WARMUP_DAYS,
):
    """Reconstructs the `(site_ids, as_of_dates)` a `DatasetVersion`
    implies — every one of the organization's own sites, and a
    deterministic, evenly-spaced series of `as_of` dates spanning the
    dataset's own date range (mirroring
    `tests/fixtures/predictions/synthetic_training_dataset.py::as_of_dates()`'s
    shape) — and calls `app/predictions/dataset.py::build_training_examples()`.
    `warmup_days` is skipped at the start so every `as_of` has that much
    historical data to build a feature snapshot from, and `horizon_days`
    is reserved at the end so every `as_of`'s label window resolves
    within the dataset's own recorded span."""
    site_ids = [
        row[0]
        for row in db.execute(select(Site.id).where(Site.organization_id == dataset_version.organization_id)).all()
    ]

    start = datetime.combine(dataset_version.date_range_start, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
        days=warmup_days
    )
    end = datetime.combine(dataset_version.date_range_end, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
        days=dataset_version.prediction_horizon_days
    )

    as_of_dates: list[datetime] = []
    current = start
    while current <= end:
        as_of_dates.append(current)
        current += timedelta(days=cadence_days)

    return build_training_examples(
        db, organization_id=dataset_version.organization_id, site_ids=site_ids, as_of_dates=as_of_dates,
        horizon_days=dataset_version.prediction_horizon_days,
    )


__all__ = [
    "build_training_examples_for_dataset_version",
    "get_dataset_version",
    "list_dataset_versions",
    "register_dataset",
    "register_real_dataset",
    "register_synthetic_dataset",
]
