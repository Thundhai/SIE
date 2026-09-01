"""Evidence sufficiency — milestone item 6. Deterministic rule tests, no
database. See app/rag/sufficiency.py's own docstring for the exact rules
these exercise.
"""

from app.rag.results import EvidenceState
from app.rag.sufficiency import evaluate_sufficiency
from app.retrieval.results import RelevanceLevel
from tests.rag_test_helpers import make_selected_item


def test_zero_evidence_is_insufficient():
    assert evaluate_sufficiency([]) == EvidenceState.INSUFFICIENT


def test_one_high_relevance_item_alone_is_partial_not_sufficient():
    """Rule 2 requires *both* a HIGH item and the minimum count — a
    single HIGH item under the default minimum (2) is not enough on its
    own; that's the deliberate distinction between SUFFICIENT and
    PARTIAL, not a bug."""
    items = [make_selected_item("E1", relevance=RelevanceLevel.HIGH)]
    assert evaluate_sufficiency(items) == EvidenceState.PARTIAL


def test_one_high_and_one_moderate_item_is_sufficient_under_default_minimum():
    items = [
        make_selected_item("E1", relevance=RelevanceLevel.HIGH),
        make_selected_item("E2", relevance=RelevanceLevel.MODERATE),
    ]
    assert evaluate_sufficiency(items) == EvidenceState.SUFFICIENT


def test_two_high_relevance_items_is_sufficient():
    items = [
        make_selected_item("E1", relevance=RelevanceLevel.HIGH),
        make_selected_item("E2", relevance=RelevanceLevel.HIGH),
    ]
    assert evaluate_sufficiency(items) == EvidenceState.SUFFICIENT


def test_only_moderate_relevance_items_no_high_is_partial():
    items = [
        make_selected_item("E1", relevance=RelevanceLevel.MODERATE),
        make_selected_item("E2", relevance=RelevanceLevel.MODERATE),
    ]
    assert evaluate_sufficiency(items) == EvidenceState.PARTIAL


def test_min_evidence_count_is_configurable():
    items = [
        make_selected_item("E1", relevance=RelevanceLevel.HIGH),
        make_selected_item("E2", relevance=RelevanceLevel.MODERATE),
        make_selected_item("E3", relevance=RelevanceLevel.MODERATE),
    ]
    assert evaluate_sufficiency(items, min_evidence_count=3) == EvidenceState.SUFFICIENT
    assert evaluate_sufficiency(items, min_evidence_count=4) == EvidenceState.PARTIAL


def test_sufficiency_never_reads_a_confidence_attribute():
    """The evidence_state computation must be reproducible purely from
    `RelevanceLevel`/count -- never from anything resembling an
    LLM-provided confidence score (milestone item 6: 'do not call this
    AI confidence'). Checked structurally: `evaluate_sufficiency` never
    accesses a `.confidence` attribute on anything."""
    import inspect

    from app.rag.sufficiency import evaluate_sufficiency

    source = inspect.getsource(evaluate_sufficiency)
    assert ".confidence" not in source
