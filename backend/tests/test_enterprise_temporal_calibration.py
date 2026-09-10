"""Enterprise temporal validation — Real-World Data Validation &
Intelligence Calibration v0.1, item 5.

`tests/test_temporal_leakage.py` already covers `events_as_of()`'s own
query-builder contract directly, against hand-seeded `SafetyEvent` rows
(the milestone's own worked example included). This file is additive,
never a repeat of that: every case here goes through the real, unmodified
`EnterpriseIngestionService` end to end — real validation, real
normalization, real version-aware upsert, real `ingestion_time` stamped
at real wall-clock "now" — to prove the guarantee holds for actual
ingested enterprise data, not just for rows a test constructed by hand.
Specifically: late-arriving events, corrected/versioned records, future
timestamps, duplicate timestamps, and out-of-order arrival (item 5's own
list), plus the milestone's own worked example run through the real
pipeline.

Runs against `db_session` (SQLite) — every assertion below checks row
*membership* (by id/count) in an `events_as_of()` result, never a raw
Python-side datetime comparison against a value read back from the
database (see `tests/evaluation/test_calibration_evaluation.py`'s own
docstring for why that particular comparison needs real PostgreSQL);
membership checks are exactly what `test_temporal_leakage.py` already
established works correctly against SQLite.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.enums import IngestionOutcome
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.temporal import events_as_of
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Enterprise Temporal Calibration Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _payload(**overrides) -> RawSafetyEventPayload:
    defaults = {
        "event_type": "INCIDENT", "event_time": "2026-01-10T09:00:00Z",
        "source_system": "legacy-ehs", "source_record_id": "ENT-001",
    }
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)


def _visible_ids(db_session, *, organization_id: uuid.UUID, as_of: datetime) -> set[uuid.UUID]:
    query = events_as_of(organization_id=organization_id, as_of=as_of)
    return {e.id for e in db_session.execute(query).scalars().all()}


# --- The milestone's own worked example, through real ingestion -----------------------------


def test_the_milestones_own_worked_example_through_real_enterprise_ingestion(db_session):
    """"if predicting risk for 2026-01-31, a feature must not include an
    incident whose event_time is 2026-01-10 but that was only reported
    into SIE on 2026-02-05" -- run through the real service, not
    hand-seeded, with `ingestion_time` genuinely stamped at real
    wall-clock "now" by `EnterpriseIngestionService`/
    `SafetyEventIngestionService` (never backdated by this test)."""
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(event_time="2026-01-10T09:00:00Z", source_record_id="LATE-001")],
    )
    event_id = result.records[0].canonical_event_id
    assert event_id is not None

    # A snapshot "as of 2026-01-31" -- before this real ingestion
    # happened -- must not see the event, precisely because it was not
    # yet knowable to the system at that historical moment.
    pre_ingestion_snapshot = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert event_id not in _visible_ids(db_session, organization_id=org_id, as_of=pre_ingestion_snapshot)

    # A snapshot taken now (after the real ingestion that just happened)
    # correctly sees it.
    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_id in _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)


# --- Late-arriving events, more generally -----------------------------------------------------


def test_a_late_arriving_batch_of_historical_incidents_is_invisible_to_any_as_of_before_real_ingestion(db_session):
    org_id = _make_org(db_session)
    payloads = [
        _payload(event_time=f"2025-{month:02d}-15T00:00:00Z", source_record_id=f"HIST-{month:02d}")
        for month in range(1, 7)
    ]
    result = enterprise_ingestion_service.ingest_batch(db_session, organization_id=org_id, source_id=None, payloads=payloads)
    event_ids = {r.canonical_event_id for r in result.records}
    assert len(event_ids) == 6

    # None of these six months of backfilled history existed, as far as
    # the system was concerned, at any point before this real ingestion
    # -- not even the most recent (June 2025) one.
    pre_ingestion = datetime(2025, 12, 31, tzinfo=timezone.utc)
    assert event_ids.isdisjoint(_visible_ids(db_session, organization_id=org_id, as_of=pre_ingestion))

    # All six are visible in a snapshot taken after real ingestion completed.
    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_ids <= _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)


# --- Corrected / versioned records ------------------------------------------------------------


def test_a_version_correction_updates_ingestion_time_so_the_original_is_not_retroactively_visible(db_session):
    """`SafetyEventIngestionService._apply()` updates the canonical row
    in place and re-stamps `ingestion_time` at real "now" on every
    accepted update -- including a version correction, not just the
    original create (see app/intelligence/ingestion_service.py). This is
    a real, documented characteristic of a single-physical-row upsert
    model, not a bug: it means a point-in-time snapshot at a moment
    between the original ingestion and a later correction can no longer,
    after that correction has happened, be reconstructed from this row --
    the row now only remembers its latest `ingestion_time`. Asserted
    directly here so a silent change to that behavior is caught."""
    org_id = _make_org(db_session)
    v1 = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="CORR-001", source_record_version="1", description="initial report")],
    )
    event_id = v1.records[0].canonical_event_id
    assert event_id is not None

    # Captured right after v1's own real ingestion, with a real (if tiny)
    # wall-clock gap before v2 -- so this snapshot genuinely falls between
    # the two ingestion moments, not after both of them.
    between_snapshot = datetime.now(timezone.utc)
    assert event_id in _visible_ids(db_session, organization_id=org_id, as_of=between_snapshot)
    time.sleep(0.05)

    v2 = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="CORR-001", source_record_version="2", description="corrected report")],
    )
    assert v2.records[0].outcome == IngestionOutcome.UPDATED.value
    assert v2.records[0].canonical_event_id == event_id  # same physical row, corrected in place

    event = db_session.get(SafetyEvent, event_id)
    assert event.description == "corrected report"
    assert event.source_record_version == "2"
    # The row's own ingestion_time now reflects the correction, not the
    # original create -- so the earlier "between" snapshot, re-evaluated
    # now, no longer sees this row as having been known at that moment.
    # (Checked as membership in an events_as_of() result, not as a raw
    # Python-side datetime comparison against a value read back from
    # SQLite -- see this module's own docstring.)
    assert event_id not in _visible_ids(db_session, organization_id=org_id, as_of=between_snapshot)

    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_id in _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)


def test_a_stale_out_of_order_version_arriving_after_a_newer_one_does_not_disturb_the_applied_state(db_session):
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="OOO-001", source_record_version="1", description="v1")],
    )
    v2 = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="OOO-001", source_record_version="2", description="v2")],
    )
    event_id = v2.records[0].canonical_event_id
    event_after_v2 = db_session.get(SafetyEvent, event_id)
    ingestion_time_after_v2 = event_after_v2.ingestion_time

    # v1 arrives late, out of order, after v2 has already been applied --
    # must be skipped, never silently reapplied over the newer content,
    # and must not disturb the already-correct row (including its own
    # ingestion_time, which stays at the v2 update, not bumped again).
    v1_late = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="OOO-001", source_record_version="1", description="v1 (late resend)")],
    )
    assert v1_late.records[0].outcome == IngestionOutcome.SKIPPED_STALE_VERSION.value

    event_after_late_v1 = db_session.get(SafetyEvent, event_id)
    assert event_after_late_v1.description == "v2"
    assert event_after_late_v1.ingestion_time == ingestion_time_after_v2


# --- Future timestamps --------------------------------------------------------------------------


def test_a_plausible_future_event_time_is_accepted_but_excluded_until_that_time_arrives(db_session):
    """A moderately-future `event_time` (e.g. a scheduled inspection or a
    permit's planned date) is accepted, not rejected -- only an
    implausibly-far-future date is (see app/intelligence/validation.py's
    own `_MAX_FUTURE_SKEW`). It must still be correctly excluded from any
    `as_of` snapshot before that future time, exactly like any other
    not-yet-current event."""
    org_id = _make_org(db_session)
    future_event_time = datetime.now(timezone.utc) + timedelta(days=30)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(
            event_type="INSPECTION", event_time=future_event_time.strftime(_ISO), source_record_id="FUTURE-001",
        )],
    )
    assert result.batch.rejected_records == 0
    assert result.batch.quarantined_records == 0
    event_id = result.records[0].canonical_event_id
    assert event_id is not None

    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_id not in _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)

    after_future_event = future_event_time + timedelta(days=1)
    assert event_id in _visible_ids(db_session, organization_id=org_id, as_of=after_future_event)


# --- Duplicate timestamps ------------------------------------------------------------------------


def test_distinct_records_sharing_an_identical_event_time_are_both_retained_and_both_visible(db_session):
    """Two genuinely distinct incidents that happen to share the exact
    same `event_time` (e.g. two separate reports both timestamped to the
    top of the hour) must never be conflated by identity/dedup logic --
    only `(source_system, source_record_id)` identity matters, never a
    shared timestamp."""
    org_id = _make_org(db_session)
    shared_time = "2026-03-01T08:00:00Z"
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[
            _payload(event_time=shared_time, source_record_id="DUPTIME-A", description="site A incident"),
            _payload(event_time=shared_time, source_record_id="DUPTIME-B", description="site B incident"),
        ],
    )
    event_ids = {r.canonical_event_id for r in result.records}
    assert len(event_ids) == 2  # two distinct canonical rows, not deduplicated by timestamp

    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_ids <= _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)


# --- Out-of-order arrival --------------------------------------------------------------------------


def test_a_batch_arriving_with_event_times_out_of_chronological_order_ingests_all_records_correctly(db_session):
    """Arrival order within a batch (or across batches) is never assumed
    to match `event_time` order -- a legacy system backfill routinely
    sends records in whatever order its own export happened to produce
    them."""
    org_id = _make_org(db_session)
    payloads = [
        _payload(event_time="2026-02-20T00:00:00Z", source_record_id="OOO-BATCH-3"),
        _payload(event_time="2026-01-05T00:00:00Z", source_record_id="OOO-BATCH-1"),
        _payload(event_time="2026-02-01T00:00:00Z", source_record_id="OOO-BATCH-2"),
    ]
    result = enterprise_ingestion_service.ingest_batch(db_session, organization_id=org_id, source_id=None, payloads=payloads)
    assert result.batch.accepted_records == 3
    event_ids = {r.canonical_event_id for r in result.records}
    assert len(event_ids) == 3

    now_snapshot = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert event_ids <= _visible_ids(db_session, organization_id=org_id, as_of=now_snapshot)

    # Each record's own event_time survived correctly regardless of its
    # position in the batch -- a sort/index bug in a naive "assume arrival
    # order == event_time order" implementation would misassign these.
    by_external_id = {r.external_record_id: db_session.get(SafetyEvent, r.canonical_event_id) for r in result.records}
    assert by_external_id["OOO-BATCH-1"].event_time.isoformat().startswith("2026-01-05")
    assert by_external_id["OOO-BATCH-2"].event_time.isoformat().startswith("2026-02-01")
    assert by_external_id["OOO-BATCH-3"].event_time.isoformat().startswith("2026-02-20")

    # A snapshot before this real ingestion excludes all three uniformly --
    # arrival order must never grant one record an earlier effective
    # ingestion_time than another sent alongside it in the same batch.
    pre_ingestion = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert event_ids.isdisjoint(_visible_ids(db_session, organization_id=org_id, as_of=pre_ingestion))
