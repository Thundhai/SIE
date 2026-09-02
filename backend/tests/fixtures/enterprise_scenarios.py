"""Realistic enterprise data scenario framework — Real-World Data
Validation & Intelligence Calibration v0.1, items 2-3.

Mirrors `tests/fixtures/intelligence/synthetic_dataset.py`'s own
conventions exactly (relative day-offsets from a caller-supplied
`as_of`, never a fixed calendar date, so every scenario and every test
built on it stays correct regardless of the wall-clock date the suite
happens to run on) — extended here with realistic terminology across
all eight domains the milestone names, and five controlled
ground-truth scenarios where the *expected* directional outcome is
deliberately known in advance.

**Every generator takes a `seed: int` and uses only `random.Random(seed)`
— never the global `random` module, never wall-clock time, never any
other non-deterministic source — so the exact same dataset is produced
on every run (item 11/13's "reproducible" requirement).**

Every domain-record helper returns a `RawSafetyEventPayload` — the same
type real ingestion consumes — never a pre-built `SafetyEvent` row, so
every scenario genuinely exercises the real validate/normalize/upsert
pipeline when fed through `SafetyEventIngestionService`/
`EnterpriseIngestionService`, exactly like the existing intelligence
evaluation harness already does.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_mapping import (
    MAINTENANCE_STATUS_TARGET_FIELDS,
    TRAINING_STATUS_TARGET_FIELDS,
)

SITES = ["Riverside Plant", "North Terminal", "Offshore Platform B"]
DEPARTMENTS = ["Operations", "Maintenance", "Logistics", "Construction"]
CONTRACTORS = ["Meridian Rigging", "Coastal Electrical", "Internal Crew"]
ACTIVITIES = ["lifting", "welding", "confined_space_entry", "vehicle_operation", "housekeeping"]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _at(as_of: datetime, rng: random.Random, *, days_ago: int) -> datetime:
    """A timestamp `days_ago` days before `as_of`, jittered within that
    day by a deterministic (seeded) hour offset — realistic spread
    without losing reproducibility."""
    return as_of - timedelta(days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))


def _record_id(prefix: str, rng: random.Random) -> str:
    return f"{prefix}-{rng.randrange(10**8):08d}"


# --- Domain record builders (realistic subtype variety, item 2) --------------------------


def incident(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, severity: str = "LOW",
    potential_severity: str | None = None, source_record_id: str | None = None, site_id=None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="INCIDENT",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        severity=severity,
        potential_severity=potential_severity,
        site_id=site_id,
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        contractor=rng.choice(CONTRACTORS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} recorded during {rng.choice(ACTIVITIES)}.",
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("INC", rng),
    )


def near_miss(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, source_record_id: str | None = None,
    site_id=None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="NEAR_MISS",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        site_id=site_id,
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        contractor=rng.choice(CONTRACTORS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} near miss reported.",
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("NM", rng),
    )


def observation(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, source_record_id: str | None = None
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="OBSERVATION",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} observation logged.",
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("OBS", rng),
    )


def inspection(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, status: str = "COMPLETED",
    source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="INSPECTION",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        status=status,
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("INSP", rng),
    )


def audit(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, source_record_id: str | None = None
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="AUDIT",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        description=f"{subtype.replace('_', ' ').title()} raised during audit.",
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("AUD", rng),
    )


def permit(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, status: str = "CLOSED",
    source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="PERMIT",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        status=status,
        location=rng.choice(SITES),
        contractor=rng.choice(CONTRACTORS),
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("PTW", rng),
    )


def training(
    rng: random.Random, as_of: datetime, *, days_ago: int, canonical_status: str, source_record_id: str | None = None
) -> RawSafetyEventPayload:
    """`canonical_status` is one of `TRAINING_STATUS_TARGET_FIELDS`'
    own keys (`COMPLETED`/`OVERDUE`/`INCOMPLETE`/`EXPIRED_CERTIFICATION`/
    `COMPETENCY_GAP`) -- reuses the exact (event_subtype, status) mapping
    `app/intelligence/terminology_mapping.py` documents, rather than
    re-deciding which SafetyEvent column each status belongs on here."""
    subtype, status = TRAINING_STATUS_TARGET_FIELDS[canonical_status]
    return RawSafetyEventPayload(
        event_type="TRAINING",
        event_subtype=subtype,
        status=status,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        contractor=rng.choice(CONTRACTORS),
        department=rng.choice(DEPARTMENTS),
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("TRN", rng),
    )


def maintenance(
    rng: random.Random, as_of: datetime, *, days_ago: int, canonical_status: str, source_record_id: str | None = None
) -> RawSafetyEventPayload:
    """`canonical_status` is one of `MAINTENANCE_STATUS_TARGET_FIELDS`'
    own keys (`OVERDUE_PREVENTIVE_MAINTENANCE`/`EQUIPMENT_FAILURE`)."""
    subtype, status = MAINTENANCE_STATUS_TARGET_FIELDS[canonical_status]
    return RawSafetyEventPayload(
        event_type="EQUIPMENT",
        event_subtype=subtype,
        status=status,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        location=rng.choice(SITES),
        department="Maintenance",
        source_system="enterprise-scenario",
        source_record_id=source_record_id or _record_id("EQP", rng),
    )


# --- Ground-truth scenarios (item 3) ------------------------------------------------------


@dataclass
class ScenarioDataset:
    key: str
    name: str
    description: str
    label: str  # "PROTOTYPE / CONTROLLED-SCENARIO CALIBRATION ONLY" -- see module docstring
    events: list[RawSafetyEventPayload] = field(default_factory=list)


_LABEL = "Prototype / controlled-scenario calibration only — not a production benchmark."


def scenario_a_stable(as_of: datetime, seed: int = 1001) -> ScenarioDataset:
    """Stable / low concern: flat incident frequency, good inspection
    coverage, low repeat findings, high training completion, low
    maintenance backlog, across both the baseline and current 30-day
    windows."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    for period in range(4):  # 4 baseline-shaped periods, most recent last
        base_days = period * 30
        events.append(incident(rng, as_of, days_ago=base_days + 5, subtype="FIRST_AID_CASE"))
        for i in range(2):
            events.append(near_miss(rng, as_of, days_ago=base_days + 3 + i, subtype="DROPPED_OBJECT"))
        for i in range(2):
            events.append(observation(rng, as_of, days_ago=base_days + 7 + i, subtype="POSITIVE_OBSERVATION"))
        events.append(inspection(rng, as_of, days_ago=base_days + 10, subtype="SITE_INSPECTION", status="COMPLETED"))
        events.append(audit(rng, as_of, days_ago=base_days + 15, subtype="COMPLIANCE_FINDING"))
        for i in range(9):
            events.append(training(rng, as_of, days_ago=base_days + i, canonical_status="COMPLETED"))
        events.append(training(rng, as_of, days_ago=base_days, canonical_status="OVERDUE"))
        events.append(maintenance(rng, as_of, days_ago=base_days + 20, canonical_status="EQUIPMENT_FAILURE"))
    return ScenarioDataset(
        key="A", name="Stable / Low Concern", label=_LABEL, events=events,
        description="Flat incident frequency, good inspection coverage, low repeat findings, "
        "~90% training completion, low maintenance backlog across four consecutive 30-day periods.",
    )


def scenario_b_emerging_risk(as_of: datetime, seed: int = 1002) -> ScenarioDataset:
    """Emerging risk: leading indicators (near misses, unsafe
    observations, overdue training, overdue maintenance, repeat
    findings) deteriorate sharply in the current 30-day window against
    a quiet 90-day baseline; incident frequency (a lagging indicator)
    stays flat -- the scenario must never claim these factors *caused*
    an incident, since none occurs."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    for period in range(1, 4):  # three quiet baseline periods (90..30 days ago)
        base_days = period * 30
        events.append(incident(rng, as_of, days_ago=base_days + 5, subtype="FIRST_AID_CASE"))
        events.append(near_miss(rng, as_of, days_ago=base_days + 3, subtype="DROPPED_OBJECT"))
        events.append(observation(rng, as_of, days_ago=base_days + 7, subtype="UNSAFE_ACT"))
        events.append(inspection(rng, as_of, days_ago=base_days + 10, subtype="SITE_INSPECTION"))
        for i in range(8):
            events.append(training(rng, as_of, days_ago=base_days + i, canonical_status="COMPLETED"))
    # Current 30-day window: sharp deterioration in leading indicators only.
    events.append(incident(rng, as_of, days_ago=5, subtype="FIRST_AID_CASE"))  # lagging stays flat
    for i in range(10):
        events.append(near_miss(rng, as_of, days_ago=i, subtype="VEHICLE_NEAR_MISS"))
    for i in range(10):
        events.append(observation(rng, as_of, days_ago=i, subtype="UNSAFE_CONDITION"))
    for i in range(2):
        events.append(training(rng, as_of, days_ago=i, canonical_status="COMPLETED"))
    for i in range(9):
        events.append(training(rng, as_of, days_ago=i, canonical_status="OVERDUE"))
    for i in range(6):
        events.append(maintenance(rng, as_of, days_ago=i, canonical_status="OVERDUE_PREVENTIVE_MAINTENANCE"))
    for i in range(3):
        events.append(audit(rng, as_of, days_ago=i, subtype="REPEAT_FINDING"))
    return ScenarioDataset(
        key="B", name="Emerging Risk", label=_LABEL, events=events,
        description="Sharp increase in near misses, unsafe observations, overdue training, overdue "
        "maintenance, and repeat findings in the most recent 30 days against a quiet 90-day baseline; "
        "incident frequency itself stays flat -- leading indicators only, no claimed causation.",
    )


def scenario_c_lagging_increase(as_of: datetime, seed: int = 1003) -> ScenarioDataset:
    """Lagging event increase: leading indicators are historically
    stable throughout; a sudden increase in *qualifying incidents*
    appears only in the current 30-day window, including several
    high-potential ones."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    for period in range(1, 5):  # four stable baseline periods (anomaly needs >= 4)
        base_days = period * 30
        events.append(incident(rng, as_of, days_ago=base_days + 5, subtype="FIRST_AID_CASE", severity="LOW"))
        events.append(near_miss(rng, as_of, days_ago=base_days + 3, subtype="DROPPED_OBJECT"))
        events.append(observation(rng, as_of, days_ago=base_days + 7, subtype="POSITIVE_OBSERVATION"))
        events.append(inspection(rng, as_of, days_ago=base_days + 10, subtype="SITE_INSPECTION"))
        for i in range(8):
            events.append(training(rng, as_of, days_ago=base_days + i, canonical_status="COMPLETED"))
    # Current window: leading indicators stay identical to baseline...
    events.append(near_miss(rng, as_of, days_ago=3, subtype="DROPPED_OBJECT"))
    events.append(observation(rng, as_of, days_ago=7, subtype="POSITIVE_OBSERVATION"))
    events.append(inspection(rng, as_of, days_ago=10, subtype="SITE_INSPECTION"))
    for i in range(8):
        events.append(training(rng, as_of, days_ago=i, canonical_status="COMPLETED"))
    # ...but a genuine incident cluster appears, several high-potential.
    for i in range(6):
        events.append(
            incident(
                rng, as_of, days_ago=i, subtype="LOST_TIME_INCIDENT", severity="HIGH",
                potential_severity="HIGH" if i % 2 == 0 else "CRITICAL",
            )
        )
    return ScenarioDataset(
        key="C", name="Lagging Event Increase", label=_LABEL, events=events,
        description="Leading indicators stay identical to a stable four-period baseline; a sudden "
        "cluster of six high-potential incidents appears only in the current 30-day window.",
    )


def scenario_d_data_quality_degradation(as_of: datetime, seed: int = 1004) -> ScenarioDataset:
    """Data quality degradation: missing event dates, invalid
    classifications, duplicate records, conflicting versions, and
    incomplete records -- deliberately mixed with some genuinely good
    records, so a quality benchmark has something to measure a
    degradation *against*."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    for i in range(6):
        events.append(incident(rng, as_of, days_ago=i, subtype="FIRST_AID_CASE"))
    for i in range(2):
        events.append(
            RawSafetyEventPayload(
                event_type="INCIDENT", event_time=None,  # missing event date -> QUARANTINED
                source_system="enterprise-scenario", source_record_id=_record_id("BAD-TIME", rng),
            )
        )
    for i in range(2):
        events.append(
            RawSafetyEventPayload(
                event_type="INCIDENT", event_time=_iso(_at(as_of, rng, days_ago=i)),
                severity="super-duper-bad",  # invalid/unrecognized classification -> PARTIAL
                source_system="enterprise-scenario", source_record_id=_record_id("BAD-SEV", rng),
            )
        )
    exact_dup = incident(rng, as_of, days_ago=2, subtype="FIRST_AID_CASE", source_record_id="DUP-0001")
    events.append(exact_dup)
    events.append(exact_dup)  # identical resend -> SKIPPED_IDEMPOTENT
    conflicting_first = RawSafetyEventPayload(
        event_type="INCIDENT", event_time=_iso(_at(as_of, rng, days_ago=1)),
        description="original account", source_record_version="1",
        source_system="enterprise-scenario", source_record_id="CONFLICT-0001",
    )
    conflicting_second = RawSafetyEventPayload(
        event_type="INCIDENT", event_time=_iso(_at(as_of, rng, days_ago=1)),
        description="a different, conflicting account under the same version", source_record_version="1",
        source_system="enterprise-scenario", source_record_id="CONFLICT-0001",
    )
    events.append(conflicting_first)
    events.append(conflicting_second)  # same version, different content -> REJECTED_VERSION_CONFLICT
    for i in range(2):
        events.append(
            RawSafetyEventPayload(
                event_type="INCIDENT", event_time=_iso(_at(as_of, rng, days_ago=i)),
                source_system="enterprise-scenario", source_record_id=None,  # incomplete -> REJECTED_INVALID
            )
        )
    return ScenarioDataset(
        key="D", name="Data Quality Degradation", label=_LABEL, events=events,
        description="Missing event dates, an invalid severity classification, an exact-duplicate "
        "resend, a same-version content conflict, and records missing their identifier, deliberately "
        "mixed with genuinely valid records.",
    )


def scenario_e_recovery(as_of: datetime, seed: int = 1005) -> ScenarioDataset:
    """Recovery: an earlier elevated period (near misses, poor training
    completion, high maintenance backlog, repeat findings) followed by
    genuine improvement in the most recent period -- indicators moving
    in the improving direction, never asserted as proof of actual
    safety improvement (see module docstring)."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    # Elevated period: ~90-60 days ago.
    for i in range(9):
        events.append(near_miss(rng, as_of, days_ago=70 + i, subtype="UNSAFE_ACT" if i % 2 else "DROPPED_OBJECT"))
    for i in range(8):
        events.append(training(rng, as_of, days_ago=70 + i, canonical_status="OVERDUE"))
    for i in range(6):
        events.append(maintenance(rng, as_of, days_ago=70 + i, canonical_status="OVERDUE_PREVENTIVE_MAINTENANCE"))
    for i in range(3):
        events.append(audit(rng, as_of, days_ago=70 + i, subtype="REPEAT_FINDING"))
    # Transitional/baseline-shaped period: ~60-30 days ago (still somewhat elevated).
    for i in range(4):
        events.append(near_miss(rng, as_of, days_ago=40 + i, subtype="DROPPED_OBJECT"))
    for i in range(3):
        events.append(training(rng, as_of, days_ago=40 + i, canonical_status="OVERDUE"))
    for i in range(5):
        events.append(training(rng, as_of, days_ago=40 + i, canonical_status="COMPLETED"))
    # Recent, recovered period: 0-30 days ago.
    for i in range(2):
        events.append(near_miss(rng, as_of, days_ago=i, subtype="DROPPED_OBJECT"))
    for i in range(9):
        events.append(training(rng, as_of, days_ago=i, canonical_status="COMPLETED"))
    events.append(training(rng, as_of, days_ago=0, canonical_status="OVERDUE"))
    events.append(maintenance(rng, as_of, days_ago=1, canonical_status="EQUIPMENT_FAILURE"))
    events.append(inspection(rng, as_of, days_ago=2, subtype="SITE_INSPECTION"))
    events.append(audit(rng, as_of, days_ago=3, subtype="COMPLIANCE_FINDING"))
    return ScenarioDataset(
        key="E", name="Recovery", label=_LABEL, events=events,
        description="An elevated period 60-90 days ago (frequent near misses, overdue training, "
        "high maintenance backlog, repeat findings) improving through a transitional period into a "
        "recovered most-recent 30 days.",
    )


ALL_SCENARIOS: dict[str, Callable[[datetime], ScenarioDataset]] = {
    "A": scenario_a_stable,
    "B": scenario_b_emerging_risk,
    "C": scenario_c_lagging_increase,
    "D": scenario_d_data_quality_degradation,
    "E": scenario_e_recovery,
}
