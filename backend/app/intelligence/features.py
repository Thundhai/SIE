"""Feature engineering foundation — milestone items 19-20.

    SafetyEvent rows (already point-in-time filtered — see
    app/intelligence/temporal.py) -> compute_feature_set() -> dict[name, FeatureValue]

`compute_feature_set()` is a pure function over an already-fetched event
list (plus an already-computed exposure figure) — no database access, no
`as_of` resolution of its own — so it is trivially unit-testable and so
the *only* place point-in-time correctness can be gotten wrong is
`app/intelligence/temporal.py::events_as_of()`, not scattered across
every feature. `FeatureEngineeringService.compute()` is the thin,
DB-touching wrapper the API layer actually calls.

Every `FeatureValue` records what the milestone spec asks for (item 19):
name, value, calculation window, as-of timestamp, source events,
calculation version, data quality — and, where relevant, the exposure
basis a rate was computed against. "Only calculate a feature when
sufficient data exists" (item 20's closing line) is implemented as: a
feature whose value depends on a denominator that doesn't exist (a rate
with nothing to divide by, an average with no values to average) reports
`value=None` and `unavailable_reason` rather than a misleading `0` or
`NaN`. A legitimately-zero *count* (zero incidents this window) is a
real, meaningful `0` — never turned into `None`.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.enums import DataSufficiency, SeverityLevel
from app.intelligence.exposure import compute_exposure_hours, normalize_rate_per_100k_hours
from app.intelligence.normalization import SEVERITY_ORDINAL
from app.intelligence.sufficiency import classify_data_sufficiency
from app.intelligence.temporal import events_as_of, utcnow, window_bounds
from app.models.safety_event import SafetyEvent

FEATURE_CALCULATION_VERSION = "feature-v1"
_MAX_SOURCE_EVENT_IDS = 50


@dataclass
class FeatureValue:
    name: str
    value: float | int | None
    window_days: int
    as_of: datetime
    entity_type: str
    entity_id: uuid.UUID | None
    source_event_ids: list[uuid.UUID]
    calculation_version: str
    data_quality: str
    exposure_basis: float | None = None
    unavailable_reason: str | None = None


def _feature(
    name: str,
    *,
    value,
    events: list[SafetyEvent],
    window_days: int,
    as_of: datetime,
    entity_type: str,
    entity_id: uuid.UUID | None,
    data_quality: DataSufficiency,
    exposure_basis: float | None = None,
    unavailable_reason: str | None = None,
) -> FeatureValue:
    return FeatureValue(
        name=name,
        value=value,
        window_days=window_days,
        as_of=as_of,
        entity_type=entity_type,
        entity_id=entity_id,
        source_event_ids=[e.id for e in events[:_MAX_SOURCE_EVENT_IDS]],
        calculation_version=FEATURE_CALCULATION_VERSION,
        data_quality=data_quality.value,
        exposure_basis=exposure_basis,
        unavailable_reason=unavailable_reason,
    )


def compute_feature_set(
    events: list[SafetyEvent],
    *,
    window_days: int,
    as_of: datetime,
    entity_type: str = "organization",
    entity_id: uuid.UUID | None = None,
    exposure_hours: float | None = None,
) -> dict[str, FeatureValue]:
    overall_quality = classify_data_sufficiency(len(events))

    def count_feature(name: str, subset: list[SafetyEvent]) -> FeatureValue:
        return _feature(
            name,
            value=len(subset),
            events=subset,
            window_days=window_days,
            as_of=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            data_quality=classify_data_sufficiency(len(events)),
        )

    by_type: dict[str, list[SafetyEvent]] = defaultdict(list)
    for event in events:
        by_type[event.event_type].append(event)

    incidents = by_type.get("INCIDENT", [])
    near_misses = by_type.get("NEAR_MISS", [])
    observations = by_type.get("OBSERVATION", [])
    audits = by_type.get("AUDIT", [])
    inspections = by_type.get("INSPECTION", [])
    actions = by_type.get("CORRECTIVE_ACTION", [])
    training = by_type.get("TRAINING", [])
    equipment = by_type.get("EQUIPMENT", [])

    features: dict[str, FeatureValue] = {
        "incident_count": count_feature("incident_count", incidents),
        "near_miss_count": count_feature("near_miss_count", near_misses),
        "observation_count": count_feature("observation_count", observations),
        "audit_count": count_feature("audit_count", audits),
        "inspection_count": count_feature("inspection_count", inspections),
    }

    # --- Severity -------------------------------------------------------
    severity_pool = incidents + near_misses
    scored = [e for e in severity_pool if e.severity in SEVERITY_ORDINAL]
    if scored:
        avg = sum(SEVERITY_ORDINAL[e.severity] for e in scored) / len(scored)
        features["avg_severity"] = _feature(
            "avg_severity", value=round(avg, 3), events=scored, window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=classify_data_sufficiency(len(scored)),
        )
    else:
        features["avg_severity"] = _feature(
            "avg_severity", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="NO_SEVERITY_DATA",
        )

    high_potential = [
        e for e in severity_pool if e.potential_severity in (SeverityLevel.HIGH.value, SeverityLevel.CRITICAL.value)
    ]
    features["high_potential_event_count"] = count_feature("high_potential_event_count", high_potential)

    severe = [e for e in severity_pool if e.severity in (SeverityLevel.HIGH.value, SeverityLevel.CRITICAL.value)]
    features["severe_event_count"] = count_feature("severe_event_count", severe)

    # --- Corrective actions ----------------------------------------------
    open_actions = [e for e in actions if e.status == "OPEN"]
    overdue_actions = [e for e in actions if e.status == "OVERDUE"]
    closed_actions = [e for e in actions if e.status == "CLOSED"]
    features["open_action_count"] = count_feature("open_action_count", open_actions)
    features["overdue_action_count"] = count_feature("overdue_action_count", overdue_actions)

    determinable_actions = open_actions + overdue_actions + closed_actions
    if determinable_actions:
        rate = len(closed_actions) / len(determinable_actions)
        features["action_closure_rate"] = _feature(
            "action_closure_rate", value=round(rate, 4), events=determinable_actions, window_days=window_days,
            as_of=as_of, entity_type=entity_type, entity_id=entity_id,
            data_quality=classify_data_sufficiency(len(determinable_actions)),
        )
    else:
        features["action_closure_rate"] = _feature(
            "action_closure_rate", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="NO_ACTION_STATUS_DATA",
        )

    recurring = [e for e in actions if e.event_subtype and "recurring" in e.event_subtype.lower()]
    features["recurring_action_count"] = count_feature("recurring_action_count", recurring)

    # --- Training ----------------------------------------------------------
    expired_certifications = [e for e in training if e.status == "EXPIRED"]
    completed_training = [e for e in training if e.status == "COMPLETED"]
    incomplete_training = [e for e in training if e.status in ("INCOMPLETE", "OVERDUE")]
    features["expired_certification_count"] = count_feature(
        "expired_certification_count", expired_certifications
    )

    determinable_training = completed_training + incomplete_training
    if determinable_training:
        rate = len(completed_training) / len(determinable_training)
        features["training_completion_rate"] = _feature(
            "training_completion_rate", value=round(rate, 4), events=determinable_training, window_days=window_days,
            as_of=as_of, entity_type=entity_type, entity_id=entity_id,
            data_quality=classify_data_sufficiency(len(determinable_training)),
        )
    else:
        features["training_completion_rate"] = _feature(
            "training_completion_rate", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="NO_TRAINING_STATUS_DATA",
        )

    competency_gaps = [e for e in training if e.event_subtype == "competency_gap"]
    features["competency_gap_count"] = count_feature("competency_gap_count", competency_gaps)

    # --- Equipment -----------------------------------------------------------
    overdue_equipment_inspections = [
        e for e in equipment if e.event_subtype == "inspection" and e.status == "OVERDUE"
    ]
    equipment_failures = [e for e in equipment if e.event_subtype == "failure"]
    maintenance_overdue = [e for e in equipment if e.event_subtype == "maintenance" and e.status == "OVERDUE"]
    features["overdue_equipment_inspection_count"] = count_feature(
        "overdue_equipment_inspection_count", overdue_equipment_inspections
    )
    features["equipment_failure_count"] = count_feature("equipment_failure_count", equipment_failures)
    features["maintenance_overdue_count"] = count_feature("maintenance_overdue_count", maintenance_overdue)

    # --- Operational context ---------------------------------------------
    contractors = {e.contractor for e in events if e.contractor}
    features["contractor_activity_count"] = _feature(
        "contractor_activity_count", value=len(contractors), events=[], window_days=window_days, as_of=as_of,
        entity_type=entity_type, entity_id=entity_id, data_quality=overall_quality,
    )
    activities = {e.activity for e in events if e.activity}
    features["activity_diversity"] = _feature(
        "activity_diversity", value=len(activities), events=[], window_days=window_days, as_of=as_of,
        entity_type=entity_type, entity_id=entity_id, data_quality=overall_quality,
    )
    location_counts = Counter(e.location for e in events if e.location)
    if location_counts and events:
        concentration = max(location_counts.values()) / len(events)
        features["location_concentration"] = _feature(
            "location_concentration", value=round(concentration, 4), events=[], window_days=window_days,
            as_of=as_of, entity_type=entity_type, entity_id=entity_id, data_quality=overall_quality,
        )
    else:
        features["location_concentration"] = _feature(
            "location_concentration", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="NO_LOCATION_DATA",
        )

    # --- Exposure-normalized (milestone item 18) --------------------------
    if exposure_hours is not None:
        features["exposure_hours"] = _feature(
            "exposure_hours", value=round(exposure_hours, 2), events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=overall_quality,
        )
        rate = normalize_rate_per_100k_hours(len(incidents), exposure_hours)
        features["incidents_per_100000_hours"] = _feature(
            "incidents_per_100000_hours",
            value=rate if isinstance(rate, (int, float)) else None,
            events=incidents,
            window_days=window_days,
            as_of=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            data_quality=classify_data_sufficiency(len(incidents)),
            exposure_basis=exposure_hours,
            unavailable_reason=None if isinstance(rate, (int, float)) else rate,
        )
    else:
        features["exposure_hours"] = _feature(
            "exposure_hours", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="EXPOSURE_DATA_UNAVAILABLE",
        )
        features["incidents_per_100000_hours"] = _feature(
            "incidents_per_100000_hours", value=None, events=[], window_days=window_days, as_of=as_of,
            entity_type=entity_type, entity_id=entity_id, data_quality=DataSufficiency.INSUFFICIENT_DATA,
            unavailable_reason="EXPOSURE_DATA_UNAVAILABLE",
        )

    return features


class FeatureEngineeringService:
    def compute(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        as_of: datetime | None = None,
        window_days: int | None = None,
        site_id: uuid.UUID | None = None,
        entity_type: str = "organization",
        entity_id: uuid.UUID | None = None,
    ) -> dict[str, FeatureValue]:
        as_of = as_of or utcnow()
        window_days = window_days or settings.INTELLIGENCE_DEFAULT_WINDOW_DAYS
        window_start, as_of = window_bounds(as_of, window_days)

        events = list(
            db.execute(
                events_as_of(organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id)
            )
            .scalars()
            .all()
        )
        exposure_hours = compute_exposure_hours(
            db, organization_id=organization_id, as_of=as_of, window_start=window_start, site_id=site_id
        )
        return compute_feature_set(
            events,
            window_days=window_days,
            as_of=as_of,
            entity_type=entity_type,
            entity_id=entity_id if entity_id is not None else site_id,
            exposure_hours=exposure_hours,
        )


feature_engineering_service = FeatureEngineeringService()
