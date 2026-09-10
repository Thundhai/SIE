"""Deterministic terminology review structure — Real Enterprise Dataset
Validation Foundation v0.1, item 3.

Builds a human-reviewable `SOURCE_TERM -> PROPOSED_CANONICAL_TERM ->
STATUS -> REASON` table over `app/intelligence/terminology_mapping.py`'s
existing, **unchanged** deterministic mapping functions. This module adds
no matching logic of its own — every resolution decision here is exactly
what `map_event_type()`/`map_event_subtype()`/`map_training_status()`/
`map_maintenance_status()` already compute; it only walks a batch of raw
payloads, calls those functions once per unique term, and renders the
result into a reviewable, deterministic structure. **No LLM, no fuzzy
matching, no probabilistic guessing** — unchanged from that module's own
governing rule.

Two status vocabularies, deliberately kept distinct:

* `MappingOutcome` (`terminology_mapping.py`, unchanged) — the raw,
  per-lookup result: `MAPPED` / `AMBIGUOUS` / `UNKNOWN`.
* `TerminologyReviewStatus` (this module) — the review table's own
  per-entry status, a superset used for the human-facing structure:
  `MAPPED`, `UNKNOWN`, `AMBIGUOUS` (the same three, carried straight
  through so a reviewer can see exactly what the mapping layer decided),
  plus `REVIEW_REQUIRED` — an additional, explicit flag set on *every*
  `UNKNOWN`/`AMBIGUOUS` entry (never on a `MAPPED` one) so a reviewer, or
  an automated report filter, can select "everything that needs a human"
  without having to know the underlying `MappingOutcome` vocabulary.
  `entry.status` always carries the precise outcome (`UNKNOWN` or
  `AMBIGUOUS`); `entry.requires_review` is the actionable boolean; the
  human-readable report (see `app/validation/report.py`) prints
  `REVIEW_REQUIRED` next to any such row for exactly that reason.

Unknown or ambiguous terminology is never guessed into a canonical
classification — it is surfaced, with a reason, for a human to decide.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_mapping import (
    _SUBTYPE_ALIASES,
    MappingOutcome,
    MappingResult,
    map_event_subtype,
    map_event_type,
    map_maintenance_status,
    map_training_status,
)

#: Event types whose `status` field is reviewed as a training status vs.
#: a maintenance status — exactly the two domains
#: `terminology_mapping.py` provides a status mapper for (item 4's own
#: scope). A canonical event_type outside this set has no reviewed
#: status vocabulary; its `status` field, if any, is not walked here —
#: not because it is unimportant, but because inventing a third,
#: unreviewed alias table for it would be new matching logic this module
#: deliberately does not add.
_TRAINING_EVENT_TYPE = "TRAINING"
_MAINTENANCE_EVENT_TYPE = "EQUIPMENT"


class TerminologyReviewStatus:
    MAPPED = "MAPPED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # see module docstring -- a flag, not a fifth MappingOutcome


_OUTCOME_TO_REVIEW_STATUS = {
    MappingOutcome.MAPPED: TerminologyReviewStatus.MAPPED,
    MappingOutcome.UNKNOWN: TerminologyReviewStatus.UNKNOWN,
    MappingOutcome.AMBIGUOUS: TerminologyReviewStatus.AMBIGUOUS,
}


@dataclass(frozen=True)
class TerminologyReviewEntry:
    """One row of the review table. `domain` is one of `event_type` /
    `event_subtype` / `training_status` / `maintenance_status`;
    `context` is the (already-mapped) canonical `event_type` a subtype or
    status was resolved under, `None` for `event_type` itself."""

    domain: str
    context: str | None
    source_term: str
    proposed_canonical_term: str | None
    status: str  # TerminologyReviewStatus
    reason: str
    occurrence_count: int
    example_source_record_ids: tuple[str, ...] = ()

    @property
    def requires_review(self) -> bool:
        return self.status in (TerminologyReviewStatus.UNKNOWN, TerminologyReviewStatus.AMBIGUOUS)


@dataclass
class _Observation:
    domain: str
    context: str | None
    source_term: str
    source_record_id: str | None


def _mapping_reason(result: MappingResult) -> str:
    if result.outcome == MappingOutcome.MAPPED:
        return f"Matched alias {result.matched_alias!r} -> {result.canonical_value}."
    if result.outcome == MappingOutcome.AMBIGUOUS:
        candidates = ", ".join(result.candidates)
        return f"Term matches multiple plausible candidates ({candidates}); not resolved automatically."
    return "No alias match found for this term in the existing mapping table."


def _observe(observations: list[_Observation], *, domain: str, context: str | None, raw_term, record_id) -> None:
    if raw_term is None or not str(raw_term).strip():
        return
    observations.append(
        _Observation(domain=domain, context=context, source_term=str(raw_term), source_record_id=record_id)
    )


def extract_term_observations(payloads: list[RawSafetyEventPayload]) -> list[_Observation]:
    """Walk raw payloads (before ingestion) and record every terminology
    occurrence this module knows how to review. Purely observational —
    makes no mapping decision itself, just enumerates what was actually
    sent, exactly as a human reviewer looking at the raw source data
    would see it."""
    observations: list[_Observation] = []
    for payload in payloads:
        record_id = payload.source_record_id
        _observe(observations, domain="event_type", context=None, raw_term=payload.event_type, record_id=record_id)

        event_type_result = map_event_type(payload.event_type)
        canonical_event_type = (
            event_type_result.canonical_value if event_type_result.outcome == MappingOutcome.MAPPED else None
        )
        if canonical_event_type is not None and canonical_event_type in _SUBTYPE_ALIASES:
            _observe(
                observations, domain="event_subtype", context=canonical_event_type,
                raw_term=payload.event_subtype, record_id=record_id,
            )

        if canonical_event_type == _TRAINING_EVENT_TYPE:
            _observe(
                observations, domain="training_status", context=canonical_event_type,
                raw_term=payload.status, record_id=record_id,
            )
        elif canonical_event_type == _MAINTENANCE_EVENT_TYPE:
            _observe(
                observations, domain="maintenance_status", context=canonical_event_type,
                raw_term=payload.status, record_id=record_id,
            )
    return observations


def _resolve(domain: str, context: str | None, source_term: str) -> MappingResult:
    if domain == "event_type":
        return map_event_type(source_term)
    if domain == "event_subtype":
        return map_event_subtype(context, source_term)
    if domain == "training_status":
        return map_training_status(source_term)
    if domain == "maintenance_status":
        return map_maintenance_status(source_term)
    raise ValueError(f"Unknown terminology review domain: {domain!r}")  # pragma: no cover -- exhaustive above


def build_terminology_review(payloads: list[RawSafetyEventPayload]) -> list[TerminologyReviewEntry]:
    """The full item-3 deterministic review structure for one batch of
    raw payloads: one `TerminologyReviewEntry` per unique
    `(domain, context, source_term)`, aggregated across the whole batch
    (`occurrence_count`), each carrying up to 5 example
    `source_record_id`s for traceability back to the records that used
    it. Sorted with `REVIEW_REQUIRED` entries first (highest occurrence
    count first within each group) so the entries most worth a human's
    time surface at the top."""
    observations = extract_term_observations(payloads)

    grouped: dict[tuple[str, str | None, str], list[_Observation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.domain, obs.context, obs.source_term)].append(obs)

    entries: list[TerminologyReviewEntry] = []
    for (domain, context, source_term), group in grouped.items():
        result = _resolve(domain, context, source_term)
        record_ids = tuple(sorted({o.source_record_id for o in group if o.source_record_id})[:5])
        entries.append(
            TerminologyReviewEntry(
                domain=domain,
                context=context,
                source_term=source_term,
                proposed_canonical_term=result.canonical_value,
                status=_OUTCOME_TO_REVIEW_STATUS[result.outcome],
                reason=_mapping_reason(result),
                occurrence_count=len(group),
                example_source_record_ids=record_ids,
            )
        )

    entries.sort(key=lambda e: (not e.requires_review, -e.occurrence_count, e.domain, e.source_term))
    return entries


@dataclass
class TerminologyReviewSummary:
    """The item-2 per-domain counters ("mapped event types, unknown event
    types, ambiguous event types, mapped subtypes, ...") derived from the
    same review entries — a plain rollup, not a second computation."""

    mapped_by_domain: dict[str, int] = field(default_factory=dict)
    unknown_by_domain: dict[str, int] = field(default_factory=dict)
    ambiguous_by_domain: dict[str, int] = field(default_factory=dict)
    review_required_total: int = 0
    unique_terms_total: int = 0

    @classmethod
    def from_entries(cls, entries: list[TerminologyReviewEntry]) -> TerminologyReviewSummary:
        mapped = Counter(e.domain for e in entries if e.status == TerminologyReviewStatus.MAPPED)
        unknown = Counter(e.domain for e in entries if e.status == TerminologyReviewStatus.UNKNOWN)
        ambiguous = Counter(e.domain for e in entries if e.status == TerminologyReviewStatus.AMBIGUOUS)
        return cls(
            mapped_by_domain=dict(mapped),
            unknown_by_domain=dict(unknown),
            ambiguous_by_domain=dict(ambiguous),
            review_required_total=sum(1 for e in entries if e.requires_review),
            unique_terms_total=len(entries),
        )
