"""Citation extraction and validation — milestone items 12-13/33. Pure
unit tests, no database.
"""

from app.rag.citations import extract_citation_ids, validate_and_sanitize_citations


def test_extract_citation_ids_finds_every_marker_in_order_deduplicated():
    text = "Fall protection is required. [E1] See also [E3] and again [E1]."
    assert extract_citation_ids(text) == ["E1", "E3"]


def test_extract_citation_ids_returns_empty_list_when_none_present():
    assert extract_citation_ids("No citations here.") == []


def test_valid_citation_is_preserved_unchanged():
    text = "Fall protection is required. [E1]"
    sanitized, valid, invalid = validate_and_sanitize_citations(text, {"E1", "E2"})
    assert sanitized == text
    assert valid == ["E1"]
    assert invalid == []


def test_invalid_citation_is_stripped_and_flagged():
    """The milestone's own worked example: the model outputs [E999] and
    E999 does not exist among the supplied evidence."""
    text = "Fall protection is required. [E999]"
    sanitized, valid, invalid = validate_and_sanitize_citations(text, {"E1"})
    assert "[E999]" not in sanitized
    assert "citation removed" in sanitized.lower()
    assert valid == []
    assert invalid == ["E999"]


def test_a_mix_of_valid_and_invalid_citations_only_strips_the_invalid_one():
    text = "Point one. [E1] Point two, unsupported. [E999]"
    sanitized, valid, invalid = validate_and_sanitize_citations(text, {"E1"})
    assert "[E1]" in sanitized
    assert "[E999]" not in sanitized
    assert valid == ["E1"]
    assert invalid == ["E999"]


def test_the_final_sanitized_text_never_contains_an_id_outside_the_valid_set():
    text = "[E1] [E2] [E3]"
    sanitized, valid, invalid = validate_and_sanitize_citations(text, {"E2"})
    assert "[E1]" not in sanitized
    assert "[E3]" not in sanitized
    assert "[E2]" in sanitized
    assert valid == ["E2"]
    assert set(invalid) == {"E1", "E3"}


def test_no_citations_at_all_is_handled_safely():
    sanitized, valid, invalid = validate_and_sanitize_citations("No supported claim here.", {"E1"})
    assert sanitized == "No supported claim here."
    assert valid == []
    assert invalid == []
