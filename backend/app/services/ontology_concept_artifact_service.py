"""Ontology concept artifact — SIE Enterprise Ontology & Data Model
Expansion v0.1: reads `backend/config/enterprise_ontology_concepts_v1.json`
(the durable, version-controlled, PII-free record of the ontology-gap
investigation performed against the 15 real-dataset terminology terms
that remain `REJECTED` in
`backend/config/real_enterprise_terminology_decisions_v1.json`) and
applies it through the existing, unmodified
`ontology_governance_service.py` lifecycle -- never a second ontology
system, mirroring `terminology_decision_artifact_service.py`'s own
established pattern for the identical reason (a governed decision made
once needs a durable, reproducible representation, not only a row in a
database that might not persist).

**What applying this artifact does and does not do.** For each artifact
entry: an `APPROVED` entry (`concept_key` is not `null`) is proposed and
approved as a new platform-wide `OntologyConcept`, via
`propose_concept()`/`approve_concept()` exactly as a human platform
administrator would call them by hand. A `REJECTED` entry (`concept_key`
is `null` -- "no new concept is justified") creates **no** row at all;
it is documentation only, recorded in this artifact's own file for
audit continuity, never a database record (there is nothing to
propose). This function **never**:

  * creates, proposes, approves, or rejects a `TerminologyMappingDecision`;
  * calls `reprocess_quarantined_records()`;
  * touches a `SafetyEvent`;
  * loads the real enterprise workbook;
  * converts any of the 15 rejected terminology decisions to approved.

Approving a concept here makes it *exist* in the ontology -- nothing
more. Whether any real-dataset term should later be remapped against
one of these newly-approved concepts is explicitly deferred to a future
milestone (see `docs/SIE_ENTERPRISE_ONTOLOGY_V0_1.md`'s own "Terminology
mapping relationship" section).

**Idempotent -- semantically, not merely by key.** Re-running this
function is safe, but "safe" here means something specific: a same
scope key does not, by itself, mean a same ontology meaning. For every
`APPROVED` artifact entry, this function looks up any existing concept
at that entry's exact `(layer, parent_domain, concept_key)` scope
(`ontology_governance_service.get_concept_by_scope()`, which -- unlike
`is_valid_concept()` -- returns a row of ANY status) and applies:

  * **no existing row** -- proposed and approved fresh, via
    `propose_concept()`/`approve_concept()`, exactly as a human platform
    administrator would call them by hand;
  * **an existing `APPROVED` row whose semantic content matches** the
    artifact entry (`definition`, `ontology_version`, and the artifact's
    own justification text as a substring of the persisted
    justification -- see `_verify_matches_or_conflict()`) -- a genuine
    no-op, counted as `already_satisfied`, never re-approved, never
    duplicated;
  * **an existing `APPROVED` row whose semantic content differs** (a
    different `definition` or `ontology_version`, or a justification
    that no longer contains the artifact's own text) -- raises
    `OntologyConceptArtifactConflictError` immediately. The existing
    database row is left completely untouched: this function never
    resolves such a conflict itself, in either direction (never "database
    wins", never "artifact wins") -- a human platform administrator must
    resolve it explicitly through the governance service;
  * **an existing `REJECTED` or `DEPRECATED` row** -- also raises
    `OntologyConceptArtifactConflictError`, never silently reinterpreted
    as if it were an `APPROVED` match and never re-approved/recreated;
    governance already decided this scope key's fate and that decision
    is never bypassed merely because the artifact says `APPROVED`;
  * **an existing `PROPOSED` row** (e.g. from an interrupted prior
    application) -- also raises `OntologyConceptArtifactConflictError`;
    resuming a partial application is a deliberate governance act, not
    something this function silently completes on its own.

This exactly mirrors `terminology_decision_artifact_service.py`'s own
`TerminologyDecisionArtifactConflictError`/`_verify_matches_or_raise()`
pattern, for the identical reason: fail loudly rather than silently
reinterpret, overwrite, or bypass an already-governed decision.

**Authorization.** Delegates entirely to `ontology_governance_service.py`'s
own platform-admin-only enforcement (`GOVERNANCE_MANAGE`,
`organization_id=None`) -- this function adds no separate check and no
bypass; an unauthorized caller fails on the very first entry, before
any row is created.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.ontology_concept import OntologyConcept, OntologyConceptStatus
from app.services import ontology_governance_service as ogs

#: `backend/config/enterprise_ontology_concepts_v1.json` -- resolved
#: relative to this file (`app/services/` -> `app` -> `backend` -> `config/`),
#: mirroring `terminology_decision_artifact_service.DEFAULT_ARTIFACT_PATH`'s
#: own resolution.
DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "config" / "enterprise_ontology_concepts_v1.json"


class OntologyConceptArtifactFormatError(ValueError):
    """Raised for a structurally invalid artifact file."""


class OntologyConceptArtifactConflictError(ValueError):
    """Raised when an existing `OntologyConcept` row at an artifact
    entry's exact `(layer, parent_domain, concept_key)` scope does not
    represent the same ontology meaning as the artifact declares --
    either because it is not `APPROVED` (a `REJECTED`, `DEPRECATED`, or
    still-`PROPOSED` row can never silently stand in for the artifact's
    `APPROVED` entry) or because an `APPROVED` row's own semantic
    content (`definition`, `ontology_version`, or justification) differs
    from what the artifact declares for that same key. Same scope key
    does not mean same ontology meaning -- this is deliberately never
    resolved automatically in either direction (never "database wins",
    never "artifact wins"); the existing database row is always left
    completely untouched, and a human platform administrator must
    resolve the conflict explicitly through the governance service. The
    message identifies the scope key and the conflicting field(s) only
    -- never the full persisted row and never any PII."""


@dataclass
class OntologyArtifactApplyResult:
    artifact_id: str
    ontology_version: int
    total_in_artifact: int = 0
    approved_new: int = 0
    already_satisfied: int = 0
    documented_no_concept: int = 0
    concept_ids: dict[tuple[str, str | None, str], uuid.UUID] = field(default_factory=dict)


def _load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise OntologyConceptArtifactFormatError(f"No ontology concept artifact at {path}.")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    concepts = data.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        raise OntologyConceptArtifactFormatError(f"{path}: 'concepts' must be a non-empty list.")
    if not isinstance(data.get("ontology_version"), int):
        raise OntologyConceptArtifactFormatError(f"{path}: missing/invalid top-level 'ontology_version'.")
    required_keys = {"layer", "parent_domain", "concept_key", "decision"}
    for entry in concepts:
        missing = required_keys - entry.keys()
        if missing:
            raise OntologyConceptArtifactFormatError(f"{path}: concept entry missing keys {missing}: {entry}")
        if entry["decision"] not in ("APPROVED", "REJECTED"):
            raise OntologyConceptArtifactFormatError(f"{path}: unsupported decision {entry['decision']!r}")
        if entry["decision"] == "APPROVED" and not entry.get("concept_key"):
            raise OntologyConceptArtifactFormatError(f"{path}: an APPROVED entry must declare a concept_key: {entry}")
    return data


def _verify_matches_or_conflict(
    existing: OntologyConcept,
    *,
    layer: str,
    parent_domain: str | None,
    concept_key: str,
    definition: str,
    justification: str,
    ontology_version: int,
) -> None:
    """Raises `OntologyConceptArtifactConflictError` unless `existing` is
    an `APPROVED` concept whose semantic content matches the artifact
    entry -- see this module's own docstring ("Idempotent -- semantically,
    not merely by key") for the full rationale. Never mutates `existing`;
    a conflict here is reported, never repaired."""
    scope = f"layer={layer!r} parent_domain={parent_domain!r} concept_key={concept_key!r}"

    if existing.status != OntologyConceptStatus.APPROVED:
        raise OntologyConceptArtifactConflictError(
            f"Ontology artifact conflict: {scope} -- existing concept {existing.id} is "
            f"{existing.status}, not APPROVED. The artifact declares this scope APPROVED, but a "
            "REJECTED, DEPRECATED, or still-PROPOSED concept can never silently satisfy an APPROVED "
            "artifact entry merely because the scope key matches; governance already decided this "
            "concept's fate and that decision is never bypassed here."
        )

    conflicting_fields: list[str] = []
    if existing.definition != definition:
        conflicting_fields.append("definition")
    if existing.ontology_version != ontology_version:
        conflicting_fields.append("ontology_version")
    if justification and justification not in (existing.justification or ""):
        conflicting_fields.append("justification")

    if conflicting_fields:
        raise OntologyConceptArtifactConflictError(
            f"Ontology artifact conflict: {scope} -- existing APPROVED concept {existing.id} has "
            f"different semantic content than the durable artifact declares for this same scope key "
            f"(conflicting field(s): {', '.join(conflicting_fields)}). Same scope key does not mean "
            "same ontology meaning -- refusing to silently accept or overwrite the existing concept; "
            "resolve manually through ontology governance."
        )


def apply_ontology_concept_artifact(
    db: Session, *, acting_user_id: uuid.UUID, artifact_path: str | Path | None = None,
) -> OntologyArtifactApplyResult:
    """Applies every `APPROVED` entry in the artifact at `artifact_path`
    (default `DEFAULT_ARTIFACT_PATH`) as a new, platform-wide
    `OntologyConcept` -- see this module's own docstring for the full
    idempotency, authorization, and scope guarantees."""
    path = Path(artifact_path) if artifact_path is not None else DEFAULT_ARTIFACT_PATH
    artifact = _load_artifact(path)
    ontology_version: int = artifact["ontology_version"]
    result = OntologyArtifactApplyResult(
        artifact_id=artifact.get("artifact_id", path.stem), ontology_version=ontology_version,
        total_in_artifact=len(artifact["concepts"]),
    )

    for entry in artifact["concepts"]:
        layer: str = entry["layer"]
        parent_domain: str | None = entry["parent_domain"]
        concept_key: str | None = entry["concept_key"]
        decision: str = entry["decision"]
        scope_key = (layer, parent_domain, concept_key)

        if decision == "REJECTED" or concept_key is None:
            # Documentation only -- no OntologyConcept row exists (or
            # should exist) for a term this investigation concluded
            # needs no new canonical concept.
            result.documented_no_concept += 1
            continue

        definition: str = entry.get("definition") or ""
        justification: str = entry.get("why_new_concept_required") or ""

        existing = ogs.get_concept_by_scope(db, layer=layer, parent_domain=parent_domain, concept_key=concept_key)

        if existing is not None:
            # Same scope key does not mean same ontology meaning --
            # raises OntologyConceptArtifactConflictError unless
            # `existing` is APPROVED and semantically identical to this
            # artifact entry. Never mutates `existing` either way.
            _verify_matches_or_conflict(
                existing, layer=layer, parent_domain=parent_domain, concept_key=concept_key,
                definition=definition, justification=justification, ontology_version=ontology_version,
            )
            result.already_satisfied += 1
            result.concept_ids[scope_key] = existing.id
            continue

        proposed = ogs.propose_concept(
            db, layer=layer, parent_domain=parent_domain, concept_key=concept_key,
            definition=definition, justification=justification, acting_user_id=acting_user_id,
        )

        approved = ogs.approve_concept(
            db, concept_id=proposed.id, acting_user_id=acting_user_id, ontology_version=ontology_version,
        )
        result.approved_new += 1
        result.concept_ids[scope_key] = approved.id

    return result


__all__ = [
    "DEFAULT_ARTIFACT_PATH",
    "OntologyArtifactApplyResult",
    "OntologyConceptArtifactConflictError",
    "OntologyConceptArtifactFormatError",
    "apply_ontology_concept_artifact",
]
