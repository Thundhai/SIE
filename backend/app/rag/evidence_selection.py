"""EvidenceSelectionService — decides which retrieved chunks actually
reach the LLM prompt. Milestone item 5: *not every retrieved chunk is
automatically passed to the LLM.*

    RetrievalResponse.results (already tenant-filtered, already
    similarity-thresholded by RetrievalService)
        -> drop INSUFFICIENT-quality extractions
        -> drop LOW-relevance matches (not usable as grounding evidence,
           even though RetrievalService's own, looser, min-similarity
           floor let them through as *retrieved*)
        -> drop near-duplicate content
        -> prioritize VERIFIED sources (stable, doesn't discard others)
        -> cap at RAG_MAX_EVIDENCE_ITEMS
        -> cap at RAG_MAX_CONTEXT_CHARACTERS (drop whole items, never
           truncate one mid-content — a citation must always point at
           its item's *complete* content, never a silently-cut fragment)
        -> assign stable citation ids E1..En, in final order

Every step here only ever *removes* an item — nothing is rewritten,
summarized, or reranked by relevance-affecting means (no BM25, no
reranking model — see the README). `SelectedEvidenceItem` wraps the
original `RetrievalResult` unchanged, so every provenance/quality/
similarity field survives all the way to the final citation
(milestone item 5's "every piece of evidence included in the prompt must
remain traceable to the original chunk").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.retrieval.results import RelevanceLevel, RetrievalResult
from app.models.enums import QualityStatus
from app.models.enums import VerificationStatus
from app.rag.results import SelectedEvidenceItem

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalized_tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class EvidenceSelectionResult:
    selected: list[SelectedEvidenceItem] = field(default_factory=list)
    retrieved_count: int = 0
    excluded_insufficient_quality_count: int = 0
    excluded_low_relevance_count: int = 0
    excluded_duplicate_count: int = 0
    excluded_over_limit_count: int = 0

    @property
    def selected_count(self) -> int:
        return len(self.selected)


class EvidenceSelectionService:
    def select(
        self,
        results: list[RetrievalResult],
        *,
        max_items: int | None = None,
        max_context_characters: int | None = None,
        dedup_threshold: float | None = None,
    ) -> EvidenceSelectionResult:
        max_items = max_items if max_items is not None else settings.RAG_MAX_EVIDENCE_ITEMS
        max_context_characters = (
            max_context_characters
            if max_context_characters is not None
            else settings.RAG_MAX_CONTEXT_CHARACTERS
        )
        dedup_threshold = (
            dedup_threshold if dedup_threshold is not None else settings.RAG_DEDUP_SIMILARITY_THRESHOLD
        )

        selection = EvidenceSelectionResult(retrieved_count=len(results))

        # Already ranked by similarity descending (RetrievalService's own
        # ORDER BY) — every filter below is stable with respect to that
        # order unless explicitly re-sorted (the verified-priority step).
        candidates: list[RetrievalResult] = []
        for result in results:
            if result.extraction_quality == QualityStatus.INSUFFICIENT:
                selection.excluded_insufficient_quality_count += 1
                continue
            if result.relevance == RelevanceLevel.LOW:
                selection.excluded_low_relevance_count += 1
                continue
            candidates.append(result)

        candidates = self._deduplicate(candidates, dedup_threshold, selection)

        # Prioritize VERIFIED sources — a stable sort keyed on
        # verification status first, keeping the existing similarity
        # order within each tier. This never *discards* an unverified
        # result on its own (that only happens via the item-count/
        # character-budget caps below, same as any other candidate) — see
        # module docstring and the README's "Source authority" section.
        candidates.sort(key=lambda r: r.verification_status != VerificationStatus.VERIFIED)

        selected_results: list[RetrievalResult] = []
        running_characters = 0
        for result in candidates:
            if len(selected_results) >= max_items:
                selection.excluded_over_limit_count += 1
                continue
            if running_characters + len(result.content) > max_context_characters:
                selection.excluded_over_limit_count += 1
                continue
            selected_results.append(result)
            running_characters += len(result.content)

        selection.selected = [
            SelectedEvidenceItem(citation_id=f"E{index}", result=result)
            for index, result in enumerate(selected_results, start=1)
        ]
        return selection

    def _deduplicate(
        self,
        candidates: list[RetrievalResult],
        dedup_threshold: float,
        selection: EvidenceSelectionResult,
    ) -> list[RetrievalResult]:
        kept: list[RetrievalResult] = []
        kept_tokens: list[frozenset[str]] = []
        for result in candidates:
            tokens = _normalized_tokens(result.content)
            is_duplicate = any(_jaccard(tokens, other) >= dedup_threshold for other in kept_tokens)
            if is_duplicate:
                selection.excluded_duplicate_count += 1
                continue
            kept.append(result)
            kept_tokens.append(tokens)
        return kept


evidence_selection_service = EvidenceSelectionService()
