"""Audit logging — see app/models/audit_log.py for the storage model and
its design rationale.

`AuditAction` is a small, open-ended collection of known action-name
constants (not an enum — new actions are expected to be added routinely
as more of the system gets wired to audit logging, without a migration).
`AuditService.log()` is the single write path; every call site listed in
this milestone's spec that is actually implemented calls it — see the
README's "Audit foundation" section for the current list and what is
*not* yet wired up. `log()` also takes an optional `commit` flag (SIE
Milestone 17 corrective patch, default `True` — see its own docstring)
letting a caller with its own transaction boundary defer the commit
instead of always committing independently.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditAction:
    """Known action names in use today. A plain string is still accepted
    by `AuditService.log()` — this class is a convenience/typo-guard, not
    an enforced enum (see module docstring)."""

    KNOWLEDGE_SOURCE_CREATED = "KNOWLEDGE_SOURCE_CREATED"
    KNOWLEDGE_VERIFIED = "KNOWLEDGE_VERIFIED"
    DOCUMENT_CREATED = "DOCUMENT_CREATED"
    DOCUMENT_VERSION_CREATED = "DOCUMENT_VERSION_CREATED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_STATUS_CHANGED = "MEMBER_STATUS_CHANGED"
    INGESTION_STARTED = "INGESTION_STARTED"
    INGESTION_COMPLETED = "INGESTION_COMPLETED"
    INGESTION_FAILED = "INGESTION_FAILED"
    RAG_QUERY_EXECUTED = "RAG_QUERY_EXECUTED"
    SAFETY_EVENT_INGESTED = "SAFETY_EVENT_INGESTED"
    SAFETY_EVENT_BATCH_INGESTED = "SAFETY_EVENT_BATCH_INGESTED"
    INTELLIGENCE_ANALYTICS_QUERIED = "INTELLIGENCE_ANALYTICS_QUERIED"
    INTELLIGENCE_SIGNAL_GENERATED = "INTELLIGENCE_SIGNAL_GENERATED"
    API_CLIENT_CREATED = "API_CLIENT_CREATED"
    API_CLIENT_SECRET_ROTATED = "API_CLIENT_SECRET_ROTATED"
    API_CLIENT_REVOKED = "API_CLIENT_REVOKED"
    PREDICTIVE_MODEL_TRAINED = "PREDICTIVE_MODEL_TRAINED"
    PREDICTIVE_MODEL_STATUS_CHANGED = "PREDICTIVE_MODEL_STATUS_CHANGED"
    PREDICTION_GENERATED = "PREDICTION_GENERATED"
    PREDICTION_ABSTAINED = "PREDICTION_ABSTAINED"
    # Model Validation & Governance v0.1 (milestone item 47's own list).
    DATASET_VALIDATED = "DATASET_VALIDATED"
    MODEL_VALIDATION_REPORT_GENERATED = "MODEL_VALIDATION_REPORT_GENERATED"
    MODEL_APPROVED = "MODEL_APPROVED"
    MODEL_REJECTED = "MODEL_REJECTED"
    MODEL_DEPLOYED = "MODEL_DEPLOYED"
    MODEL_UNDEPLOYED = "MODEL_UNDEPLOYED"
    MODEL_RETIRED = "MODEL_RETIRED"
    MODEL_REVIEW_REQUIRED = "MODEL_REVIEW_REQUIRED"
    MODEL_REVIEW_ACKNOWLEDGED = "MODEL_REVIEW_ACKNOWLEDGED"
    PREDICTION_OUTCOME_EVALUATED = "PREDICTION_OUTCOME_EVALUATED"
    # Intelligence Platform Integration & Enterprise API v0.1 (milestone
    # item 24's own list). ANALYTICS_QUERY/RAG_QUERY/EVENT_INGESTION are
    # already covered by the existing, more specific
    # INTELLIGENCE_ANALYTICS_QUERIED/RAG_QUERY_EXECUTED/
    # SAFETY_EVENT_INGESTED(_BATCH) actions above -- reused, not
    # duplicated under a second, vaguer name.
    API_AUTHENTICATED = "API_AUTHENTICATED"
    API_ACCESS_DENIED = "API_ACCESS_DENIED"
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"
    # Enterprise Data Ingestion & Validation Foundation v0.1 (milestone
    # item 17's own list). Per-record/per-batch canonical-event outcomes
    # are already covered by the existing, more specific
    # SAFETY_EVENT_INGESTED/SAFETY_EVENT_BATCH_INGESTED actions above --
    # reused, not duplicated, for the underlying safety_events write path
    # (see app/intelligence/enterprise_ingestion.py's own docstring).
    INGESTION_SOURCE_CREATED = "INGESTION_SOURCE_CREATED"
    INGESTION_SOURCE_STATUS_CHANGED = "INGESTION_SOURCE_STATUS_CHANGED"
    ENTERPRISE_INGESTION_BATCH_COMPLETED = "ENTERPRISE_INGESTION_BATCH_COMPLETED"
    # Real Enterprise Terminology & Ontology Calibration v0.1 (this
    # milestone's own item 15 list) -- app/services/terminology_calibration_service.py
    # is the one write path for every one of these.
    TERMINOLOGY_MAPPING_CANDIDATE_CREATED = "TERMINOLOGY_MAPPING_CANDIDATE_CREATED"
    TERMINOLOGY_MAPPING_PROPOSED = "TERMINOLOGY_MAPPING_PROPOSED"
    TERMINOLOGY_MAPPING_APPROVED = "TERMINOLOGY_MAPPING_APPROVED"
    TERMINOLOGY_MAPPING_REJECTED = "TERMINOLOGY_MAPPING_REJECTED"
    TERMINOLOGY_MAPPING_NEW_VERSION_OPENED = "TERMINOLOGY_MAPPING_NEW_VERSION_OPENED"
    TERMINOLOGY_HISTORICAL_REPROCESSING_APPLIED = "TERMINOLOGY_HISTORICAL_REPROCESSING_APPLIED"
    # SIE Enterprise Ontology & Data Model Expansion v0.1 --
    # app/services/ontology_governance_service.py is the one write path
    # for every one of these. Platform-wide (organization_id=None on the
    # AuditLog row), mirroring KNOWLEDGE_SOURCE_CREATED's own GLOBAL-write
    # precedent -- see that service's own docstring.
    ONTOLOGY_CONCEPT_PROPOSED = "ONTOLOGY_CONCEPT_PROPOSED"
    ONTOLOGY_CONCEPT_APPROVED = "ONTOLOGY_CONCEPT_APPROVED"
    ONTOLOGY_CONCEPT_REJECTED = "ONTOLOGY_CONCEPT_REJECTED"
    ONTOLOGY_CONCEPT_DEPRECATED = "ONTOLOGY_CONCEPT_DEPRECATED"
    # SIE Milestone 17: Actions & Intervention Foundation v0.1 --
    # app/services/safety_action_service.py is the one write path for
    # every one of these (called from app/api/v1/actions.py). Distinct
    # from the domain-scoped SafetyActionHistory table (§12 of that
    # milestone) -- this is the platform-wide security/administrative
    # log every other milestone already writes to; see that service
    # module's own docstring for why both exist.
    SAFETY_ACTION_CREATED = "SAFETY_ACTION_CREATED"
    SAFETY_ACTION_UPDATED = "SAFETY_ACTION_UPDATED"
    SAFETY_ACTION_ASSIGNED = "SAFETY_ACTION_ASSIGNED"
    SAFETY_ACTION_STATUS_CHANGED = "SAFETY_ACTION_STATUS_CHANGED"
    # SIE Milestone 20: Production Authentication & Identity Foundation
    # v0.1 -- app/api/deps_auth.py::get_production_authenticated_user_id
    # is the one write path for AUTH_SUCCEEDED/AUTH_REJECTED;
    # app/services/identity_service.py::IdentityResolverService is the one
    # write path for IDENTITY_PROVISIONED. Never logs a token, secret, or
    # password -- see that dependency's own docstring.
    AUTH_SUCCEEDED = "AUTH_SUCCEEDED"
    AUTH_REJECTED = "AUTH_REJECTED"
    IDENTITY_PROVISIONED = "IDENTITY_PROVISIONED"
    # SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1, item
    # 24. app/services/risk_assessment_service.py is the one write path
    # for every one of these (called from app/api/v1/risk_assessments.py).
    RISK_ASSESSMENT_CREATED = "RISK_ASSESSMENT_CREATED"
    RISK_ASSESSMENT_UPDATED = "RISK_ASSESSMENT_UPDATED"
    RISK_ASSESSMENT_SUBMITTED = "RISK_ASSESSMENT_SUBMITTED"
    RISK_ASSESSMENT_APPROVED = "RISK_ASSESSMENT_APPROVED"
    RISK_ASSESSMENT_SUPERSEDED = "RISK_ASSESSMENT_SUPERSEDED"
    RISK_ASSESSMENT_FINDING_CREATED = "RISK_ASSESSMENT_FINDING_CREATED"
    RISK_ASSESSMENT_FINDING_UPDATED = "RISK_ASSESSMENT_FINDING_UPDATED"


class AuditService:
    def log(
        self,
        db: Session,
        *,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        commit: bool = True,
    ) -> AuditLog:
        """`commit=True` (default) is unchanged behavior for every
        existing call site across this codebase: the `AuditLog` row
        commits immediately, on its own.

        `commit=False` (SIE Milestone 17 corrective patch) instead only
        `db.add()`s and `db.flush()`s the row, so it participates in a
        caller's own open transaction rather than committing
        independently — used by
        `app/services/safety_action_service.py::action_mutation_transaction()`
        so a `SafetyAction` mutation and the `AuditLog` row describing it
        either both persist or neither does. This is purely additive:
        no other call site passes `commit=False`, so nothing about the
        platform-wide audit trail's existing behavior changes."""
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            organization_id=organization_id,
            user_id=user_id,
            event_metadata=metadata,
            request_id=request_id,
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        else:
            db.flush()
        return entry


audit_service = AuditService()
