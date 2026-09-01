"""Audit logging — see app/models/audit_log.py for the storage model and
its design rationale.

`AuditAction` is a small, open-ended collection of known action-name
constants (not an enum — new actions are expected to be added routinely
as more of the system gets wired to audit logging, without a migration).
`AuditService.log()` is the single write path; every call site listed in
this milestone's spec that is actually implemented calls it — see the
README's "Audit foundation" section for the current list and what is
*not* yet wired up.
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
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            organization_id=organization_id,
            user_id=user_id,
            event_metadata=metadata,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry


audit_service = AuditService()
