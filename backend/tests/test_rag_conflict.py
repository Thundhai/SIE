"""Source conflict detection — milestone items 15/36. Pure unit tests, no
database. See app/rag/conflict.py's own docstring for the exact heuristic
and its documented limitations.
"""

from app.rag.conflict import detect_conflicts
from tests.rag_test_helpers import make_selected_item


def test_the_milestones_own_worked_example_is_detected():
    """Source A: 'Hard hats are required.' Source B: 'Hard hats are not
    required.' -- milestone item 36's exact scenario."""
    items = [
        make_selected_item("E1", content="Hard hats are required.", source_name="Source A"),
        make_selected_item("E2", content="Hard hats are not required.", source_name="Source B"),
    ]
    conflicts = detect_conflicts(items)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert {conflict.citation_id_a, conflict.citation_id_b} == {"E1", "E2"}
    assert {conflict.source_name_a, conflict.source_name_b} == {"Source A", "Source B"}
    assert "Hard hats are required." in {conflict.statement_a, conflict.statement_b}
    assert "Hard hats are not required." in {conflict.statement_a, conflict.statement_b}


def test_two_requirement_statements_about_different_subjects_do_not_conflict():
    items = [
        make_selected_item("E1", content="Hard hats are required."),
        make_selected_item("E2", content="A permit to work is required before hot work."),
    ]
    assert detect_conflicts(items) == []


def test_two_statements_with_the_same_polarity_do_not_conflict():
    items = [
        make_selected_item("E1", content="Hard hats are required on site."),
        make_selected_item("E2", content="Hard hats are mandatory on site."),
    ]
    assert detect_conflicts(items) == []


def test_a_single_evidence_item_never_conflicts_with_itself():
    items = [make_selected_item("E1", content="Hard hats are required.")]
    assert detect_conflicts(items) == []


def test_non_requirement_statements_are_never_flagged():
    items = [
        make_selected_item("E1", content="The assembly point is near the north gate."),
        make_selected_item("E2", content="The assembly point is not near the north gate."),
    ]
    # Neither statement contains a requirement cue word (required/must/
    # shall/...), so the narrow heuristic does not fire -- see the
    # module's own documented scope.
    assert detect_conflicts(items) == []


def test_the_full_evaluation_corpus_produces_no_false_positive_conflicts():
    """Regression guard: the existing 28-chunk synthetic corpus
    (tests/fixtures/evaluation/corpus.py) must never trigger a spurious
    conflict just from this heuristic being added."""
    from tests.fixtures.evaluation.corpus import CORPUS

    items = [
        make_selected_item(f"E{i}", content=chunk.text) for i, chunk in enumerate(CORPUS, start=1)
    ]
    assert detect_conflicts(items) == []
