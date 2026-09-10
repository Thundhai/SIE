"""The minimal model registry service — milestone items 24-26, extended
by Model Validation & Governance v0.1 items 21-25.

    training.py -> create_model_entry() -> status=TRAINED
    human review -> mark_validated() -> VALIDATED
    human review -> approve()        -> APPROVED   (requires reviewer_user_id;
                                                       writes a ModelApproval row)
    human review -> deploy()         -> DEPLOYED   (retires any previously
                                                       deployed model for the
                                                       same organization + entity_type)
    human review -> undeploy()       -> APPROVED   (pulls a model out of serving
                                                       without retiring it --
                                                       redeployable later)
    human review -> retire()         -> RETIRED    (terminal)
    human review -> reject()         -> REJECTED   (requires reviewer_user_id;
                                                       writes a ModelApproval row)

**No automatic deployment (milestone item 26).** `create_model_entry()`
is the *only* function `app/predictions/training.py` calls — it always
produces a `TRAINED` row. Every later transition is a separate, explicit
call this module exposes and nothing in this codebase calls on training's
behalf: `TRAINED -> VALIDATED -> APPROVED -> DEPLOYED` is a human-review
workflow, not a pipeline.

**The model can never approve itself (milestone item 23).** `approve()`
and `reject()` both require a `reviewer_user_id` — there is no code path
that transitions a model to `APPROVED` without one — and both persist a
`ModelApproval` row (reviewer, timestamp, model version, the validation
report it was decided against, and any notes) in the same call, so an
`APPROVED`/`REJECTED` model can never exist without a matching, durable
approval record.

**Rollback never deletes history (milestone item 25).** `undeploy()` and
`retire()` both leave the row in place — a superseded/pulled model is
still fully inspectable, still resolves from every `Prediction.model_id`
that used it, and (if merely undeployed, not retired) can be redeployed
via `deploy()` without retraining.

Every transition is audit-logged (milestone item 46) and rejected outright
— `InvalidModelTransitionError`, no partial state change — if it is not
in `app/predictions/enums.py::_ALLOWED_TRANSITIONS`.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_approval import ModelApproval
from app.models.model_registry_entry import ModelRegistryEntry
from app.predictions.enums import ModelStatus, is_allowed_transition
from app.services.audit_service import AuditAction, audit_service

# One specific audit action per target status (milestone item 47's own
# list) -- falls back to the generic PREDICTIVE_MODEL_STATUS_CHANGED for
# any status not named here (VALIDATED has no dedicated action; it's
# covered by mark_validated()'s own metadata).
_TRANSITION_AUDIT_ACTIONS: dict[ModelStatus, str] = {
    ModelStatus.APPROVED: AuditAction.MODEL_APPROVED,
    ModelStatus.REJECTED: AuditAction.MODEL_REJECTED,
    ModelStatus.DEPLOYED: AuditAction.MODEL_DEPLOYED,
    ModelStatus.RETIRED: AuditAction.MODEL_RETIRED,
}


class InvalidModelTransitionError(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition a model from {current!r} to {target!r}.")


def _next_model_version(db: Session, *, organization_id: uuid.UUID, model_name: str) -> str:
    """`vN`, auto-incremented per `(organization_id, model_name)` — never
    reusing a version number, even across REJECTED/RETIRED rows (milestone
    item 22: "never overwrite a previous model version")."""
    existing = db.execute(
        select(ModelRegistryEntry.model_version).where(
            ModelRegistryEntry.organization_id == organization_id,
            ModelRegistryEntry.model_name == model_name,
        )
    ).scalars().all()
    highest = 0
    for v in existing:
        match = re.fullmatch(r"v(\d+)", v)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"v{highest + 1}"


def create_model_entry(
    db: Session,
    *,
    organization_id: uuid.UUID,
    model_name: str,
    model_type: str,
    entity_type: str,
    prediction_target_version: str,
    label_definition_version: str,
    feature_set_version: str,
    training_data_version: str,
    horizon_days: int,
    training_period_start: date,
    training_period_end: date,
    validation_period_start: date,
    validation_period_end: date,
    test_period_start: date,
    test_period_end: date,
    hyperparameters: dict,
    metrics: dict,
    parameters: dict,
    dataset_version_id: uuid.UUID | None = None,
    notes: str | None = None,
    user_id: uuid.UUID | None = None,
) -> ModelRegistryEntry:
    entry = ModelRegistryEntry(
        organization_id=organization_id,
        model_name=model_name,
        model_version=_next_model_version(db, organization_id=organization_id, model_name=model_name),
        model_type=model_type,
        status=ModelStatus.TRAINED.value,
        entity_type=entity_type,
        prediction_target_version=prediction_target_version,
        label_definition_version=label_definition_version,
        feature_set_version=feature_set_version,
        training_data_version=training_data_version,
        horizon_days=horizon_days,
        dataset_version_id=dataset_version_id,
        training_period_start=training_period_start,
        training_period_end=training_period_end,
        validation_period_start=validation_period_start,
        validation_period_end=validation_period_end,
        test_period_start=test_period_start,
        test_period_end=test_period_end,
        hyperparameters=hyperparameters,
        metrics=metrics,
        parameters=parameters,
        calibration_validated=False,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    audit_service.log(
        db,
        action=AuditAction.PREDICTIVE_MODEL_TRAINED,
        resource_type="model_registry_entry",
        resource_id=entry.id,
        organization_id=organization_id,
        user_id=user_id,
        metadata={"model_name": model_name, "model_version": entry.model_version, "status": entry.status},
    )
    return entry


def _transition(
    db: Session,
    entry: ModelRegistryEntry,
    *,
    target_status: ModelStatus,
    user_id: uuid.UUID | None,
    extra_metadata: dict | None = None,
    audit_action: str | None = None,
) -> ModelRegistryEntry:
    if not is_allowed_transition(entry.status, target_status.value):
        raise InvalidModelTransitionError(entry.status, target_status.value)

    previous_status = entry.status
    entry.status = target_status.value
    db.commit()
    db.refresh(entry)

    metadata = {"model_name": entry.model_name, "model_version": entry.model_version, "from": previous_status, "to": entry.status}
    if extra_metadata:
        metadata.update(extra_metadata)
    audit_service.log(
        db,
        action=audit_action or _TRANSITION_AUDIT_ACTIONS.get(target_status, AuditAction.PREDICTIVE_MODEL_STATUS_CHANGED),
        resource_type="model_registry_entry",
        resource_id=entry.id,
        organization_id=entry.organization_id,
        user_id=user_id,
        metadata=metadata,
    )
    return entry


def mark_validated(
    db: Session, entry: ModelRegistryEntry, *, calibration_validated: bool, user_id: uuid.UUID | None = None
) -> ModelRegistryEntry:
    """`calibration_validated` is recorded here, deliberately alongside
    the status transition itself — a model can reach `VALIDATED` status
    without passing calibration (a human reviewer may still want to
    inspect it), but `Prediction.probability` (milestone items 18-19) is
    gated on this flag alone, never on status."""
    entry.calibration_validated = calibration_validated
    return _transition(
        db, entry, target_status=ModelStatus.VALIDATED, user_id=user_id,
        extra_metadata={"calibration_validated": calibration_validated},
    )


def _record_approval_decision(
    db: Session,
    entry: ModelRegistryEntry,
    *,
    reviewer_user_id: uuid.UUID,
    decision: str,
    validation_report: dict | None,
    notes: str | None,
) -> ModelApproval:
    approval = ModelApproval(
        organization_id=entry.organization_id,
        model_id=entry.id,
        model_version=entry.model_version,
        reviewer_user_id=reviewer_user_id,
        decision=decision,
        notes=notes,
        validation_report=validation_report or {},
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def approve(
    db: Session,
    entry: ModelRegistryEntry,
    *,
    reviewer_user_id: uuid.UUID,
    validation_report: dict | None = None,
    notes: str | None = None,
) -> ModelRegistryEntry:
    """A human reviewer's decision — `reviewer_user_id` is required
    (milestone item 23: the model can never approve itself). Writes a
    `ModelApproval` row in the same call that changes status, so an
    `APPROVED` model always has a matching approval record."""
    result = _transition(
        db, entry, target_status=ModelStatus.APPROVED, user_id=reviewer_user_id,
        extra_metadata={"reviewer_user_id": str(reviewer_user_id)},
    )
    _record_approval_decision(
        db, result, reviewer_user_id=reviewer_user_id, decision="APPROVE",
        validation_report=validation_report, notes=notes,
    )
    return result


def deploy(db: Session, entry: ModelRegistryEntry, *, user_id: uuid.UUID | None = None) -> ModelRegistryEntry:
    """Exactly one `DEPLOYED` model may serve live predictions for a given
    `(organization_id, entity_type)` at a time — any previously deployed
    model for the same organization and entity type is retired first, so
    `predictor.py`'s "find the deployed model" lookup is never ambiguous.
    Works identically whether `entry` is newly `APPROVED` or a previously
    `undeploy()`-ed model being redeployed (milestone item 25's
    "redeploy a previously approved version")."""
    previously_deployed = db.execute(
        select(ModelRegistryEntry).where(
            ModelRegistryEntry.organization_id == entry.organization_id,
            ModelRegistryEntry.entity_type == entry.entity_type,
            ModelRegistryEntry.status == ModelStatus.DEPLOYED.value,
            ModelRegistryEntry.id != entry.id,
        )
    ).scalars().all()
    for old in previously_deployed:
        _transition(db, old, target_status=ModelStatus.RETIRED, user_id=user_id, extra_metadata={"reason": "SUPERSEDED_BY_NEW_DEPLOYMENT"})

    return _transition(db, entry, target_status=ModelStatus.DEPLOYED, user_id=user_id)


def undeploy(db: Session, entry: ModelRegistryEntry, *, user_id: uuid.UUID | None = None) -> ModelRegistryEntry:
    """Pulls a model out of live serving without retiring it (milestone
    item 25) — returns to `APPROVED`, so it remains eligible for
    `deploy()` again later. Use `retire()` instead for a permanent
    decommission."""
    return _transition(
        db, entry, target_status=ModelStatus.APPROVED, user_id=user_id,
        extra_metadata={"reason": "UNDEPLOYED"}, audit_action=AuditAction.MODEL_UNDEPLOYED,
    )


def retire(db: Session, entry: ModelRegistryEntry, *, user_id: uuid.UUID | None = None) -> ModelRegistryEntry:
    return _transition(db, entry, target_status=ModelStatus.RETIRED, user_id=user_id)


def reject(
    db: Session,
    entry: ModelRegistryEntry,
    *,
    reviewer_user_id: uuid.UUID,
    reason: str,
    validation_report: dict | None = None,
) -> ModelRegistryEntry:
    """A human reviewer's decision not to approve a model — also requires
    `reviewer_user_id` and writes a matching `ModelApproval` row (milestone
    item 23), for the same reason `approve()` does."""
    result = _transition(
        db, entry, target_status=ModelStatus.REJECTED, user_id=reviewer_user_id, extra_metadata={"reason": reason},
    )
    _record_approval_decision(
        db, result, reviewer_user_id=reviewer_user_id, decision="REJECT",
        validation_report=validation_report, notes=reason,
    )
    return result


def get_deployed_model(db: Session, *, organization_id: uuid.UUID, entity_type: str) -> ModelRegistryEntry | None:
    """The single model `predictor.py` serves live predictions from for
    this organization/entity type — `None` if nothing has been deployed
    yet (predictor.py must abstain, not fall back to a lesser model)."""
    return db.execute(
        select(ModelRegistryEntry).where(
            ModelRegistryEntry.organization_id == organization_id,
            ModelRegistryEntry.entity_type == entity_type,
            ModelRegistryEntry.status == ModelStatus.DEPLOYED.value,
        )
    ).scalar_one_or_none()


__all__ = [
    "InvalidModelTransitionError",
    "approve",
    "create_model_entry",
    "deploy",
    "get_deployed_model",
    "mark_validated",
    "reject",
    "retire",
    "undeploy",
]
