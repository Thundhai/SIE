"""Deterministic validation and normalization — milestone items 12/14.
Pure unit tests, no database.
"""

import uuid

from app.intelligence.normalization import (
    normalize_category,
    normalize_datetime,
    normalize_severity,
    normalize_status,
    normalize_units_hours,
)
from app.intelligence.validation import validate_and_normalize
from tests.intelligence_test_helpers import make_raw_payload

ORG_ID = uuid.uuid4()


# --- Normalization -----------------------------------------------------------------


def test_normalize_severity_recognizes_common_aliases():
    assert normalize_severity("minor") == "LOW"
    assert normalize_severity("Moderate") == "MEDIUM"
    assert normalize_severity("HIGH") == "HIGH"
    assert normalize_severity("fatal") == "CRITICAL"


def test_normalize_severity_returns_none_for_unrecognized_value():
    assert normalize_severity("banana") is None


def test_normalize_datetime_parses_iso8601_with_z_suffix():
    dt = normalize_datetime("2026-06-01T12:00:00Z")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 6 and dt.day == 1


def test_normalize_datetime_returns_none_for_garbage():
    assert normalize_datetime("not-a-date") is None


def test_normalize_category_trims_and_collapses_whitespace_without_rewriting_case():
    assert normalize_category("  North   Site  ") == "North Site"


def test_normalize_category_never_destroys_the_original_casing_or_spelling():
    assert normalize_category("ACME Industrial Pty Ltd") == "ACME Industrial Pty Ltd"


def test_normalize_status_uppercases_and_trims():
    assert normalize_status(" open ") == "OPEN"


def test_normalize_units_hours_rejects_negative_and_non_numeric():
    assert normalize_units_hours(100) == 100.0
    assert normalize_units_hours(-5) is None
    assert normalize_units_hours("not-a-number") is None


# --- Validation ----------------------------------------------------------------------


def test_missing_source_system_is_rejected_with_no_row_to_store():
    result, normalized = validate_and_normalize(
        make_raw_payload(source_system=None), organization_id=ORG_ID
    )
    assert result.status == "REJECTED"
    assert normalized is None
    assert any(i.code == "MISSING_SOURCE_SYSTEM" for i in result.issues)


def test_missing_source_record_id_is_rejected():
    result, normalized = validate_and_normalize(
        make_raw_payload(source_record_id=None), organization_id=ORG_ID
    )
    assert result.status == "REJECTED"
    assert normalized is None


def test_missing_event_type_is_rejected():
    result, normalized = validate_and_normalize(make_raw_payload(event_type=None), organization_id=ORG_ID)
    assert result.status == "REJECTED"
    assert normalized is None


def test_fully_valid_payload_is_valid():
    result, normalized = validate_and_normalize(make_raw_payload(), organization_id=ORG_ID)
    assert result.status == "VALID"
    assert result.issues == []
    assert normalized is not None
    assert normalized.event_type == "INCIDENT"
    assert normalized.organization_id == ORG_ID


def test_missing_event_time_is_quarantined_but_still_stored():
    result, normalized = validate_and_normalize(make_raw_payload(event_time=None), organization_id=ORG_ID)
    assert result.status == "QUARANTINED"
    assert normalized is not None  # still stored -- see module docstring
    assert any(i.code == "MISSING_EVENT_TIME" for i in result.issues)


def test_invalid_event_time_is_quarantined():
    result, normalized = validate_and_normalize(
        make_raw_payload(event_time="not-a-date"), organization_id=ORG_ID
    )
    assert result.status == "QUARANTINED"
    assert any(i.code == "INVALID_EVENT_TIME" for i in result.issues)


def test_impossible_date_far_future_is_quarantined():
    result, normalized = validate_and_normalize(
        make_raw_payload(event_time="4026-06-01T00:00:00Z"), organization_id=ORG_ID
    )
    assert result.status == "QUARANTINED"
    assert any(i.code == "IMPOSSIBLE_DATE" for i in result.issues)


def test_impossible_duration_period_end_before_event_time_is_quarantined():
    result, normalized = validate_and_normalize(
        make_raw_payload(event_time="2026-06-01T00:00:00Z", period_end="2026-05-01T00:00:00Z"),
        organization_id=ORG_ID,
    )
    assert result.status == "QUARANTINED"
    assert any(i.code == "IMPOSSIBLE_DURATION" for i in result.issues)


def test_invalid_severity_is_partial_not_quarantined():
    result, normalized = validate_and_normalize(
        make_raw_payload(severity="extremely bad"), organization_id=ORG_ID
    )
    assert result.status == "PARTIAL"
    assert any(i.code == "INVALID_SEVERITY" for i in result.issues)
    assert normalized.severity is None  # unrecognized -> not guessed


def test_unrecognized_event_type_is_partial_not_rejected():
    """The model must remain extensible (milestone item 5) -- an unknown
    domain is a degradation, never an outright rejection."""
    result, normalized = validate_and_normalize(
        make_raw_payload(event_type="SOMETHING_NEW"), organization_id=ORG_ID
    )
    assert result.status == "PARTIAL"
    assert normalized is not None
    assert normalized.event_type == "SOMETHING_NEW"


def test_malformed_source_record_id_too_long_is_rejected():
    result, normalized = validate_and_normalize(
        make_raw_payload(source_record_id="x" * 300), organization_id=ORG_ID
    )
    assert result.status == "REJECTED"
    assert any(i.code == "MALFORMED_SOURCE_RECORD_ID" for i in result.issues)


def test_source_value_preserves_the_original_raw_input_unchanged():
    """Milestone item 14: 'do not destroy source values.'"""
    result, normalized = validate_and_normalize(
        make_raw_payload(severity="extremely bad"), organization_id=ORG_ID
    )
    assert normalized.source_value["severity"] == "extremely bad"
    assert normalized.severity is None  # normalized value is separate from source_value
