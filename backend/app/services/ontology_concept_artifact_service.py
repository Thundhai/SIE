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

**Idempotent.** Re-running this function is safe: `propose_concept()`
itself raises `OntologyConceptConflictError` for a scope key that
already has a row (whatever its status), which this function catches
per-entry and treats as "already applied" -- an `APPROVED` concept
already matching the artifact is left untouched, never re-approved,
never duplicated. A conflicting existing concept (same scope key, a
genuinely different definition/status) still raises loudly, exactly
like the terminology decision artifact's own conflict handling.

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

from app.services import ontology_governance_service as ogs

#: `backend/config/enterprise_ontology_concepts_v1.json` -- resolved
#: relative to this file (`app/services/` -> `app` -> `backend` -> `config/`),
#: mirroring `terminology_decision_artifact_service.DEFAULT_ARTIFACT_PATH`'s
#: own resolution.
DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "config" / "enterprise_ontology_concepts_v1.json"


class OntologyConceptArtifactFormatError(ValueError):
    """Raised for a structurally invalid artifact file."""


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

        if ogs.is_valid_concept(db, layer=layer, parent_domain=parent_domain, concept_key=concept_key):
            result.already_satisfied += 1
            existing = ogs.list_concepts(db, layer=layer, parent_domain=parent_domain, status="APPROVED")
            match = next(c for c in existing if c.concept_key == concept_key)
            result.concept_ids[scope_key] = match.id
            continue

        # A row already exists at this scope but is not (yet, or ever)
        # APPROVED -- e.g. PROPOSED from an interrupted prior
        # application, or REJECTED/DEPRECATED -- surfaces here as
        # OntologyConceptConflictError, propagated as-is: never silently
        # reinterpreted, the caller sees the existing row's own state.
        proposed = ogs.propose_concept(
            db, layer=layer, parent_domain=parent_domain, concept_key=concept_key,
            definition=entry.get("definition") or "", justification=entry.get("why_new_concept_required") or "",
            acting_user_id=acting_user_id,
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
    "OntologyConceptArtifactFormatError",
    "apply_ontology_concept_artifact",
]
