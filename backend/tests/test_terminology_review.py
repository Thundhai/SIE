"""Unit tests for `app/intelligence/terminology_review.py` — Real
Enterprise Dataset Validation Foundation v0.1, item 3.

Pure functions over `RawSafetyEventPayload` lists, no database needed —
every assertion here can be checked against
`app/intelligence/terminology_mapping.py`'s own, unchanged alias tables
directly.
"""

from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_review import (
    TerminologyReviewStatus,
    TerminologyReviewSummary,
    build_terminology_review,
    extract_term_observations,
)


def _payload(**overrides) -> RawSafetyEventPayload:
    defaults = {"event_type": "INCIDENT", "event_time": "2026-01-01T00:00:00Z", "source_record_id": "REC-1"}
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)


def test_a_mapped_event_type_produces_a_mapped_entry_with_the_canonical_term():
    entries = build_terminology_review([_payload(event_type="Near Miss", source_record_id="A")])
    entry = next(e for e in entries if e.domain == "event_type")
    assert entry.status == TerminologyReviewStatus.MAPPED
    assert entry.proposed_canonical_term == "NEAR_MISS"
    assert not entry.requires_review
    assert "near miss" in entry.reason.lower()


def test_an_unknown_event_type_is_flagged_review_required_and_never_guessed():
    entries = build_terminology_review([_payload(event_type="Widget Malfunction", source_record_id="A")])
    entry = next(e for e in entries if e.domain == "event_type")
    assert entry.status == TerminologyReviewStatus.UNKNOWN
    assert entry.proposed_canonical_term is None
    assert entry.requires_review


def test_an_ambiguous_event_type_lists_every_candidate_and_never_picks_one():
    entries = build_terminology_review([_payload(event_type="finding", source_record_id="A")])
    entry = next(e for e in entries if e.domain == "event_type")
    assert entry.status == TerminologyReviewStatus.AMBIGUOUS
    assert entry.proposed_canonical_term is None
    assert "AUDIT" in entry.reason and "INSPECTION" in entry.reason
    assert entry.requires_review


def test_subtype_is_reviewed_under_its_own_mapped_event_type_as_context():
    entries = build_terminology_review(
        [_payload(event_type="Near Miss", event_subtype="Dropped Object", source_record_id="A")]
    )
    entry = next(e for e in entries if e.domain == "event_subtype")
    assert entry.context == "NEAR_MISS"
    assert entry.status == TerminologyReviewStatus.MAPPED
    assert entry.proposed_canonical_term == "DROPPED_OBJECT"


def test_subtype_cannot_be_resolved_when_its_own_event_type_is_unresolved():
    """No canonical event_type context -> no subtype table to check
    against -- the subtype is simply not walked at all (never a guess at
    which domain's subtype table might apply)."""
    entries = build_terminology_review(
        [_payload(event_type="Widget Malfunction", event_subtype="something", source_record_id="A")]
    )
    assert not any(e.domain == "event_subtype" for e in entries)


def test_training_status_is_reviewed_only_under_the_training_event_type():
    entries = build_terminology_review([_payload(event_type="Training", status="Past Due", source_record_id="A")])
    entry = next(e for e in entries if e.domain == "training_status")
    assert entry.context == "TRAINING"
    assert entry.proposed_canonical_term == "OVERDUE"


def test_maintenance_status_is_reviewed_only_under_the_equipment_event_type():
    entries = build_terminology_review([_payload(event_type="Equipment", status="Breakdown", source_record_id="A")])
    entry = next(e for e in entries if e.domain == "maintenance_status")
    assert entry.context == "EQUIPMENT"
    assert entry.proposed_canonical_term == "EQUIPMENT_FAILURE"


def test_status_is_not_reviewed_under_an_unrelated_event_type():
    entries = build_terminology_review([_payload(event_type="INCIDENT", status="OPEN", source_record_id="A")])
    assert not any(e.domain in ("training_status", "maintenance_status") for e in entries)


def test_occurrences_of_the_same_term_are_aggregated_with_a_correct_count_and_examples():
    payloads = [
        _payload(event_type="finding", source_record_id="A"),
        _payload(event_type="finding", source_record_id="B"),
        _payload(event_type="finding", source_record_id="C"),
    ]
    entries = build_terminology_review(payloads)
    entry = next(e for e in entries if e.domain == "event_type")
    assert entry.occurrence_count == 3
    assert set(entry.example_source_record_ids) == {"A", "B", "C"}


def test_distinct_terms_produce_distinct_entries_never_merged():
    payloads = [_payload(event_type="Near Miss", source_record_id="A"), _payload(event_type="NM", source_record_id="B")]
    entries = build_terminology_review(payloads)
    event_type_entries = [e for e in entries if e.domain == "event_type"]
    assert len(event_type_entries) == 2  # "Near Miss" and "NM" are distinct source terms
    assert {e.proposed_canonical_term for e in event_type_entries} == {"NEAR_MISS"}  # both resolve the same way


def test_missing_terms_are_not_observed_at_all():
    entries = extract_term_observations([_payload(event_type=None, source_record_id="A")])
    assert entries == []


def test_review_required_entries_sort_before_mapped_entries():
    payloads = [
        _payload(event_type="Near Miss", source_record_id="A"),
        _payload(event_type="Widget Malfunction", source_record_id="B"),
    ]
    entries = build_terminology_review(payloads)
    assert entries[0].requires_review  # UNKNOWN sorts first
    assert not entries[-1].requires_review  # MAPPED sorts last


def test_summary_rolls_up_entries_by_domain_and_status():
    payloads = [
        _payload(event_type="Near Miss", source_record_id="A"),
        _payload(event_type="finding", source_record_id="B"),
        _payload(event_type="Widget Malfunction", source_record_id="C"),
    ]
    summary = TerminologyReviewSummary.from_entries(build_terminology_review(payloads))
    assert summary.mapped_by_domain == {"event_type": 1}
    assert summary.ambiguous_by_domain == {"event_type": 1}
    assert summary.unknown_by_domain == {"event_type": 1}
    assert summary.review_required_total == 2
    assert summary.unique_terms_total == 3
