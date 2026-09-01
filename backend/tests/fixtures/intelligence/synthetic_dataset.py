"""Synthetic safety-data evaluation dataset — milestone item 40.

Entirely synthetic and non-confidential: generic incidents, near misses,
observations, audits, inspections, corrective actions, training,
equipment, and workforce/exposure records across multiple sites,
contractors, activities, and dates. Every timestamp is expressed as an
offset from a caller-supplied `as_of` (never a fixed calendar date), so
the dataset — and every test built on it — stays correct regardless of
the wall-clock date the suite happens to run on, and so it can genuinely
exercise temporal-window/trend/anomaly logic relative to "now".

Six organization profiles, matching the milestone's own required list:

  * `trending_org` — increasing incident frequency, overdue corrective
    actions, training-compliance deterioration, and an equipment-failure
    cluster, all in the most recent 30 days versus a quieter baseline.
  * `sparse_data_org` — a handful of events; not enough for a confident
    signal or trend.
  * `stale_data_org` — all data is old; nothing within the freshness
    window.
  * `missing_exposure_org` — incidents exist, but no WORKFORCE/
    EXPOSURE_HOURS records at all.
  * `duplicate_records_org` — the same source record sent twice
    (identical content).
  * `malformed_records_org` — payloads missing required fields or
    carrying invalid values.

Each function returns `list[RawSafetyEventPayload]` — real payload
objects fed through the actual ingestion pipeline by
`tests/evaluation/intelligence_harness.py`, not pre-built `SafetyEvent`
rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.intelligence.schemas import RawSafetyEventPayload

SITES = ["North Yard", "South Yard", "Offshore Platform A"]
CONTRACTORS = ["Acme Rigging", "Bolt Contractors", "Internal Crew"]
ACTIVITIES = ["lifting", "welding", "confined_space_entry", "permit_to_work"]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def trending_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    events: list[RawSafetyEventPayload] = []

    # Increasing incident frequency: 1 incident 75-45 days ago, 3
    # incidents 45-15 days ago, 6 incidents in the most recent 15 days.
    incident_schedule = [(75, 1), (45, 3), (15, 6)]
    counter = 0
    for days_ago_start, count in incident_schedule:
        for i in range(count):
            counter += 1
            events.append(
                RawSafetyEventPayload(
                    event_type="INCIDENT",
                    event_subtype="injury",
                    event_time=_iso(as_of - timedelta(days=days_ago_start - i)),
                    site_id=None,
                    location=SITES[counter % len(SITES)],
                    contractor=CONTRACTORS[counter % len(CONTRACTORS)],
                    activity=ACTIVITIES[counter % len(ACTIVITIES)],
                    severity="medium",
                    potential_severity="high" if counter % 3 == 0 else "medium",
                    source_system="safelytic",
                    source_record_id=f"trending-incident-{counter}",
                )
            )

    # Overdue corrective actions: a growing backlog.
    for i in range(6):
        events.append(
            RawSafetyEventPayload(
                event_type="CORRECTIVE_ACTION",
                event_subtype="overdue_action",
                event_time=_iso(as_of - timedelta(days=10 - i)),
                status="OVERDUE" if i < 5 else "OPEN",
                source_system="safelytic",
                source_record_id=f"trending-action-{i}",
            )
        )
    # A quiet baseline of mostly-closed actions further back.
    for i in range(4):
        events.append(
            RawSafetyEventPayload(
                event_type="CORRECTIVE_ACTION",
                event_time=_iso(as_of - timedelta(days=60 - i)),
                status="CLOSED",
                source_system="safelytic",
                source_record_id=f"trending-action-baseline-{i}",
            )
        )

    # Training compliance deterioration: mostly completed a while back,
    # mostly overdue recently.
    for i in range(4):
        events.append(
            RawSafetyEventPayload(
                event_type="TRAINING",
                event_time=_iso(as_of - timedelta(days=60 - i)),
                status="COMPLETED",
                source_system="safelytic",
                source_record_id=f"trending-training-baseline-{i}",
            )
        )
    for i in range(6):
        events.append(
            RawSafetyEventPayload(
                event_type="TRAINING",
                event_time=_iso(as_of - timedelta(days=10 - i)),
                status="COMPLETED" if i < 1 else "OVERDUE",
                source_system="safelytic",
                source_record_id=f"trending-training-recent-{i}",
            )
        )

    # Equipment failure cluster: sparse baseline, a real cluster recently.
    events.append(
        RawSafetyEventPayload(
            event_type="EQUIPMENT", event_subtype="failure",
            event_time=_iso(as_of - timedelta(days=70)),
            source_system="safelytic", source_record_id="trending-equip-baseline-1",
        )
    )
    for i in range(5):
        events.append(
            RawSafetyEventPayload(
                event_type="EQUIPMENT", event_subtype="failure",
                event_time=_iso(as_of - timedelta(days=5 - i)),
                source_system="safelytic", source_record_id=f"trending-equip-failure-{i}",
            )
        )

    # Exposure hours, so rate-normalized indicators are computable.
    events.append(
        RawSafetyEventPayload(
            event_type="WORKFORCE", event_subtype="EXPOSURE_HOURS",
            event_time=_iso(as_of - timedelta(days=15)),
            period_end=_iso(as_of),
            attributes={"hours": 12000},
            source_system="safelytic", source_record_id="trending-exposure-1",
        )
    )

    # A few observations/audits/inspections for breadth (multiple domains).
    for i in range(3):
        events.append(
            RawSafetyEventPayload(
                event_type="OBSERVATION", event_subtype="unsafe_act",
                event_time=_iso(as_of - timedelta(days=8 - i)),
                source_system="safelytic", source_record_id=f"trending-obs-{i}",
            )
        )
    events.append(
        RawSafetyEventPayload(
            event_type="AUDIT", event_subtype="hse_audit",
            event_time=_iso(as_of - timedelta(days=20)),
            source_system="safelytic", source_record_id="trending-audit-1",
        )
    )
    events.append(
        RawSafetyEventPayload(
            event_type="INSPECTION", event_subtype="site_inspection",
            event_time=_iso(as_of - timedelta(days=5)),
            source_system="safelytic", source_record_id="trending-inspection-1",
        )
    )

    return events


def sparse_data_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    return [
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(as_of - timedelta(days=2)),
            severity="low", source_system="safelytic", source_record_id="sparse-1",
        ),
        RawSafetyEventPayload(
            event_type="NEAR_MISS", event_time=_iso(as_of - timedelta(days=1)),
            source_system="safelytic", source_record_id="sparse-2",
        ),
    ]


def stale_data_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    """Everything ingested (and having happened) well outside the
    default 7-day freshness window."""
    old = as_of - timedelta(days=90)
    return [
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(old), severity="medium",
            source_system="legacy-spreadsheet", source_record_id=f"stale-{i}",
        )
        for i in range(4)
    ]


def missing_exposure_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    return [
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(as_of - timedelta(days=i)),
            severity="low", source_system="safelytic", source_record_id=f"no-exposure-{i}",
        )
        for i in range(5)
    ]


def duplicate_records_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    """The identical source record, sent twice -- proves idempotent
    ingestion end to end (milestone item 11), not just at the unit level."""
    payload = RawSafetyEventPayload(
        event_type="INCIDENT", event_time=_iso(as_of - timedelta(days=1)), severity="medium",
        source_system="safelytic", source_record_id="duplicate-1",
    )
    return [payload, payload]


def malformed_records_org_events(as_of: datetime) -> list[RawSafetyEventPayload]:
    return [
        # Missing source_record_id -- must be rejected, no row stored.
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(as_of), source_system="safelytic", source_record_id=None,
        ),
        # Missing event_time -- quarantined, still stored.
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=None, source_system="safelytic", source_record_id="malformed-2",
        ),
        # Invalid severity -- partial, still stored and usable.
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(as_of), severity="super duper bad",
            source_system="safelytic", source_record_id="malformed-3",
        ),
        # A genuinely valid record alongside the bad ones.
        RawSafetyEventPayload(
            event_type="INCIDENT", event_time=_iso(as_of), severity="low",
            source_system="safelytic", source_record_id="malformed-4",
        ),
    ]


ALL_PROFILES = {
    "trending_org": trending_org_events,
    "sparse_data_org": sparse_data_org_events,
    "stale_data_org": stale_data_org_events,
    "missing_exposure_org": missing_exposure_org_events,
    "duplicate_records_org": duplicate_records_org_events,
    "malformed_records_org": malformed_records_org_events,
}
