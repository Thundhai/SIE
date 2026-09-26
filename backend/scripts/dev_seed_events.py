"""Generic, deterministic `RawSafetyEventPayload` builders for local
development seeding — SIE Milestone UI-DEV-01, M43-IP-03 corrective fix.

WHY THIS MODULE EXISTS (M43-IP-03 corrective note)
-----------------------------------------------------
`scripts/seed_dev_environment.py` originally reused
`tests/fixtures/enterprise_scenarios.py::scenario_b_emerging_risk()` — a
curated dataset purpose-built to calibrate the (now-private) Intelligence
anomaly-detection engine (see docs/M43_IP_03_PUBLIC_EXTRACTION.md §4's
corrective note). M43-IP-03 deleted that test fixture along with the rest
of the intelligence-calibration test suite, which broke this dev script
(CI: `ModuleNotFoundError: No module named 'tests.fixtures.enterprise_scenarios'`)
without anyone noticing the *runtime* (non-test) dependency on it, exactly
like the `risk_area_ontology_seed.py`/migration-0017 case.

This module is deliberately **not** a restoration of `enterprise_scenarios.py`.
The domain-record *builder functions* below (`incident`, `near_miss`,
`observation`, `inspection`, `training`) are generic — they assemble a
`RawSafetyEventPayload` from a few random realistic-looking field choices,
with no scoring, no aliasing, no calibration logic — so they are safe to
keep in Public SIE. The *curated scenario datasets* (`scenario_a_stable`,
`scenario_b_emerging_risk`, etc.) are not reproduced here: their entire
purpose was demonstrating/calibrating the anomaly-detection engine that
M43-IP-03 extracted to the private Commercial Core repository, so keeping
them would mean maintaining demo data engineered for a feature this
repository can no longer compute (`GET /api/v1/intelligence/enterprise`
now returns 501 — see `app/integrations/commercial_core.py`). Recreating
that shape here, for a capability that no longer exists in this
repository, would itself be a kind of fake extraction. `training()`
below also does **not** import `TRAINING_STATUS_TARGET_FIELDS` from the
deleted `app/intelligence/terminology_mapping.py` (private terminology
alias-resolution module) — the tiny (subtype, status) pair it needs is
inlined directly, since the only proprietary part of that module was the
alias table, not this trivial schema fact.

Every generator takes a `seed: int` and uses only `random.Random(seed)` —
never the global `random` module, never wall-clock time — so the exact
same dataset is produced on every run.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.intelligence.schemas import RawSafetyEventPayload

SITES = ["Riverside Plant", "North Terminal", "Offshore Platform B"]
DEPARTMENTS = ["Operations", "Maintenance", "Logistics", "Construction"]
CONTRACTORS = ["Meridian Rigging", "Coastal Electrical", "Internal Crew"]
ACTIVITIES = ["lifting", "welding", "confined_space_entry", "vehicle_operation", "housekeeping"]

# The one trivial (subtype, status) fact `training()` needs -- inlined
# rather than imported from the deleted, private
# app/intelligence/terminology_mapping.py (see module docstring above).
_TRAINING_STATUS_TARGET_FIELDS: dict[str, tuple[str | None, str | None]] = {
    "COMPLETED": (None, "COMPLETED"),
    "OVERDUE": (None, "OVERDUE"),
}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _at(as_of: datetime, rng: random.Random, *, days_ago: int) -> datetime:
    """A timestamp `days_ago` days before `as_of`, jittered within that
    day by a deterministic (seeded) hour offset."""
    return as_of - timedelta(days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))


def _record_id(prefix: str, rng: random.Random) -> str:
    return f"{prefix}-{rng.randrange(10**8):08d}"


def incident(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, severity: str = "LOW",
    source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="INCIDENT",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        severity=severity,
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        contractor=rng.choice(CONTRACTORS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} recorded during {rng.choice(ACTIVITIES)}.",
        source_system="dev-seed",
        source_record_id=source_record_id or _record_id("INC", rng),
    )


def near_miss(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="NEAR_MISS",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        contractor=rng.choice(CONTRACTORS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} near miss reported.",
        source_system="dev-seed",
        source_record_id=source_record_id or _record_id("NM", rng),
    )


def observation(
    rng: random.Random, as_of: datetime, *, days_ago: int, subtype: str, source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    return RawSafetyEventPayload(
        event_type="OBSERVATION",
        event_subtype=subtype,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        location=rng.choice(SITES),
        department=rng.choice(DEPARTMENTS),
        activity=rng.choice(ACTIVITIES),
        description=f"{subtype.replace('_', ' ').title()} observation logged.",
        source_system="dev-seed",
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
        source_system="dev-seed",
        source_record_id=source_record_id or _record_id("INSP", rng),
    )


def training(
    rng: random.Random, as_of: datetime, *, days_ago: int, canonical_status: str, source_record_id: str | None = None,
) -> RawSafetyEventPayload:
    """`canonical_status` is `"COMPLETED"` or `"OVERDUE"` — see
    `_TRAINING_STATUS_TARGET_FIELDS` above."""
    subtype, status = _TRAINING_STATUS_TARGET_FIELDS[canonical_status]
    return RawSafetyEventPayload(
        event_type="TRAINING",
        event_subtype=subtype,
        status=status,
        event_time=_iso(_at(as_of, rng, days_ago=days_ago)),
        contractor=rng.choice(CONTRACTORS),
        department=rng.choice(DEPARTMENTS),
        source_system="dev-seed",
        source_record_id=source_record_id or _record_id("TRN", rng),
    )


def representative_demo_events(as_of: datetime, seed: int = 90031001) -> list[RawSafetyEventPayload]:
    """A small, realistic-looking spread of events over the last ~90
    days -- enough for a freshly seeded local database to show real,
    backend-computed ingestion results and a real risk assessment in the
    UI. Deliberately **not** engineered to trigger any particular
    Intelligence analytics status (trend/anomaly/concentration): that
    computation is Commercial Core-only in this repository now (see
    module docstring), so there is nothing here to calibrate against."""
    rng = random.Random(seed)
    events: list[RawSafetyEventPayload] = []
    for period in range(3):
        base_days = period * 30
        events.append(incident(rng, as_of, days_ago=base_days + 5, subtype="FIRST_AID_CASE"))
        events.append(near_miss(rng, as_of, days_ago=base_days + 3, subtype="DROPPED_OBJECT"))
        events.append(near_miss(rng, as_of, days_ago=base_days + 12, subtype="VEHICLE_INCIDENT"))
        events.append(observation(rng, as_of, days_ago=base_days + 7, subtype="UNSAFE_ACT"))
        events.append(observation(rng, as_of, days_ago=base_days + 18, subtype="POSITIVE_OBSERVATION"))
        events.append(inspection(rng, as_of, days_ago=base_days + 10, subtype="SITE_INSPECTION"))
        for i in range(4):
            events.append(training(rng, as_of, days_ago=base_days + i, canonical_status="COMPLETED"))
        events.append(training(rng, as_of, days_ago=base_days, canonical_status="OVERDUE"))
    return events
