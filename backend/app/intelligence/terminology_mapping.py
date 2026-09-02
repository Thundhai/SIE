"""Deterministic enterprise terminology mapping — Real-World Data
Validation & Intelligence Calibration v0.1, item 4.

Enterprise systems name the same underlying concept differently: one
source's `"Near Miss"` is another's `"NM"` or `"Potential Incident"`.
`app/intelligence/normalization.py` deliberately does **not** solve this
— `normalize_category()`'s own docstring is explicit that terminology
aliasing is "a data-quality/entity-resolution problem for a future
milestone, not something this function silently papers over," and
`validate_and_normalize()` only upper-cases `event_type` and checks it
against `SafetyEventType.__members__` (an unrecognized value is still
*stored*, verbatim, as a data-quality degradation — never rejected, but
never translated either).

This module is that "future milestone," addressing exactly one problem:
given a source system's own label for an event type, subtype, training
status, or maintenance status, either (a) confidently resolve it to
SIE's canonical vocabulary, or (b) say plainly that it could not, rather
than guessing. **No LLM, no fuzzy/similarity matching, no heuristic
scoring** — every lookup here is an exact match (after whitespace/case/
punctuation normalization) against a hand-curated, reviewable alias
table. An alias not in the table is `UNKNOWN`, not "probably this one";
a term registered as genuinely ambiguous (plausibly meaning more than
one canonical value, with no way to tell which from the term alone) is
`AMBIGUOUS`, listing every candidate rather than picking one.

**Deliberately additive, not wired into the default ingestion path.**
`GenericJSONAdapter` (`app/intelligence/adapters.py`) remains the
default, untouched, no-op-`transform()` adapter every existing test and
the production `/intelligence/events`/`/data/ingestion` endpoints use.
`TerminologyMappingAdapter` below is a second, opt-in adapter — exactly
the extension point `DataSourceAdapter.transform()`'s own docstring
describes ("a source-specific severity remap the generic normalizer
wouldn't know about... without any call site above it changing") — used
by this milestone's own evaluation harness to demonstrate the mapping
layer against realistic heterogeneous input, and available to a future
per-source-system adapter that wants deterministic terminology
resolution without writing its own alias table from scratch.

    raw "Near Miss" / "NM" / "Potential Incident" / "near-miss"
        -> _normalize_key() -> "near miss" / "nm" / "potential incident"
        -> map_event_type() -> MappingResult(MAPPED, canonical_value="NEAR_MISS")

    raw "finding" (used ambiguously by both audit and inspection systems)
        -> map_event_type() -> MappingResult(AMBIGUOUS, candidates=("AUDIT", "INSPECTION"))
        -> caller quarantines the record rather than guessing (see
           TerminologyMappingAdapter.validate() below)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum

from app.intelligence.enums import DataQualityStatus, SafetyEventType
from app.intelligence.schemas import (
    NormalizedSafetyEvent,
    RawSafetyEventPayload,
    ValidationIssue,
    ValidationResult,
)
from app.intelligence.validation import validate_and_normalize

_WHITESPACE_OR_SEPARATOR_RE = re.compile(r"[\s\-_/]+")


def _normalize_key(raw: str) -> str:
    """Case/whitespace/punctuation-insensitive lookup key — `"Near-Miss"`,
    `"near_miss"`, and `"  Near   Miss "` all normalize to `"near miss"`.
    Never applied to the value actually stored anywhere (`source_value`
    always preserves the caller's exact original text)."""
    return _WHITESPACE_OR_SEPARATOR_RE.sub(" ", raw.strip().lower()).strip()


class MappingOutcome(str, Enum):
    MAPPED = "MAPPED"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MappingResult:
    outcome: MappingOutcome
    canonical_value: str | None = None
    matched_alias: str | None = None
    candidates: tuple[str, ...] = ()


# --- event_type: broad-domain aliases -----------------------------------------------------

_EVENT_TYPE_ALIASES: dict[str, str] = {
    # INCIDENT
    "incident": SafetyEventType.INCIDENT.value,
    "safety incident": SafetyEventType.INCIDENT.value,
    "injury": SafetyEventType.INCIDENT.value,
    # NEAR_MISS
    "near miss": SafetyEventType.NEAR_MISS.value,
    "nm": SafetyEventType.NEAR_MISS.value,
    "potential incident": SafetyEventType.NEAR_MISS.value,
    "close call": SafetyEventType.NEAR_MISS.value,
    # OBSERVATION
    "observation": SafetyEventType.OBSERVATION.value,
    "obs": SafetyEventType.OBSERVATION.value,
    "safety observation": SafetyEventType.OBSERVATION.value,
    # INSPECTION
    "inspection": SafetyEventType.INSPECTION.value,
    "insp": SafetyEventType.INSPECTION.value,
    # AUDIT
    "audit": SafetyEventType.AUDIT.value,
    "compliance audit": SafetyEventType.AUDIT.value,
    # CORRECTIVE_ACTION
    "corrective action": SafetyEventType.CORRECTIVE_ACTION.value,
    "ca": SafetyEventType.CORRECTIVE_ACTION.value,
    "capa": SafetyEventType.CORRECTIVE_ACTION.value,
    # PERMIT
    "permit": SafetyEventType.PERMIT.value,
    "permit to work": SafetyEventType.PERMIT.value,
    "ptw": SafetyEventType.PERMIT.value,
    # TRAINING
    "training": SafetyEventType.TRAINING.value,
    "training record": SafetyEventType.TRAINING.value,
    # WORKFORCE
    "workforce": SafetyEventType.WORKFORCE.value,
    "exposure hours": SafetyEventType.WORKFORCE.value,
    # EQUIPMENT (also the domain "maintenance / operational signals" lands
    # in -- see module docstring and map_maintenance_status() below)
    "equipment": SafetyEventType.EQUIPMENT.value,
    "maintenance": SafetyEventType.EQUIPMENT.value,
    "asset": SafetyEventType.EQUIPMENT.value,
    # ENVIRONMENTAL
    "environmental": SafetyEventType.ENVIRONMENTAL.value,
    "environmental condition": SafetyEventType.ENVIRONMENTAL.value,
}

# Terms a real organization might plausibly use for more than one
# domain, with genuinely no way to disambiguate from the term alone --
# registered explicitly so a lookup never silently picks one.
_AMBIGUOUS_EVENT_TYPE_TERMS: dict[str, tuple[str, ...]] = {
    "finding": (SafetyEventType.AUDIT.value, SafetyEventType.INSPECTION.value),
    "event": (SafetyEventType.INCIDENT.value, SafetyEventType.NEAR_MISS.value, SafetyEventType.OBSERVATION.value),
    "report": (SafetyEventType.INCIDENT.value, SafetyEventType.OBSERVATION.value),
}


def map_event_type(raw: str | None) -> MappingResult:
    """Resolve a source system's own event-type label to a canonical
    `SafetyEventType` value, or say plainly that it could not."""
    if raw is None or not str(raw).strip():
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    key = _normalize_key(str(raw))
    if key in _AMBIGUOUS_EVENT_TYPE_TERMS:
        return MappingResult(outcome=MappingOutcome.AMBIGUOUS, candidates=_AMBIGUOUS_EVENT_TYPE_TERMS[key])
    canonical = _EVENT_TYPE_ALIASES.get(key)
    if canonical is None:
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    return MappingResult(outcome=MappingOutcome.MAPPED, canonical_value=canonical, matched_alias=key)


# --- event_subtype: per-domain aliases -----------------------------------------------------
# Keyed by the canonical event_type each subtype table applies under --
# the same raw string can mean different things in different domains
# (e.g. "compliance" under AUDIT vs. nothing under NEAR_MISS), so subtype
# resolution is never domain-agnostic.

_SUBTYPE_ALIASES: dict[str, dict[str, str]] = {
    SafetyEventType.INCIDENT.value: {
        "first aid case": "FIRST_AID_CASE",
        "fac": "FIRST_AID_CASE",
        "first aid": "FIRST_AID_CASE",
        "medical treatment case": "MEDICAL_TREATMENT_CASE",
        "mtc": "MEDICAL_TREATMENT_CASE",
        "lost time incident": "LOST_TIME_INCIDENT",
        "lti": "LOST_TIME_INCIDENT",
        "lost time injury": "LOST_TIME_INCIDENT",
        "vehicle incident": "VEHICLE_INCIDENT",
        "mva": "VEHICLE_INCIDENT",
        "vehicle accident": "VEHICLE_INCIDENT",
        "property damage": "PROPERTY_DAMAGE",
        "environmental event": "ENVIRONMENTAL_EVENT",
        "spill": "ENVIRONMENTAL_EVENT",
    },
    SafetyEventType.NEAR_MISS.value: {
        "dropped object": "DROPPED_OBJECT",
        "vehicle near miss": "VEHICLE_NEAR_MISS",
        "fall from height near miss": "FALL_FROM_HEIGHT_NEAR_MISS",
        "fall from height": "FALL_FROM_HEIGHT_NEAR_MISS",
        "process deviation": "PROCESS_DEVIATION",
    },
    SafetyEventType.OBSERVATION.value: {
        "unsafe act": "UNSAFE_ACT",
        "unsafe condition": "UNSAFE_CONDITION",
        "positive observation": "POSITIVE_OBSERVATION",
        "positive obs": "POSITIVE_OBSERVATION",
        "housekeeping deficiency": "HOUSEKEEPING_DEFICIENCY",
        "housekeeping": "HOUSEKEEPING_DEFICIENCY",
        "ppe issue": "PPE_ISSUE",
        "ppe non compliance": "PPE_ISSUE",
    },
    SafetyEventType.INSPECTION.value: {
        "equipment inspection": "EQUIPMENT_INSPECTION",
        "site inspection": "SITE_INSPECTION",
        "safety inspection": "SAFETY_INSPECTION",
        "environmental inspection": "ENVIRONMENTAL_INSPECTION",
    },
    SafetyEventType.AUDIT.value: {
        "compliance finding": "COMPLIANCE_FINDING",
        "management system finding": "MANAGEMENT_SYSTEM_FINDING",
        "repeat finding": "REPEAT_FINDING",
        "recurring finding": "REPEAT_FINDING",
    },
    SafetyEventType.PERMIT.value: {
        "hot work": "HOT_WORK",
        "confined space": "CONFINED_SPACE",
        "work at height": "WORK_AT_HEIGHT",
        "lifting operation": "LIFTING_OPERATION",
        "lifting": "LIFTING_OPERATION",
    },
}

# A short form a real source might send that's ambiguous *within* one
# domain's own subtype vocabulary -- e.g. "damage" under INCIDENT could
# plausibly mean PROPERTY_DAMAGE or (loosely) VEHICLE_INCIDENT.
_AMBIGUOUS_SUBTYPE_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    SafetyEventType.INCIDENT.value: {
        "damage": ("PROPERTY_DAMAGE", "VEHICLE_INCIDENT"),
    },
    SafetyEventType.OBSERVATION.value: {
        "safety issue": ("UNSAFE_ACT", "UNSAFE_CONDITION"),
    },
}


def map_event_subtype(canonical_event_type: str, raw: str | None) -> MappingResult:
    """Resolve a source system's own subtype label to SIE's canonical
    subtype for `canonical_event_type` (already-mapped, e.g. from
    `map_event_type()`). Domains with no curated subtype table
    (WORKFORCE, EQUIPMENT — see `map_maintenance_status()` instead,
    TRAINING — see `map_training_status()` instead, ENVIRONMENTAL,
    CORRECTIVE_ACTION) always return `UNKNOWN` here, not a guess."""
    if raw is None or not str(raw).strip():
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    key = _normalize_key(str(raw))
    ambiguous = _AMBIGUOUS_SUBTYPE_TERMS.get(canonical_event_type, {})
    if key in ambiguous:
        return MappingResult(outcome=MappingOutcome.AMBIGUOUS, candidates=ambiguous[key])
    table = _SUBTYPE_ALIASES.get(canonical_event_type, {})
    canonical = table.get(key)
    if canonical is None:
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    return MappingResult(outcome=MappingOutcome.MAPPED, canonical_value=canonical, matched_alias=key)


# --- Training status: maps onto SafetyEvent.status, except COMPETENCY_GAP, -----------------
# which app/intelligence/features.py reads from event_subtype instead --
# see TRAINING_STATUS_TARGET_FIELDS below, which records which column
# each canonical value actually belongs on (the existing schema's own
# choice, not something this module invents).

_TRAINING_STATUS_ALIASES: dict[str, str] = {
    "completed": "COMPLETED",
    "complete": "COMPLETED",
    "training complete": "COMPLETED",
    "overdue": "OVERDUE",
    "overdue training": "OVERDUE",
    "past due": "OVERDUE",
    "competency gap": "COMPETENCY_GAP",
    "skills gap": "COMPETENCY_GAP",
    "expired certification": "EXPIRED_CERTIFICATION",
    "expired cert": "EXPIRED_CERTIFICATION",
    "certification expired": "EXPIRED_CERTIFICATION",
    "incomplete": "INCOMPLETE",
}

#: canonical training-status value -> (event_subtype, status) to set on
#: the outgoing record -- exactly the two columns
#: `app/intelligence/features.py::compute_feature_set()` actually reads
#: (`event.status` for COMPLETED/OVERDUE/EXPIRED/INCOMPLETE,
#: `event.event_subtype == "competency_gap"` for the fourth).
TRAINING_STATUS_TARGET_FIELDS: dict[str, tuple[str | None, str | None]] = {
    "COMPLETED": (None, "COMPLETED"),
    "OVERDUE": (None, "OVERDUE"),
    "INCOMPLETE": (None, "INCOMPLETE"),
    "EXPIRED_CERTIFICATION": (None, "EXPIRED"),
    "COMPETENCY_GAP": ("competency_gap", None),
}


def map_training_status(raw: str | None) -> MappingResult:
    if raw is None or not str(raw).strip():
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    key = _normalize_key(str(raw))
    canonical = _TRAINING_STATUS_ALIASES.get(key)
    if canonical is None:
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    return MappingResult(outcome=MappingOutcome.MAPPED, canonical_value=canonical, matched_alias=key)


# --- Maintenance status: maps onto SafetyEvent.event_subtype + status ---------------------
# (EQUIPMENT-typed records) -- same "which column" reasoning as training
# status above.

_MAINTENANCE_STATUS_ALIASES: dict[str, str] = {
    "overdue preventive maintenance": "OVERDUE_PREVENTIVE_MAINTENANCE",
    "overdue pm": "OVERDUE_PREVENTIVE_MAINTENANCE",
    "pm overdue": "OVERDUE_PREVENTIVE_MAINTENANCE",
    # A backlog is an aggregate condition (many overdue items accumulating),
    # not a distinct per-record subtype -- treated as the same underlying
    # record type as a single overdue-maintenance item; see module docstring.
    "maintenance backlog": "OVERDUE_PREVENTIVE_MAINTENANCE",
    "backlog": "OVERDUE_PREVENTIVE_MAINTENANCE",
    "equipment failure": "EQUIPMENT_FAILURE",
    "failure": "EQUIPMENT_FAILURE",
    "breakdown": "EQUIPMENT_FAILURE",
}

#: canonical maintenance-status value -> (event_subtype, status), reading
#: `app/intelligence/features.py::compute_feature_set()`'s own EQUIPMENT
#: filters directly.
MAINTENANCE_STATUS_TARGET_FIELDS: dict[str, tuple[str | None, str | None]] = {
    "OVERDUE_PREVENTIVE_MAINTENANCE": ("maintenance", "OVERDUE"),
    "EQUIPMENT_FAILURE": ("failure", None),
}


def map_maintenance_status(raw: str | None) -> MappingResult:
    if raw is None or not str(raw).strip():
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    key = _normalize_key(str(raw))
    canonical = _MAINTENANCE_STATUS_ALIASES.get(key)
    if canonical is None:
        return MappingResult(outcome=MappingOutcome.UNKNOWN)
    return MappingResult(outcome=MappingOutcome.MAPPED, canonical_value=canonical, matched_alias=key)


# --- The opt-in adapter demonstrating this module wired into ingestion --------------------


class TerminologyMappingAdapter:
    """`DataSourceAdapter`-conforming (see `app/intelligence/adapters.py`'s
    own docstring for the Protocol) — the same four methods
    `GenericJSONAdapter` implements, with one difference: `event_type`/
    `event_subtype` are resolved through this module's alias tables
    before the shared `validate_and_normalize()` pipeline runs.
    **Ambiguous or unknown terminology is quarantined, never guessed**
    (item 4's own instruction) — a blocking `ValidationIssue` is added
    and the record's status is forced to `QUARANTINED` exactly the way
    `app/intelligence/validation.py`'s own blocking-issue rule already
    works, reusing that rule rather than reimplementing it."""

    source_system_name = "terminology-mapped"

    def _mapped_payload_and_issues(
        self, raw: RawSafetyEventPayload
    ) -> tuple[RawSafetyEventPayload, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        event_type_result = map_event_type(raw.event_type)
        if event_type_result.outcome == MappingOutcome.MAPPED:
            mapped_type = event_type_result.canonical_value
        else:
            mapped_type = raw.event_type  # preserved verbatim; validate_and_normalize() will flag it
            code = (
                "AMBIGUOUS_EVENT_TYPE_MAPPING"
                if event_type_result.outcome == MappingOutcome.AMBIGUOUS
                else "UNKNOWN_EVENT_TYPE_MAPPING"
            )
            detail = (
                f"could be {', '.join(event_type_result.candidates)}"
                if event_type_result.outcome == MappingOutcome.AMBIGUOUS
                else "no known alias"
            )
            issues.append(
                ValidationIssue(
                    code, f"event_type {raw.event_type!r} terminology mapping is unresolved ({detail}).", True
                )
            )

        mapped_subtype = raw.event_subtype
        if mapped_type in _SUBTYPE_ALIASES and raw.event_subtype:
            subtype_result = map_event_subtype(mapped_type, raw.event_subtype)
            if subtype_result.outcome == MappingOutcome.MAPPED:
                mapped_subtype = subtype_result.canonical_value
            else:
                code = (
                    "AMBIGUOUS_SUBTYPE_MAPPING"
                    if subtype_result.outcome == MappingOutcome.AMBIGUOUS
                    else "UNKNOWN_SUBTYPE_MAPPING"
                )
                issues.append(
                    ValidationIssue(
                        code, f"event_subtype {raw.event_subtype!r} terminology mapping is unresolved.", True
                    )
                )

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
        return mapped, issues

    def validate(self, raw: RawSafetyEventPayload) -> ValidationResult:
        mapped, mapping_issues = self._mapped_payload_and_issues(raw)
        # A throwaway id is safe here -- validate_and_normalize() only
        # stamps organization_id onto the NormalizedSafetyEvent it
        # builds; no validation rule reads it (mirrors
        # GenericJSONAdapter.validate()'s identical reasoning).
        result, _ = validate_and_normalize(mapped, organization_id=uuid.uuid4())
        all_issues = list(result.issues) + mapping_issues
        # Reuse validate_and_normalize()'s own blocking-issue rule rather
        # than reimplementing "what does a blocking issue force" here.
        if result.status == "REJECTED":
            status = "REJECTED"
        elif any(i.blocking for i in mapping_issues):
            status = DataQualityStatus.QUARANTINED.value
        else:
            status = result.status
        return ValidationResult(status=status, issues=all_issues)

    def normalize(
        self, raw: RawSafetyEventPayload, *, organization_id: uuid.UUID
    ) -> NormalizedSafetyEvent | None:
        mapped, _ = self._mapped_payload_and_issues(raw)
        _, normalized = validate_and_normalize(mapped, organization_id=organization_id)
        if normalized is not None:
            # validate_and_normalize() built source_value from `mapped`
            # (the post-mapping payload) -- overwrite just the two
            # mapped fields with the *true* original terminology the
            # source system actually sent, so `source_value` keeps its
            # existing, codebase-wide meaning ("the payload exactly as
            # received," never this adapter's own translation of it).
            normalized.source_value["event_type"] = raw.event_type
            normalized.source_value["event_subtype"] = raw.event_subtype
        return normalized

    def transform(self, normalized: NormalizedSafetyEvent) -> NormalizedSafetyEvent:
        return normalized

    def ingest(
        self, db, *, organization_id: uuid.UUID, raw: RawSafetyEventPayload, batch_id: uuid.UUID
    ):
        from app.intelligence.ingestion_service import safety_event_ingestion_service

        return safety_event_ingestion_service.ingest_event(
            db, organization_id=organization_id, payload=raw, adapter=self, batch_id=batch_id
        )
