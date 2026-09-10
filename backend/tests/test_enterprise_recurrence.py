"""SIE Milestone 22: Enterprise Intelligence & Risk Analytics Foundation
v0.1, item 8 — `app/intelligence/recurrence.py`. Pure-function tests
(no database) against `tests.intelligence_test_helpers.make_safety_event`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.intelligence.recurrence import classify_recurrence, detect_recurrence
from tests.intelligence_test_helpers import make_safety_event

AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)
WINDOW_START = AS_OF - timedelta(days=30)
ORG_ID = uuid.uuid4()
SITE_A = uuid.uuid4()
SITE_B = uuid.uuid4()


def _events(count, *, site_id, event_type="INCIDENT", event_subtype=None, start_days_ago=1):
    return [
        make_safety_event(
            organization_id=ORG_ID,
            site_id=site_id,
            event_type=event_type,
            event_subtype=event_subtype,
            event_time=AS_OF - timedelta(days=start_days_ago + i),
        )
        for i in range(count)
    ]


def _detect(events):
    return detect_recurrence(events, window_start=WINDOW_START, window_end=AS_OF, window_days=30)


def test_classify_recurrence_boundaries():
    assert classify_recurrence(0).value == "NONE"
    assert classify_recurrence(1).value == "NONE"
    assert classify_recurrence(2).value == "WATCH"
    assert classify_recurrence(3).value == "RECURRING"
    assert classify_recurrence(4).value == "RECURRING"
    assert classify_recurrence(5).value == "HIGH_RECURRENCE"
    assert classify_recurrence(10).value == "HIGH_RECURRENCE"


def test_a_single_event_produces_no_pattern():
    events = _events(1, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    assert patterns == []


def test_two_events_reach_the_watch_threshold():
    events = _events(2, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.classification == "WATCH"
    assert subtype_pattern.count == 2


def test_three_events_reach_the_recurring_threshold():
    events = _events(3, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.classification == "RECURRING"


def test_five_events_reach_the_high_recurrence_threshold():
    events = _events(5, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.classification == "HIGH_RECURRENCE"


def test_separate_sites_do_not_combine():
    events = _events(1, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT", start_days_ago=1) + _events(
        1, site_id=SITE_B, event_subtype="VEHICLE_INCIDENT", start_days_ago=2
    )
    patterns = _detect(events)
    # Each site individually only has 1 vehicle incident -- below WATCH_MIN.
    assert patterns == []

    events_two_each = _events(2, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT", start_days_ago=1) + _events(
        2, site_id=SITE_B, event_subtype="VEHICLE_INCIDENT", start_days_ago=5
    )
    patterns_two_each = _detect(events_two_each)
    site_ids = {p.site_id for p in patterns_two_each if p.event_subtype == "VEHICLE_INCIDENT"}
    assert site_ids == {SITE_A, SITE_B}
    for p in patterns_two_each:
        if p.event_subtype == "VEHICLE_INCIDENT":
            assert p.count == 2  # never 4 -- sites never combine


def test_event_type_pattern_is_detected_separately_from_subtype_pattern():
    events = _events(2, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT") + _events(
        2, site_id=SITE_A, event_subtype="PROPERTY_DAMAGE", start_days_ago=10
    )
    patterns = _detect(events)
    type_pattern = next(p for p in patterns if p.event_subtype is None)
    assert type_pattern.event_type == "INCIDENT"
    assert type_pattern.count == 4  # all 4 INCIDENT events, regardless of subtype
    subtype_patterns = {p.event_subtype for p in patterns if p.event_subtype is not None}
    assert subtype_patterns == {"VEHICLE_INCIDENT", "PROPERTY_DAMAGE"}


def test_events_with_no_site_never_produce_a_pattern():
    events = _events(5, site_id=None, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    assert patterns == []


def test_non_adverse_event_types_are_excluded_from_recurrence_population():
    # AUDIT is not INCIDENT/NEAR_MISS -- never counted toward a pattern.
    events = _events(5, site_id=SITE_A, event_type="AUDIT", event_subtype="hse_audit")
    patterns = _detect(events)
    assert patterns == []


def test_supporting_event_ids_are_bounded():
    events = _events(30, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = _detect(events)
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.count == 30
    assert len(subtype_pattern.supporting_event_ids) <= 20


def test_first_seen_and_last_seen_reflect_the_actual_event_times():
    events = [
        make_safety_event(organization_id=ORG_ID, site_id=SITE_A, event_type="INCIDENT",
                           event_subtype="VEHICLE_INCIDENT", event_time=AS_OF - timedelta(days=20)),
        make_safety_event(organization_id=ORG_ID, site_id=SITE_A, event_type="INCIDENT",
                           event_subtype="VEHICLE_INCIDENT", event_time=AS_OF - timedelta(days=2)),
    ]
    patterns = _detect(events)
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.first_seen == AS_OF - timedelta(days=20)
    assert subtype_pattern.last_seen == AS_OF - timedelta(days=2)


def test_site_label_is_used_when_provided():
    events = _events(2, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    patterns = detect_recurrence(
        events, window_start=WINDOW_START, window_end=AS_OF, window_days=30, site_labels={SITE_A: "Site 04"}
    )
    subtype_pattern = next(p for p in patterns if p.event_subtype == "VEHICLE_INCIDENT")
    assert subtype_pattern.site_label == "Site 04"


# --- SIE Milestone 24: Enterprise Intelligence Pattern & Correlation
# Foundation v0.1, item 1's own instruction to build pattern detection on
# the existing recurrence infrastructure rather than replacing it -- the
# following two tests close item 17's "Patterns" test list (deterministic
# pattern key, period coverage), the two cases not already covered above
# by test_first_seen_and_last_seen_reflect_the_actual_event_times() and
# test_supporting_event_ids_are_bounded(). ------------------------------


def test_pattern_key_is_deterministic_and_reflects_site_type_and_subtype():
    events = _events(3, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT")
    first = _detect(events)
    second = _detect(events)
    type_pattern = next(p for p in first if p.event_subtype is None)
    subtype_pattern = next(p for p in first if p.event_subtype == "VEHICLE_INCIDENT")
    assert type_pattern.pattern_key == f"site:{SITE_A}|event_type:INCIDENT"
    assert subtype_pattern.pattern_key == f"site:{SITE_A}|event_type:INCIDENT|event_subtype:VEHICLE_INCIDENT"
    # Repeated detection over the same events produces the identical key.
    assert {p.pattern_key for p in first} == {p.pattern_key for p in second}


def test_period_coverage_distinguishes_spread_out_from_same_day_recurrence():
    """Milestone item 3's own worked example: a pattern occurring "8 times
    over 30 days" is materially different from "8 times on one day" --
    `first_seen`/`last_seen` (already exposed on every `RecurrencePattern`)
    give a caller everything needed to tell them apart, with no separate
    opaque "pattern score" required."""
    spread_out = _events(8, site_id=SITE_A, event_subtype="VEHICLE_INCIDENT", start_days_ago=1)
    same_day = [
        make_safety_event(
            organization_id=ORG_ID, site_id=SITE_B, event_type="INCIDENT", event_subtype="VEHICLE_INCIDENT",
            event_time=AS_OF - timedelta(hours=i),
        )
        for i in range(8)
    ]
    patterns = _detect(spread_out + same_day)
    spread_pattern = next(p for p in patterns if p.site_id == SITE_A and p.event_subtype == "VEHICLE_INCIDENT")
    same_day_pattern = next(p for p in patterns if p.site_id == SITE_B and p.event_subtype == "VEHICLE_INCIDENT")

    assert spread_pattern.count == same_day_pattern.count == 8
    assert (spread_pattern.last_seen - spread_pattern.first_seen).days >= 7
    assert (same_day_pattern.last_seen - same_day_pattern.first_seen).days == 0
