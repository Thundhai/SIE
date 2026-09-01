"""Evidence sufficiency — milestone item 6. Deterministic rules only; the
LLM is never asked whether its own evidence is sufficient (that would
make the model the judge of its own grounding, exactly what this
milestone's "the LLM is not the source of truth" principle forbids).

Operates on `EvidenceSelectionResult.selected` — i.e. evidence that has
*already* passed quality/relevance/deduplication filtering
(`app/rag/evidence_selection.py`). A LOW-relevance-only retrieval never
reaches this module with any candidates at all, since
`EvidenceSelectionService` drops LOW-relevance results outright; the "only
weak evidence available" case the milestone's own example describes is
therefore exactly the `selected_count == 0` rule below, not a separate
check.

**The exact rules** (never called "AI confidence" anywhere in this
codebase — see `app/retrieval/results.py::RelevanceLevel`'s own
docstring for why "confidence" is avoided throughout the retrieval layer
too):

  1. Zero selected evidence items -> `INSUFFICIENT`.
  2. At least one `HIGH`-relevance item, **and** at least
     `settings.RAG_SUFFICIENT_MIN_EVIDENCE_COUNT` items overall (HIGH or
     MODERATE — LOW is never present here, see above) -> `SUFFICIENT`.
  3. Anything else (some evidence exists, but rule 2's bar isn't met —
     e.g. only MODERATE-relevance items, or a single HIGH-relevance item
     alone) -> `PARTIAL`.
"""

from __future__ import annotations

from app.core.config import settings
from app.retrieval.results import RelevanceLevel
from app.rag.results import EvidenceState, SelectedEvidenceItem


def evaluate_sufficiency(
    selected: list[SelectedEvidenceItem],
    *,
    min_evidence_count: int | None = None,
) -> EvidenceState:
    min_evidence_count = (
        min_evidence_count
        if min_evidence_count is not None
        else settings.RAG_SUFFICIENT_MIN_EVIDENCE_COUNT
    )

    if not selected:
        return EvidenceState.INSUFFICIENT

    has_high_relevance = any(
        item.result.relevance == RelevanceLevel.HIGH for item in selected
    )
    if has_high_relevance and len(selected) >= min_evidence_count:
        return EvidenceState.SUFFICIENT

    return EvidenceState.PARTIAL
