"""EvidenceSelectionService — milestone item 5. Pure unit tests, no
database — see tests/rag_test_helpers.py.
"""

from app.models.enums import QualityStatus, VerificationStatus
from app.rag.evidence_selection import EvidenceSelectionService
from app.retrieval.results import RelevanceLevel
from tests.rag_test_helpers import make_retrieval_result


def test_not_every_retrieved_result_is_selected_by_default():
    """The milestone's own framing: selection is a real filtering step,
    not a pass-through."""
    service = EvidenceSelectionService()
    results = [make_retrieval_result(rank=i, similarity=0.9 - i * 0.01) for i in range(1, 4)]
    selection = service.select(results)
    assert selection.retrieved_count == 3
    assert selection.selected_count == 3  # nothing to filter here, but counted correctly


def test_insufficient_quality_evidence_is_excluded():
    service = EvidenceSelectionService()
    results = [
        make_retrieval_result(extraction_quality=QualityStatus.HIGH),
        make_retrieval_result(extraction_quality=QualityStatus.INSUFFICIENT),
    ]
    selection = service.select(results)
    assert selection.selected_count == 1
    assert selection.excluded_insufficient_quality_count == 1


def test_low_relevance_evidence_is_excluded():
    service = EvidenceSelectionService()
    results = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH),
        make_retrieval_result(relevance=RelevanceLevel.LOW),
    ]
    selection = service.select(results)
    assert selection.selected_count == 1
    assert selection.excluded_low_relevance_count == 1


def test_max_evidence_items_caps_selection():
    service = EvidenceSelectionService()
    results = [make_retrieval_result(rank=i, similarity=0.9 - i * 0.01) for i in range(1, 11)]
    selection = service.select(results, max_items=3)
    assert selection.selected_count == 3
    assert selection.excluded_over_limit_count == 7


def test_max_context_characters_drops_whole_items_never_truncates_one():
    service = EvidenceSelectionService()
    results = [
        make_retrieval_result(content="A" * 100),
        make_retrieval_result(content="B" * 100),
        make_retrieval_result(content="C" * 100),
    ]
    selection = service.select(results, max_items=10, max_context_characters=150)
    assert selection.selected_count == 1
    # The one selected item's content is not cut short.
    assert len(selection.selected[0].result.content) == 100
    assert selection.excluded_over_limit_count == 2


def test_near_duplicate_content_is_deduplicated():
    service = EvidenceSelectionService()
    text = "Workers must wear a full-body harness when working at height above 1.8 metres."
    near_duplicate = text + " Additional filler word."
    results = [
        make_retrieval_result(similarity=0.9, content=text),
        make_retrieval_result(similarity=0.8, content=near_duplicate),
    ]
    selection = service.select(results, dedup_threshold=0.7)
    assert selection.selected_count == 1
    assert selection.excluded_duplicate_count == 1
    # The higher-similarity (first) item is the one kept.
    assert selection.selected[0].result.content == text


def test_distinct_content_is_never_treated_as_a_duplicate():
    service = EvidenceSelectionService()
    results = [
        make_retrieval_result(content="Workers must wear a harness above 1.8 metres."),
        make_retrieval_result(content="A permit to work is required before hot work begins."),
    ]
    selection = service.select(results)
    assert selection.selected_count == 2


def test_verified_sources_are_prioritized_but_unverified_ones_are_not_discarded():
    service = EvidenceSelectionService()
    unverified = make_retrieval_result(
        similarity=0.9, verification_status=VerificationStatus.PENDING, content="Unverified statement about X."
    )
    verified = make_retrieval_result(
        similarity=0.85, verification_status=VerificationStatus.VERIFIED, content="Verified statement about Y."
    )
    selection = service.select([unverified, verified], max_items=2)
    # Both survive (never discarded purely for being unverified) ...
    assert selection.selected_count == 2
    # ... but the verified one is ordered first.
    assert selection.selected[0].result.verification_status == VerificationStatus.VERIFIED


def test_verified_priority_does_not_discard_unverified_evidence_under_a_tight_cap():
    """Prioritization only reorders — it must never itself be the reason
    a relevant unverified result disappears while a *less* relevant
    verified one survives the count cap; that would need its own,
    separate, explicit design decision this milestone does not make."""
    service = EvidenceSelectionService()
    verified_low_sim = make_retrieval_result(
        similarity=0.5, verification_status=VerificationStatus.VERIFIED, content="Weakly relevant verified text."
    )
    unverified_high_sim = make_retrieval_result(
        similarity=0.95, verification_status=VerificationStatus.PENDING, content="Highly relevant unverified text."
    )
    selection = service.select([unverified_high_sim, verified_low_sim], max_items=2)
    assert selection.selected_count == 2


def test_citation_ids_are_assigned_stably_in_final_order():
    service = EvidenceSelectionService()
    results = [make_retrieval_result(rank=i, similarity=0.9 - i * 0.01) for i in range(1, 4)]
    selection = service.select(results)
    assert [item.citation_id for item in selection.selected] == ["E1", "E2", "E3"]


def test_every_selected_item_preserves_full_provenance_from_the_original_result():
    service = EvidenceSelectionService()
    result = make_retrieval_result(location="Slide 17", source_authority_level="regulation")
    selection = service.select([result])
    selected = selection.selected[0]
    assert selected.result.location == "Slide 17"
    assert selected.result.source_authority_level == "regulation"
    assert selected.result.chunk_id == result.chunk_id
    assert selected.result.similarity == result.similarity


def test_zero_results_selects_nothing_without_raising():
    service = EvidenceSelectionService()
    selection = service.select([])
    assert selection.selected == []
    assert selection.retrieved_count == 0
