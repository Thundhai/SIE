"""Citation extraction and validation — milestone items 12-13. The LLM is
never trusted to have only cited real evidence: every `[E#]` token in a
generated answer is checked against the actual evidence identifiers that
were supplied to it, deterministically, by this module — not by asking
the model to double-check itself.

    generated answer text -> extract [E#] tokens
        -> split into (valid, invalid) against the evidence actually supplied
        -> sanitize: every invalid token is replaced in the answer text,
           never left in place and never silently dropped without a trace
        -> RAGService adds one warning per invalid citation removed

A citation identifier is only ever `E` followed by digits (`E1`, `E12`,
...) — the exact, closed format `app/rag/evidence_selection.py` assigns.
Nothing else in the answer text is touched.
"""

from __future__ import annotations

import re

_CITATION_RE = re.compile(r"\[E(\d+)\]")
_INVALID_CITATION_PLACEHOLDER = "[citation removed: not found in supplied evidence]"


def extract_citation_ids(text: str) -> list[str]:
    """Every `E#` id referenced via a `[E#]` token in `text`, in the order
    first encountered, de-duplicated."""
    return list(dict.fromkeys(f"E{n}" for n in _CITATION_RE.findall(text)))


def validate_and_sanitize_citations(
    answer_text: str, valid_citation_ids: set[str]
) -> tuple[str, list[str], list[str]]:
    """Returns `(sanitized_text, valid_ids_used, invalid_ids_found)`.

    `sanitized_text` is `answer_text` with every citation token that is
    *not* in `valid_citation_ids` replaced by a clearly-labeled
    placeholder — the final response must never contain a fabricated
    evidence reference (milestone item 13), whether that reference points
    at nothing (`[E999]` when no E999 exists) or, in principle, at a real
    id the model was never actually given.
    """

    def _replace(match: re.Match) -> str:
        citation_id = f"E{match.group(1)}"
        if citation_id in valid_citation_ids:
            return match.group(0)
        return _INVALID_CITATION_PLACEHOLDER

    all_ids = extract_citation_ids(answer_text)
    valid_used = [c for c in all_ids if c in valid_citation_ids]
    invalid_found = [c for c in all_ids if c not in valid_citation_ids]
    sanitized = _CITATION_RE.sub(_replace, answer_text)
    return sanitized, valid_used, invalid_found
