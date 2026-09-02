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
           -> a hit: resolved, annotated as calibration-sourced (never
              silently indistinguishable from a static-table match — see
              `normalize()`'s own `_terminology_calibration` attributes
              note below)
           -> no hit: UNKNOWN/AMBIGUOUS exactly as before, quarantined,
              never guessed

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


class CalibratedTerminologyMappingAdapter:
    """`DataSourceAdapter`-conforming, same four methods as
    `TerminologyMappingAdapter` (which this intentionally does not
    subclass — its own `_mapped_payload_and_issues()` is private and
    reimplementing the calibration lookup inline here keeps this
    adapter's own resolution order — static table, then approved
    calibration decision, then quarantine — visible in one place rather
    than split across an override)."""

    source_system_name = "terminology-mapped-calibrated"

    def __init__(self, active_mappings: dict[tuple[str, str | None, str], str] | None = None):
        #: `{(domain, context, normalized_term): canonical_term}` for
        #: this organization+source_system's currently-APPROVED
        #: decisions only — see `build_active_mapping_index()`. An
        #: empty/omitted index makes this adapter behave *exactly* like
        #: the plain `TerminologyMappingAdapter` (no calibration
        #: decisions exist yet), never a behavior change by omission.
        self._active_mappings = active_mappings or {}

    def _resolve_event_type(self, raw_event_type: str | None) -> tuple[str | None, str | None, list[ValidationIssue]]:
        """Returns `(canonical_or_raw_value, calibration_source_term_if_used, issues)`."""
        result = map_event_type(raw_event_type)
        if result.outcome == MappingOutcome.MAPPED:
            return result.canonical_value, None, []

        normalized = _normalize_key(str(raw_event_type)) if raw_event_type else None
        approved = self._active_mappings.get((_EVENT_TYPE_DOMAIN, None, normalized)) if normalized else None
        if approved:
            return approved, raw_event_type, []

        code = "AMBIGUOUS_EVENT_TYPE_MAPPING" if result.outcome == MappingOutcome.AMBIGUOUS else "UNKNOWN_EVENT_TYPE_MAPPING"
        detail = (
            f"could be {', '.join(result.candidates)}" if result.outcome == MappingOutcome.AMBIGUOUS else "no known alias"
        )
        issue = ValidationIssue(
            code, f"event_type {raw_event_type!r} terminology mapping is unresolved ({detail}).", True
        )
        return raw_event_type, None, [issue]

    def _resolve_event_subtype(
        self, mapped_event_type: str | None, raw_event_subtype: str | None
    ) -> tuple[str | None, str | None, list[ValidationIssue]]:
        if mapped_event_type not in _SUBTYPE_ALIASES or not raw_event_subtype:
            return raw_event_subtype, None, []

        result = map_event_subtype(mapped_event_type, raw_event_subtype)
        if result.outcome == MappingOutcome.MAPPED:
            return result.canonical_value, None, []

        normalized = _normalize_key(str(raw_event_subtype))
        approved = self._active_mappings.get((_EVENT_SUBTYPE_DOMAIN, mapped_event_type, normalized))
        if approved:
            return approved, raw_event_subtype, []

        code = "AMBIGUOUS_SUBTYPE_MAPPING" if result.outcome == MappingOutcome.AMBIGUOUS else "UNKNOWN_SUBTYPE_MAPPING"
        issue = ValidationIssue(code, f"event_subtype {raw_event_subtype!r} terminology mapping is unresolved.", True)
        return raw_event_subtype, None, [issue]

    def _mapped_payload_and_issues(
        self, raw: RawSafetyEventPayload
    ) -> tuple[RawSafetyEventPayload, list[ValidationIssue], dict[str, str]]:
        mapped_type, calibration_type_source, type_issues = self._resolve_event_type(raw.event_type)
        mapped_subtype, calibration_subtype_source, subtype_issues = self._resolve_event_subtype(mapped_type, raw.event_subtype)

        calibration_info: dict[str, str] = {}
        if calibration_type_source is not None:
            calibration_info["event_type_resolved_via_calibration"] = calibration_type_source
        if calibration_subtype_source is not None:
            calibration_info["event_subtype_resolved_via_calibration"] = calibration_subtype_source

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
