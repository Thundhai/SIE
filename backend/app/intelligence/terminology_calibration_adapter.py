"""Calibration-aware terminology adapter — SIE Real Enterprise Terminology
& Ontology Calibration v0.1, item 11 ("re-evaluate after an approved
mapping exists") and item 16 ("wire approved mappings into ingestion,
never automatically apply to historical records").

    raw event_type/event_subtype term
        -> static alias table (terminology_mapping.py, UNCHANGED — tried FIRST, always)
        -> MAPPED: use it, exactly like TerminologyMappingAdapter always has
        -> UNKNOWN/AMBIGUOUS: consult the precomputed `active_mappings` index
           (an organization+source_system's currently-APPROVED decisions,
           built ONCE per batch by
           `terminology_calibration_service.build_active_mapping_index()`)
           -> a hit: resolved, annotated with the exact `ActiveMappingProvenance`
              that resolved it (never silently indistinguishable from a
              static-table match, and never just "calibration=true" — see
              `normalize()`'s own `_terminology_calibration` attributes
              note below)
           -> no hit: UNKNOWN/AMBIGUOUS exactly as before, quarantined,
              never guessed

**Exact provenance (corrective commit, audit item 1).** A calibration-
resolved event's `attributes["_terminology_calibration"]` records, per
domain resolved this way, the *exact* `TerminologyMappingDecision` that
did it: `decision_id`, `mapping_version`, `organization_id`,
`source_system`, `domain`, `context`, `source_term` (the decision's own
recorded term), `normalized_term`, `canonical_term`, and `raw_term` (the
actual value this specific payload sent — case/whitespace-equivalent to
`source_term` by construction of the `normalized_term` lookup, but kept
distinct since they need not be byte-identical). This is the one place
that chain is captured — `ActiveMappingProvenance` below, produced by
`terminology_calibration_service.build_active_mapping_index()`/
`get_active_mapping()` and carried through unchanged. Never a second
provenance system: this rides entirely on `SafetyEvent.attributes`, the
same existing JSON provenance surface `source_value`/`source_content_hash`/
`ingestion_batch_id` already use for "what happened to this record and
why" (see `app/models/safety_event.py`'s own docstring).

**Compound event_type+subtype targets (Implement Approved HSE Terminology
Decisions v0.1).** An `event_type`-domain decision may also carry a
`target_event_subtype` (see `ActiveMappingProvenance` below) for a source
system whose raw payload has no independent subtype field at all (e.g.
the real workbook's Incident sheet — see
`app/validation/real_dataset_loader.py`'s own documented finding). This
is never a second ontology or a guess: `target_event_subtype` must
already be a genuinely pre-existing SIE canonical value (validated by
`terminology_calibration_service._valid_compound_subtype_for()` before
the decision can become `APPROVED`), and is only ever consulted when the
payload's own raw `event_subtype` is empty — a real independent raw
subtype value always takes precedence and is resolved on its own terms.

**Never automatically applied to historical records.** This adapter only
ever sees the payloads a caller explicitly hands to `ingest_batch()`/
`ingest_event()` for a *new* ingestion call — it has no path back to
already-stored `SafetyEvent` rows. Retroactively fixing up previously
QUARANTINED records is a deliberately separate, explicit operation:
`app/services/terminology_reprocessing_service.py::reprocess_quarantined_records()`.

**Why a precomputed dict, not a live per-record query.** `DataSourceAdapter.validate()`/
`normalize()` (`app/intelligence/adapters.py`) take no `db` parameter —
by design, so every adapter stays a pure, DB-free transformation the
Protocol can call for any record without a session in scope. Consulting
the database once per *batch* (via `build_active_mapping_index()`) rather
than once per *record* is both the only Protocol-conformant option and
the same "resolve once per batch" pattern this codebase already uses
elsewhere (e.g. `real_dataset_evaluation.py`'s own site resolution)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.intelligence.schemas import (
    NormalizedSafetyEvent,
    RawSafetyEventPayload,
    ValidationIssue,
    ValidationResult,
)
from app.intelligence.terminology_mapping import (
    _SUBTYPE_ALIASES,
    MappingOutcome,
    _normalize_key,
    map_event_subtype,
    map_event_type,
)
from app.intelligence.validation import validate_and_normalize

#: Domain identifiers as stored on `TerminologyMappingDecision.domain` —
#: matching `app.models.terminology_mapping_decision`'s own vocabulary
#: without importing the ORM model into this pure-transformation module.
_EVENT_TYPE_DOMAIN = "event_type"
_EVENT_SUBTYPE_DOMAIN = "event_subtype"


@dataclass(frozen=True)
class ActiveMappingProvenance:
    """Exactly which `TerminologyMappingDecision` resolved a term —
    corrective-commit audit item 1's own required field list, verbatim.
    Produced by `terminology_calibration_service.build_active_mapping_index()`/
    `get_active_mapping()` from the real ORM row (never reconstructed or
    guessed here) and carried, unchanged, into a resolved event's own
    `attributes["_terminology_calibration"]` via `as_attributes()` below —
    the one place this chain is captured, riding on the existing
    `SafetyEvent.attributes` JSON provenance surface, not a second
    provenance system."""

    decision_id: uuid.UUID
    mapping_version: int
    organization_id: uuid.UUID
    source_system: str
    domain: str
    context: str | None
    source_term: str
    normalized_term: str
    canonical_term: str
    #: Real Enterprise Terminology Calibration — Implement Approved HSE
    #: Terminology Decisions v0.1. An `event_type`-domain decision may
    #: additionally carry a *compound* subtype target — the human
    #: reviewer's own decision that this raw term should classify as
    #: BOTH `event_type=canonical_term` AND `event_subtype=<this value>`
    #: — used when the source system provides no independent raw
    #: subtype value to resolve on its own (see
    #: `app/validation/real_dataset_loader.py`'s own documented finding
    #: that the real workbook's Incident sheet has no subtype-bearing
    #: column). `None` for an ordinary, non-compound decision — never
    #: set except by explicit reviewer intent recorded in the decision's
    #: own `provenance["target_event_subtype"]` at candidate-creation
    #: time (`TerminologyMappingDecision`'s own `provenance` JSON
    #: column — no new schema). Applied by
    #: `CalibratedTerminologyMappingAdapter._resolve_event_subtype()`
    #: ONLY when the payload's own raw `event_subtype` is empty — a
    #: genuine independent raw subtype value is always resolved on its
    #: own terms first and this is never consulted.
    target_event_subtype: str | None = None

    def as_attributes(self, *, raw_term: str) -> dict[str, Any]:
        """`raw_term` is the exact value *this* payload sent — kept
        distinct from `source_term` (the decision's own recorded term)
        since the two need only be `_normalize_key()`-equivalent, not
        byte-identical (e.g. differing case/whitespace)."""
        return {
            "decision_id": str(self.decision_id),
            "mapping_version": self.mapping_version,
            "organization_id": str(self.organization_id),
            "source_system": self.source_system,
            "domain": self.domain,
            "context": self.context,
            "source_term": self.source_term,
            "normalized_term": self.normalized_term,
            "canonical_term": self.canonical_term,
            "raw_term": raw_term,
        }


class CalibratedTerminologyMappingAdapter:
    """`DataSourceAdapter`-conforming, same four methods as
    `TerminologyMappingAdapter` (which this intentionally does not
    subclass — its own `_mapped_payload_and_issues()` is private and
    reimplementing the calibration lookup inline here keeps this
    adapter's own resolution order — static table, then approved
    calibration decision, then quarantine — visible in one place rather
    than split across an override)."""

    source_system_name = "terminology-mapped-calibrated"

    def __init__(self, active_mappings: dict[tuple[str, str | None, str], ActiveMappingProvenance] | None = None):
        #: `{(domain, context, normalized_term): ActiveMappingProvenance}`
        #: for this organization+source_system's currently-APPROVED
        #: decisions only — see `build_active_mapping_index()`. An
        #: empty/omitted index makes this adapter behave *exactly* like
        #: the plain `TerminologyMappingAdapter` (no calibration
        #: decisions exist yet), never a behavior change by omission.
        self._active_mappings = active_mappings or {}

    def _resolve_event_type(
        self, raw_event_type: str | None
    ) -> tuple[str | None, ActiveMappingProvenance | None, list[ValidationIssue]]:
        """Returns `(canonical_or_raw_value, provenance_if_calibration_resolved, issues)`."""
        result = map_event_type(raw_event_type)
        if result.outcome == MappingOutcome.MAPPED:
            return result.canonical_value, None, []

        normalized = _normalize_key(str(raw_event_type)) if raw_event_type else None
        provenance = self._active_mappings.get((_EVENT_TYPE_DOMAIN, None, normalized)) if normalized else None
        if provenance is not None:
            return provenance.canonical_term, provenance, []

        code = "AMBIGUOUS_EVENT_TYPE_MAPPING" if result.outcome == MappingOutcome.AMBIGUOUS else "UNKNOWN_EVENT_TYPE_MAPPING"
        detail = (
            f"could be {', '.join(result.candidates)}" if result.outcome == MappingOutcome.AMBIGUOUS else "no known alias"
        )
        issue = ValidationIssue(
            code, f"event_type {raw_event_type!r} terminology mapping is unresolved ({detail}).", True
        )
        return raw_event_type, None, [issue]

    def _resolve_event_subtype(
        self,
        mapped_event_type: str | None,
        raw_event_subtype: str | None,
        *,
        compound_provenance: ActiveMappingProvenance | None = None,
    ) -> tuple[str | None, ActiveMappingProvenance | None, list[ValidationIssue]]:
        if not raw_event_subtype:
            # No independent raw subtype value on this payload at all --
            # the one legitimate source left is a *compound* event_type
            # decision that itself declares a target_event_subtype (see
            # ActiveMappingProvenance.target_event_subtype's own
            # docstring). Never invented when no such decision exists;
            # `compound_provenance` is `None` for every ordinary payload
            # that simply has no subtype to give.
            if compound_provenance is not None and compound_provenance.target_event_subtype:
                return compound_provenance.target_event_subtype, compound_provenance, []
            return raw_event_subtype, None, []

        if mapped_event_type not in _SUBTYPE_ALIASES:
            return raw_event_subtype, None, []

        result = map_event_subtype(mapped_event_type, raw_event_subtype)
        if result.outcome == MappingOutcome.MAPPED:
            return result.canonical_value, None, []

        normalized = _normalize_key(str(raw_event_subtype))
        provenance = self._active_mappings.get((_EVENT_SUBTYPE_DOMAIN, mapped_event_type, normalized))
        if provenance is not None:
            return provenance.canonical_term, provenance, []

        code = "AMBIGUOUS_SUBTYPE_MAPPING" if result.outcome == MappingOutcome.AMBIGUOUS else "UNKNOWN_SUBTYPE_MAPPING"
        issue = ValidationIssue(code, f"event_subtype {raw_event_subtype!r} terminology mapping is unresolved.", True)
        return raw_event_subtype, None, [issue]

    def _mapped_payload_and_issues(
        self, raw: RawSafetyEventPayload
    ) -> tuple[RawSafetyEventPayload, list[ValidationIssue], dict[str, dict[str, Any]]]:
        mapped_type, type_provenance, type_issues = self._resolve_event_type(raw.event_type)
        mapped_subtype, subtype_provenance, subtype_issues = self._resolve_event_subtype(
            mapped_type, raw.event_subtype, compound_provenance=type_provenance
        )

        calibration_info: dict[str, dict[str, Any]] = {}
        if type_provenance is not None:
            calibration_info["event_type"] = type_provenance.as_attributes(raw_term=raw.event_type)
        if subtype_provenance is not None:
            if subtype_provenance is type_provenance:
                # Compound: the SAME event_type decision also supplied the
                # subtype (the payload had no independent raw subtype value
                # at all) -- record the exact decision/version that drove
                # it, same as any other calibration resolution, but with
                # the *applied* subtype value as canonical_term rather than
                # the type decision's own (which would be misleading here).
                calibration_info["event_subtype"] = {
                    **type_provenance.as_attributes(raw_term=raw.event_type),
                    "canonical_term": type_provenance.target_event_subtype,
                    "derived_from_compound_event_type_decision": True,
                }
            else:
                calibration_info["event_subtype"] = subtype_provenance.as_attributes(raw_term=raw.event_subtype)

        mapped = RawSafetyEventPayload(
            event_type=mapped_type,
            event_subtype=mapped_subtype,
            event_time=raw.event_time,
            period_end=raw.period_end,
            reported_time=raw.reported_time,
            site_id=raw.site_id,
            location=raw.location,
            project=raw.project,
            department=raw.department,
            contractor=raw.contractor,
            activity=raw.activity,
            severity=raw.severity,
            potential_severity=raw.potential_severity,
            status=raw.status,
            description=raw.description,
            attributes=raw.attributes,
            source_system=raw.source_system,
            source_record_id=raw.source_record_id,
            source_record_version=raw.source_record_version,
            correlation_id=raw.correlation_id,
            source_schema_version=raw.source_schema_version,
        )
        return mapped, type_issues + subtype_issues, calibration_info

    def validate(self, raw: RawSafetyEventPayload) -> ValidationResult:
        mapped, mapping_issues, _ = self._mapped_payload_and_issues(raw)
        result, _ = validate_and_normalize(mapped, organization_id=uuid.uuid4())
        all_issues = list(result.issues) + mapping_issues
        if result.status == "REJECTED":
            status = "REJECTED"
        elif any(i.blocking for i in mapping_issues):
            status = "QUARANTINED"
        else:
            status = result.status
        return ValidationResult(status=status, issues=all_issues)

    def normalize(
        self, raw: RawSafetyEventPayload, *, organization_id: uuid.UUID
    ) -> NormalizedSafetyEvent | None:
        mapped, _, calibration_info = self._mapped_payload_and_issues(raw)
        _, normalized = validate_and_normalize(mapped, organization_id=organization_id)
        if normalized is not None:
            # source_value keeps its codebase-wide meaning ("exactly as
            # received"), same as TerminologyMappingAdapter -- the raw
            # terms, never this adapter's resolution of them.
            normalized.source_value["event_type"] = raw.event_type
            normalized.source_value["event_subtype"] = raw.event_subtype
            if calibration_info:
                # Recorded on the canonical event's own attributes, not
                # source_value -- a note about *how this record was
                # classified*, not part of "what was received". Never
                # overwrites an existing attributes key a real payload
                # might have used for something else.
                normalized.attributes = {
                    **normalized.attributes,
                    "_terminology_calibration": calibration_info,
                }
        return normalized

    def transform(self, normalized: NormalizedSafetyEvent) -> NormalizedSafetyEvent:
        return normalized

    def ingest(self, db, *, organization_id: uuid.UUID, raw: RawSafetyEventPayload, batch_id: uuid.UUID):
        from app.intelligence.ingestion_service import safety_event_ingestion_service

        return safety_event_ingestion_service.ingest_event(
            db, organization_id=organization_id, payload=raw, adapter=self, batch_id=batch_id
        )


__all__ = ["CalibratedTerminologyMappingAdapter"]
