"""Deterministic label generation — milestone item 6.

    generate_label(organization_id, site_id, as_of, horizon_days)
        -> select only SafetyEvent rows strictly after as_of
        -> limited to the prediction horizon (item 3's exact semantics)
        -> determine whether a qualifying INCIDENT occurred (item 4)
        -> LabelResult(label, supporting_event_ids)

**Future target events may be used to create labels during training/
evaluation. They must NEVER be used as model features** — this module
does exactly one thing (produce a label from future events) and nothing
in `app/predictions/dataset.py` or `feature_snapshot_service.py` ever
calls it before building a feature snapshot, or feeds its
`supporting_event_ids` into any feature. See
`tests/test_feature_label_separation.py` for the explicit regression
test this separation gets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.safety_event import SafetyEvent
from app.predictions.spec import (
    HORIZON_DAYS,
    LABEL_DEFINITION_VERSION,
    PREDICTION_ENTITY_TYPE,
    QUALIFYING_DATA_QUALITY_STATUSES,
    QUALIFYING_EVENT_TYPE,
)


@dataclass
class LabelResult:
    entity_type: str
    entity_id: uuid.UUID
    as_of: datetime
    horizon_days: int
    horizon_start: datetime  # exclusive -- event_time > horizon_start
    horizon_end: datetime  # inclusive -- event_time <= horizon_end
    label: int  # 0 or 1
    label_definition_version: str
    # Evaluation/audit only -- see module docstring. Never a model input.
    supporting_event_ids: list[uuid.UUID] = field(default_factory=list)


def generate_label(
    db: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    as_of: datetime,
    horizon_days: int | None = None,
) -> LabelResult:
    horizon_days = horizon_days if horizon_days is not None else HORIZON_DAYS
    horizon_start = as_of
    horizon_end = as_of + timedelta(days=horizon_days)

    query = select(SafetyEvent).where(
        SafetyEvent.organization_id == organization_id,
        SafetyEvent.site_id == site_id,
        SafetyEvent.event_type == QUALIFYING_EVENT_TYPE,
        SafetyEvent.event_time > horizon_start,
        SafetyEvent.event_time <= horizon_end,
        SafetyEvent.data_quality_status.in_(QUALIFYING_DATA_QUALITY_STATUSES),
    )
    qualifying_events = db.execute(query).scalars().all()

    return LabelResult(
        entity_type=PREDICTION_ENTITY_TYPE,
        entity_id=site_id,
        as_of=as_of,
        horizon_days=horizon_days,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        label=1 if qualifying_events else 0,
        label_definition_version=LABEL_DEFINITION_VERSION,
        supporting_event_ids=[e.id for e in qualifying_events],
    )
