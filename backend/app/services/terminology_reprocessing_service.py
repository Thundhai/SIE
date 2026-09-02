"""Explicit historical reprocessing — SIE Real Enterprise Terminology &
Ontology Calibration v0.1, item 13.

**Never called by the normal ingestion path.** Approving a mapping
(`terminology_calibration_service.approve_mapping()`) only changes how a
*future* ingestion call resolves that term (via
`CalibratedTerminologyMappingAdapter`, consulting
`build_active_mapping_index()`) — it never reaches back and rewrites
already-stored `SafetyEvent` rows. `reprocess_quarantined_records()`
below is the one, deliberate, explicitly-invoked exception: a human/admin
decides, after a mapping is approved, that the specific records it now
resolves should be updated too, and calls this function themselves. It is
never triggered automatically by `approve_mapping()`, a scheduled job, or
any other code path.

**Why this cannot simply re-run `ingest_batch()`/`ingest_event()`.** A
genuinely important architecture finding from building this milestone:
`SafetyEventIngestionService`'s idempotency check
(`app/intelligence/ingestion_service.py::_upsert()`) compares
`source_content_hash` — a hash of `source_value`, the payload **exactly
as originally received**. Reprocessing a quarantined record does not
change what was received, only *how it now resolves*; the raw
`event_type`/`event_subtype` string is identical to what is already
stored. Re-ingesting the same raw payload therefore always produces
`SKIPPED_IDEMPOTENT` — a real re-ingest can never re-trigger
reclassification for content that has not changed, only for content that
has. Reprocessing here calls `validate_and_normalize()` directly and then
`SafetyEventIngestionService._apply()` (the same, unmodified row-mutation
helper `_upsert()` itself calls) to bypass that specific short-circuit —
deliberately, not a workaround for a bug, since the two operations are
answering genuinely different questions ("did the source resend this
record?" vs. "does this record now resolve differently?").

**Temporal integrity is preserved by design, not by accident.**
`_apply()` stamps a fresh `ingestion_time = utcnow()` on every call,
exactly like a normal `CREATED`/`UPDATED` outcome — so a point-in-time
query (`events_as_of()`, `ingestion_time <= as_of`) from *before* this
reprocessing run correctly continues to exclude the record, exactly as
if it had never been reprocessed. Reprocessing is only ever knowable
*going forward* from the moment it actually happened, never retroactively
inserted into history — see item 13's own distinction between "newly
ingested," "explicitly reprocessed," and "retrospective analytical
recalculation" (the third is unaffected by this module entirely: any
analytics call already recomputes live over whatever canonical events
exist at query time).

**Scope.** Only the `event_type`/`event_subtype` domains are supported —
the same two domains `CalibratedTerminologyMappingAdapter` (and, before
it, the base `TerminologyMappingAdapter`) actually resolve during
ingestion. `training_status`/`maintenance_status` are reviewed by
`terminology_review.py` for reporting only; no ingestion adapter in this
codebase ever gates a record's canonical classification on them, so
there is nothing for a `training_status`/`maintenance_status` approval to
retroactively unlock — `reprocess_quarantined_records()` raises rather
than silently no-op for those domains.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.ingestion_service import (
    _content_hash,
    safety_event_ingestion_service,
)
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_calibration_adapter import ActiveMappingProvenance
from app.intelligence.terminology_mapping import _normalize_key
from app.intelligence.validation import validate_and_normalize
from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import (
    TerminologyMappingDecision,
    TerminologyMappingDecisionDomain,
    TerminologyMappingDecisionStatus,
)
from app.services.audit_service import AuditAction, audit_service
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

_SUPPORTED_DOMAINS = (TerminologyMappingDecisionDomain.EVENT_TYPE, TerminologyMappingDecisionDomain.EVENT_SUBTYPE)


class ReprocessingNotSupportedError(ValueError):
    """Raised for a domain no ingestion adapter actually gates
    classification on — see module docstring."""


class ReprocessingRequiresApprovedDecisionError(ValueError):
    """Raised when `decision_id` is not (currently) `APPROVED` — only an
    explicitly approved mapping may ever change a stored record's
    classification, the same rule ingestion itself follows."""


@dataclass
class ReprocessingResult:
    decision_id: uuid.UUID
    organization_id: uuid.UUID
    source_system: str
    domain: str
    context: str | None
    source_term: str
    records_examined: int = 0
    records_updated: int = 0
    records_still_unresolved: int = 0
    updated_event_ids: list[uuid.UUID] = field(default_factory=list)


def _raw_payload_from_source_value(source_value: dict) -> RawSafetyEventPayload:
    """Reconstructs the payload exactly as originally received —
    `source_value`'s own keys are `RawSafetyEventPayload`'s field names
    verbatim (see `RawSafetyEventPayload.as_source_value()`)."""
    known_fields = {f for f in RawSafetyEventPayload.__dataclass_fields__}
    return RawSafetyEventPayload(**{k: v for k, v in source_value.items() if k in known_fields})


def reprocess_quarantined_records(
    db: Session,
    *,
    organization_id: uuid.UUID,
    decision_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> ReprocessingResult:
    """Explicitly re-evaluates every currently-`QUARANTINED` `SafetyEvent`
    in `organization_id` whose raw, originally-received term (from
    `source_value`, never the possibly-already-mutated `event_type`
    column) matches `decision`'s own scope key, using `decision`'s
    approved canonical term. Requires `GOVERNANCE_MANAGE` — the same
    permission gate as `approve_mapping()`, since this mutates stored
    canonical data. Tenant- and source-scoped by construction (the query
    below is always filtered to `organization_id` and `decision.source_system`)."""
    authorization_service.require(
        db, user_id=acting_user_id, permission=Permission.GOVERNANCE_MANAGE, organization_id=organization_id
    )

    decision = db.execute(
        select(TerminologyMappingDecision).where(
            TerminologyMappingDecision.id == decision_id,
            TerminologyMappingDecision.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if decision is None:
        raise ValueError(f"No terminology mapping decision {decision_id} in organization {organization_id}.")
    if decision.status != TerminologyMappingDecisionStatus.APPROVED:
        raise ReprocessingRequiresApprovedDecisionError(
            f"Decision {decision_id} is {decision.status}, not APPROVED -- reprocessing requires an approved mapping."
        )
    if decision.domain not in _SUPPORTED_DOMAINS:
        raise ReprocessingNotSupportedError(
            f"domain {decision.domain!r} is not gated by any ingestion adapter's classification -- "
            f"reprocessing only supports {_SUPPORTED_DOMAINS}."
        )

    result = ReprocessingResult(
        decision_id=decision.id, organization_id=organization_id, source_system=decision.source_system,
        domain=decision.domain, context=decision.context, source_term=decision.source_term,
    )

    candidates = db.execute(
        select(SafetyEvent).where(
            SafetyEvent.organization_id == organization_id,
            SafetyEvent.source_system == decision.source_system,
            SafetyEvent.data_quality_status == "QUARANTINED",
        )
    ).scalars().all()

    field_name = "event_type" if decision.domain == TerminologyMappingDecisionDomain.EVENT_TYPE else "event_subtype"
    reprocessing_batch_id = uuid.uuid4()

    for event in candidates:
        source_value = event.source_value or {}
        # event_subtype decisions are scoped *under* an already-correctly-
        # resolved context event_type (item 7's own scoping rule) -- a
        # record whose event_type itself never resolved is never in scope
        # for a subtype decision, exactly like ingestion itself only
        # reviews subtype when `mapped_type in _SUBTYPE_ALIASES`.
        if decision.domain == TerminologyMappingDecisionDomain.EVENT_SUBTYPE and event.event_type != decision.context:
            continue

        raw_term = source_value.get(field_name)
        if raw_term is None or _normalize_key(str(raw_term)) != decision.normalized_term:
            continue

        result.records_examined += 1

        raw_payload = _raw_payload_from_source_value(source_value)
        setattr(raw_payload, field_name, decision.proposed_canonical_term)

        # Compound event_type+subtype target (Implement Approved HSE
        # Terminology Decisions v0.1) -- applied ONLY when this decision
        # is event_type-domain, declares one, and the record has no
        # independent raw subtype value of its own to preserve instead
        # (mirrors CalibratedTerminologyMappingAdapter._resolve_event_subtype()'s
        # own precedence rule exactly).
        target_event_subtype = None
        if decision.domain == TerminologyMappingDecisionDomain.EVENT_TYPE:
            target_event_subtype = (decision.provenance or {}).get("target_event_subtype")
            if target_event_subtype and not raw_payload.event_subtype:
                raw_payload.event_subtype = target_event_subtype
            else:
                target_event_subtype = None  # nothing to record -- a real raw subtype value took precedence

        validation_result, normalized = validate_and_normalize(raw_payload, organization_id=organization_id)
        if normalized is None:
            result.records_still_unresolved += 1
            continue

        # source_value keeps its codebase-wide meaning: exactly as
        # originally received, never this reprocessing's own resolution.
        normalized.source_value["event_type"] = source_value.get("event_type")
        normalized.source_value["event_subtype"] = source_value.get("event_subtype")

        # Exact mapping provenance (corrective-commit audit item 1) --
        # the same ActiveMappingProvenance shape the calibration-aware
        # adapter attaches at ingestion time, so a reprocessed event is
        # traceable back to precisely this decision/version exactly like
        # a freshly-ingested one, never a bare "calibration=true" flag.
        # Never overwrites an existing attributes key.
        provenance = ActiveMappingProvenance(
            decision_id=decision.id, mapping_version=decision.mapping_version, organization_id=organization_id,
            source_system=decision.source_system, domain=decision.domain, context=decision.context,
            source_term=decision.source_term, normalized_term=decision.normalized_term,
            canonical_term=decision.proposed_canonical_term, target_event_subtype=target_event_subtype,
        )
        calibration_info = {field_name: provenance.as_attributes(raw_term=str(raw_term))}
        if target_event_subtype:
            # Same decision, same exact decision_id/mapping_version --
            # recorded distinctly under "event_subtype" with the applied
            # compound value, never the type decision's own canonical_term.
            calibration_info["event_subtype"] = {
                **provenance.as_attributes(raw_term=str(raw_term)),
                "canonical_term": target_event_subtype,
                "derived_from_compound_event_type_decision": True,
            }
        normalized.attributes = {**normalized.attributes, "_terminology_calibration": calibration_info}

        content_hash = _content_hash(normalized.source_value)
        issues_json = [{"code": i.code, "message": i.message, "blocking": i.blocking} for i in validation_result.issues] or None

        safety_event_ingestion_service._apply(
            event, normalized, content_hash, validation_result.status, issues_json,
            reprocessing_batch_id, event.ingestion_source_id,
        )
        result.records_updated += 1
        result.updated_event_ids.append(event.id)

    db.commit()

    audit_service.log(
        db, action=AuditAction.TERMINOLOGY_HISTORICAL_REPROCESSING_APPLIED, resource_type="TerminologyMappingDecision",
        resource_id=decision.id, organization_id=organization_id, user_id=acting_user_id,
        metadata={
            "source_system": decision.source_system, "domain": decision.domain, "context": decision.context,
            "source_term": decision.source_term, "mapping_version": decision.mapping_version,
            "records_examined": result.records_examined, "records_updated": result.records_updated,
            "records_still_unresolved": result.records_still_unresolved,
            "reprocessing_batch_id": str(reprocessing_batch_id),
        },
    )
    return result


__all__ = [
    "ReprocessingNotSupportedError",
    "ReprocessingRequiresApprovedDecisionError",
    "ReprocessingResult",
    "reprocess_quarantined_records",
]
