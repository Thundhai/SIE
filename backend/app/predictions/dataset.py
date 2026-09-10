"""Training-example construction — milestone items 6-7. Combines a
point-in-time feature snapshot with a label computed independently from
*future* events, and nothing more.

    for each (site, as_of):
        feature_snapshot_service.get_or_build_feature_snapshot(as_of)  -- never sees the future
        labels.generate_label(as_of, horizon_days)                     -- never sees the past
        -> TrainingExample(feature_vector, label)

**Feature/label separation is non-negotiable (item 7).** This module
calls `get_or_build_feature_snapshot()` and `generate_label()`
independently, in either order (there is no shared state or intermediate
object passed between them), and never feeds `LabelResult.supporting_event_ids`
or `LabelResult.label` into `vectorize()`'s input. See
`tests/test_feature_label_separation.py` for the regression test this
gets: it proves that mutating/removing the *label* window's events never
changes the computed feature vector for the same `(site, as_of)`, and
vice versa.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.predictions.feature_snapshot_service import get_or_build_feature_snapshot
from app.predictions.labels import LabelResult, generate_label
from app.predictions.spec import HORIZON_DAYS, LABEL_DEFINITION_VERSION
from app.predictions.vectorization import VECTORIZATION_VERSION, vectorize


@dataclass
class TrainingExample:
    entity_type: str
    entity_id: uuid.UUID
    organization_id: uuid.UUID
    as_of: datetime
    feature_snapshot_id: uuid.UUID
    feature_vector: dict[str, float | None]
    feature_set_version: str
    data_quality: str  # snapshot-level rollup -- app/predictions/feature_snapshot_service.py
    label: int
    label_definition_version: str
    horizon_days: int
    # Evaluation/audit only -- see labels.py's own docstring. Never fed
    # back into `feature_vector` by anything in this module.
    supporting_event_ids: list[uuid.UUID]


def build_training_example(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    as_of: datetime,
    horizon_days: int | None = None,
    persist_snapshot: bool = True,
) -> TrainingExample:
    horizon_days = horizon_days if horizon_days is not None else HORIZON_DAYS

    snapshot = get_or_build_feature_snapshot(
        db, organization_id=organization_id, site_id=site_id, as_of=as_of, persist=persist_snapshot
    )
    label_result: LabelResult = generate_label(
        db, organization_id=organization_id, site_id=site_id, as_of=as_of, horizon_days=horizon_days
    )

    return TrainingExample(
        entity_type="site",
        entity_id=site_id,
        organization_id=organization_id,
        as_of=as_of,
        feature_snapshot_id=snapshot.id,
        feature_vector=vectorize(snapshot.features),
        feature_set_version=snapshot.feature_set_version,
        data_quality=snapshot.data_quality,
        label=label_result.label,
        label_definition_version=label_result.label_definition_version,
        horizon_days=horizon_days,
        supporting_event_ids=list(label_result.supporting_event_ids),
    )


def build_training_examples(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_ids: list[uuid.UUID],
    as_of_dates: list[datetime],
    horizon_days: int | None = None,
    persist_snapshots: bool = True,
) -> list[TrainingExample]:
    """One example per `(site, as_of)` pair. Order of iteration does not
    matter for correctness (each example is computed independently), but
    is deterministic (site-major, then as_of ascending) for reproducible
    dataset builds."""
    examples: list[TrainingExample] = []
    for site_id in site_ids:
        for as_of in sorted(as_of_dates):
            examples.append(
                build_training_example(
                    db,
                    organization_id=organization_id,
                    site_id=site_id,
                    as_of=as_of,
                    horizon_days=horizon_days,
                    persist_snapshot=persist_snapshots,
                )
            )
    return examples


__all__ = ["LABEL_DEFINITION_VERSION", "VECTORIZATION_VERSION", "TrainingExample", "build_training_example", "build_training_examples"]
