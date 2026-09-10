"""Terminology decision artifact — Terminology Calibration v0.1 corrective
commit, **blocker 1**: a durable, version-controlled, PII-free
representation of the 18 governed HSE terminology decisions made during
human review of the real enterprise dataset, and the one mechanism that
applies it.

**The problem this fixes.** The prior corrective commit (`0505d8b`)
persisted the 18 decisions only in a throwaway local PostgreSQL database
that was deliberately destroyed at the end of that session (per this
codebase's own "never commit the real workbook" policy). If that
database disappears, the governed decisions disappear with it — the
repository contained the *machinery* to make and apply such decisions,
but not a durable, reproducible representation of the actual decision
set itself. That does not satisfy "create/persist the 18 human
decisions."

**What lives where:**

    backend/config/real_enterprise_terminology_decisions_v1.json
        The durable artifact -- WHAT was decided. Version-controlled,
        human-reviewable, PII-free: source_term, domain, context,
        occurrence_count (already public in
        docs/REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md), decision
        (APPROVED/REJECTED), canonical_event_type, target_event_subtype,
        and a rationale string -- never a real record ID, name,
        narrative, email, or phone number, and never a database UUID
        (those are generated fresh by `TerminologyMappingDecision` every
        time the artifact is applied -- see the module docstring's own
        "do not fabricate real database UUIDs" instruction).

    apply_terminology_decision_artifact() below (this module)
        HOW it gets applied -- reads the artifact and drives it through
        the existing, unmodified governed lifecycle
        (`terminology_calibration_service.create_review_candidates()`/
        `propose_mapping()`/`approve_mapping()`/`reject_mapping()`).
        Never a second terminology-decision system: every row this
        function ever creates or mutates is a completely ordinary
        `TerminologyMappingDecision`, indistinguishable in the database
        from one a human reviewer created by hand through the same
        service calls.

**Authorization boundary (explicit, no backdoor).** This function does
not itself grant, bypass, or check any special permission beyond what
`terminology_calibration_service.propose_mapping()`/`approve_mapping()`/
`reject_mapping()` already enforce on every call: `GOVERNANCE_MANAGE` in
`organization_id`, via the same `authorization_service.require()` those
functions already call. `apply_terminology_decision_artifact()` itself
additionally requires it up front, before touching the database at all,
purely so an unauthorized caller fails immediately and obviously rather
than partway through a batch -- not a second, different, or weaker
check. There is no environment variable, internal flag, or "trusted
caller" exception that skips this. A caller without `GOVERNANCE_MANAGE`
in `organization_id` cannot apply this artifact, exactly as they cannot
call `approve_mapping()` directly.

**Idempotency (safe to run more than once).** For each artifact entry,
this function first looks up any existing decision at that entry's exact
scope key (`organization_id`, `source_system`, `domain`, `context`,
`normalized_source_term`) --

  * a **terminal** existing decision (`APPROVED`/`REJECTED`) whose
    outcome already matches the artifact is left completely untouched
    (a no-op for that entry -- counted as `already_satisfied`, never
    re-approved/re-rejected, never a duplicate row);
  * a terminal existing decision whose outcome **conflicts** with the
    artifact (different status, different canonical term, or different
    compound subtype target) raises `TerminologyDecisionArtifactConflictError`
    immediately -- fail loudly, never silently reinterpret or overwrite
    an already-decided human judgment;
  * a **non-terminal** existing decision (`REVIEW_CANDIDATE`/`PROPOSED`
    -- e.g. from an interrupted prior application) is carried forward to
    its artifact-declared terminal state on the SAME row, never a new
    one;
  * **no** existing decision at that scope means a fresh
    `REVIEW_CANDIDATE` is created (via `create_review_candidates()`,
    which has its own, independent dedup-by-scope check too) and then
    carried to its terminal state.

Running this function twice therefore never creates 36 decisions, never
converts a `REJECTED` decision to `APPROVED`, never silently opens
`mapping_version=2` (that remains `open_new_version()`'s own, entirely
separate, deliberate operation -- never invoked here), and never
triggers reprocessing: `reprocess_quarantined_records()` is never called
by this module. Applying the artifact only ever changes
`TerminologyMappingDecision` rows; a real `SafetyEvent`'s own
classification is changed only by a human/admin explicitly calling
`reprocess_quarantined_records()` themselves afterward, exactly as
before this corrective commit.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.terminology_mapping import _normalize_key
from app.intelligence.terminology_review import (
    TerminologyReviewEntry,
    TerminologyReviewStatus,
)
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services import terminology_calibration_service as svc
from app.services.authorization_service import authorization_service
from app.services.permissions import Permission

#: `backend/config/real_enterprise_terminology_decisions_v1.json` --
#: resolved relative to this file so it works regardless of the caller's
#: own working directory (`app/services/` -> `app` -> `backend` -> `config/`).
DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "config" / "real_enterprise_terminology_decisions_v1.json"

_SUPPORTED_DECISION_KINDS = ("APPROVED", "REJECTED")


class TerminologyDecisionArtifactConflictError(ValueError):
    """Raised when an existing **terminal** decision at a scope key does
    not match what the artifact declares for that same scope key --
    fail loudly rather than silently reinterpret or overwrite an
    already-decided human judgment."""


class TerminologyDecisionArtifactFormatError(ValueError):
    """Raised for a structurally invalid artifact file (missing keys, an
    unsupported `decision` value, an empty decision list, ...)."""


@dataclass
class ArtifactApplyResult:
    artifact_id: str
    total_in_artifact: int = 0
    created_new: int = 0
    resumed_pending: int = 0
    already_satisfied: int = 0
    approved: int = 0
    rejected: int = 0
    #: `{(source_system, domain, context, source_term): decision_id}` --
    #: for a caller that wants to know exactly which row resulted from
    #: which artifact entry, without a second query.
    decision_ids: dict[tuple[str, str, str | None, str], uuid.UUID] = field(default_factory=dict)


def _load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TerminologyDecisionArtifactFormatError(f"No decision artifact at {path}.")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise TerminologyDecisionArtifactFormatError(f"{path}: 'decisions' must be a non-empty list.")
    if not data.get("source_system"):
        raise TerminologyDecisionArtifactFormatError(f"{path}: missing top-level 'source_system'.")
    required_keys = {"source_term", "domain", "context", "decision"}
    for entry in decisions:
        missing = required_keys - entry.keys()
        if missing:
            raise TerminologyDecisionArtifactFormatError(f"{path}: decision entry missing keys {missing}: {entry}")
        if entry["decision"] not in _SUPPORTED_DECISION_KINDS:
            raise TerminologyDecisionArtifactFormatError(
                f"{path}: unsupported decision {entry['decision']!r} (expected one of {_SUPPORTED_DECISION_KINDS})."
            )
    return data


def _find_existing(
    db: Session, *, organization_id: uuid.UUID, source_system: str, domain: str, context: str | None, normalized_term: str,
) -> TerminologyMappingDecision | None:
    """The highest-`mapping_version` row at this exact scope key, of any
    status -- mirrors `get_active_mapping()`'s own ordering, but never
    filters by `status` (this lookup needs to see a `REVIEW_CANDIDATE`/
    `PROPOSED` row too, not just an `APPROVED` one)."""
    return db.execute(
        select(TerminologyMappingDecision).where(
            TerminologyMappingDecision.organization_id == organization_id,
            TerminologyMappingDecision.source_system == source_system,
            TerminologyMappingDecision.domain == domain,
            TerminologyMappingDecision.context == context,
            TerminologyMappingDecision.normalized_term == normalized_term,
        ).order_by(TerminologyMappingDecision.mapping_version.desc())
    ).scalars().first()


def _verify_matches_or_raise(
    existing: TerminologyMappingDecision,
    *,
    decision_kind: str,
    canonical_event_type: str | None,
    target_event_subtype: str | None,
    scope_key: tuple[str, str, str | None, str],
) -> None:
    if existing.status != decision_kind:
        raise TerminologyDecisionArtifactConflictError(
            f"{scope_key}: existing decision {existing.id} is {existing.status}, but the artifact declares "
            f"{decision_kind}. Refusing to silently reinterpret an already-terminal human decision."
        )
    if decision_kind == "APPROVED":
        if existing.proposed_canonical_term != canonical_event_type:
            raise TerminologyDecisionArtifactConflictError(
                f"{scope_key}: existing APPROVED decision {existing.id} has proposed_canonical_term="
                f"{existing.proposed_canonical_term!r}, but the artifact declares {canonical_event_type!r}."
            )
        existing_target = (existing.provenance or {}).get("target_event_subtype")
        if existing_target != target_event_subtype:
            raise TerminologyDecisionArtifactConflictError(
                f"{scope_key}: existing APPROVED decision {existing.id} has target_event_subtype="
                f"{existing_target!r}, but the artifact declares {target_event_subtype!r}."
            )


def apply_terminology_decision_artifact(
    db: Session,
    *,
    organization_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    artifact_path: str | Path | None = None,
) -> ArtifactApplyResult:
    """Applies every decision in the artifact at `artifact_path`
    (default `DEFAULT_ARTIFACT_PATH`) to `organization_id`, through the
    existing governed lifecycle -- see this module's own docstring for
    the full idempotency and authorization guarantees. Never reprocesses
    a single `SafetyEvent`; never touches any organization other than
    `organization_id`; never invents a canonical value not already
    present in the artifact itself (which in turn only ever names
    pre-existing SIE canonical values -- see the artifact file's own
    `rationale` fields)."""
    authorization_service.require(
        db, user_id=acting_user_id, permission=Permission.GOVERNANCE_MANAGE, organization_id=organization_id
    )

    path = Path(artifact_path) if artifact_path is not None else DEFAULT_ARTIFACT_PATH
    artifact = _load_artifact(path)
    source_system: str = artifact["source_system"]
    result = ArtifactApplyResult(
        artifact_id=artifact.get("artifact_id", path.stem), total_in_artifact=len(artifact["decisions"])
    )

    for entry in artifact["decisions"]:
        domain: str = entry["domain"]
        context: str | None = entry["context"]
        source_term: str = entry["source_term"]
        decision_kind: str = entry["decision"]
        canonical_event_type: str | None = entry.get("canonical_event_type")
        target_event_subtype: str | None = entry.get("target_event_subtype")
        occurrence_count: int = entry.get("occurrence_count", 0)
        rationale: str = entry.get("rationale", "Applied from the governed decision artifact.")
        normalized_term = _normalize_key(source_term)
        scope_key = (source_system, domain, context, source_term)

        existing = _find_existing(
            db, organization_id=organization_id, source_system=source_system, domain=domain,
            context=context, normalized_term=normalized_term,
        )

        if existing is not None and existing.is_terminal:
            _verify_matches_or_raise(
                existing, decision_kind=decision_kind, canonical_event_type=canonical_event_type,
                target_event_subtype=target_event_subtype, scope_key=scope_key,
            )
            result.already_satisfied += 1
            result.decision_ids[scope_key] = existing.id
            continue

        if existing is None:
            review_entry = TerminologyReviewEntry(
                domain=domain, context=context, source_term=source_term, proposed_canonical_term=None,
                status=TerminologyReviewStatus.UNKNOWN,
                reason="Surfaced from the governed decision artifact (never guessed).",
                occurrence_count=occurrence_count,
            )
            created = svc.create_review_candidates(
                db, organization_id=organization_id, source_system=source_system, entries=[review_entry],
                provenance={"decision_artifact_id": result.artifact_id},
            )
            if created:
                candidate = created[0]
                result.created_new += 1
            else:
                # create_review_candidates() has its own independent
                # dedup-by-scope check (raw source_term, not normalized)
                # and found an existing row this normalized-term lookup
                # above did not surface -- re-fetch and treat it exactly
                # like `existing` would have been treated.
                candidate = _find_existing(
                    db, organization_id=organization_id, source_system=source_system, domain=domain,
                    context=context, normalized_term=normalized_term,
                )
                if candidate is None:
                    raise TerminologyDecisionArtifactConflictError(
                        f"{scope_key}: create_review_candidates() reported an existing row but it could not be re-found."
                    )
                if candidate.is_terminal:
                    _verify_matches_or_raise(
                        candidate, decision_kind=decision_kind, canonical_event_type=canonical_event_type,
                        target_event_subtype=target_event_subtype, scope_key=scope_key,
                    )
                    result.already_satisfied += 1
                    result.decision_ids[scope_key] = candidate.id
                    continue
                result.resumed_pending += 1
        else:
            candidate = existing
            result.resumed_pending += 1

        if decision_kind == "APPROVED" and target_event_subtype:
            # Compound event_type+subtype target (see
            # app/intelligence/terminology_calibration_adapter.py's own
            # ActiveMappingProvenance.target_event_subtype docstring) --
            # stored on the existing provenance JSON column, never a new
            # column, exactly like a human reviewer applying it by hand
            # would (see tests/test_terminology_calibration.py's own
            # `_approve_compound()` helper for the identical pattern).
            candidate.provenance = {**(candidate.provenance or {}), "target_event_subtype": target_event_subtype}
            db.add(candidate)
            db.commit()
            db.refresh(candidate)

        # `candidate` is guaranteed non-terminal here (freshly created
        # REVIEW_CANDIDATE, or an existing non-terminal row resumed
        # above) -- propose_mapping() itself handles both
        # REVIEW_CANDIDATE and an already-PROPOSED row identically (the
        # latter revises the proposal, e.g. from an interrupted prior
        # application), so this is never conditioned on the exact status.
        candidate = svc.propose_mapping(
            db, organization_id=organization_id, decision_id=candidate.id,
            proposed_canonical_term=canonical_event_type if decision_kind == "APPROVED" else None,
            rationale=rationale, acting_user_id=acting_user_id,
        )

        if decision_kind == "APPROVED":
            decided = svc.approve_mapping(db, organization_id=organization_id, decision_id=candidate.id, acting_user_id=acting_user_id)
            result.approved += 1
        else:
            decided = svc.reject_mapping(
                db, organization_id=organization_id, decision_id=candidate.id, acting_user_id=acting_user_id, reason=rationale
            )
            result.rejected += 1

        result.decision_ids[scope_key] = decided.id

    return result


__all__ = [
    "DEFAULT_ARTIFACT_PATH",
    "ArtifactApplyResult",
    "TerminologyDecisionArtifactConflictError",
    "TerminologyDecisionArtifactFormatError",
    "apply_terminology_decision_artifact",
]
