"""Shared test helpers for the intelligence & predictive analytics test
suite — mirrors `tests/rag_test_helpers.py`'s "build the domain object
with sane defaults, override what the test cares about" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.intelligence.schemas import RawSafetyEventPayload
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from app.models.site import Site


def make_safety_event(**overrides) -> SafetyEvent:
    """A `SafetyEvent` ORM instance built directly (no DB session) — safe
    for pure-function tests (features/signals/trends operate on plain
    Python attribute access, never a query)."""
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        site_id=None,
        event_type="INCIDENT",
        event_subtype=None,
        event_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        period_end=None,
        reported_time=None,
        ingestion_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        location=None,
        project=None,
        department=None,
        contractor=None,
        activity=None,
        severity=None,
        potential_severity=None,
        status=None,
        description=None,
        attributes={},
        source_system="test-system",
        source_record_id=str(uuid.uuid4()),
        source_value={},
        source_content_hash="hash",
        normalization_version="normalize-v1",
        schema_version="schema-v1",
        ingestion_batch_id=uuid.uuid4(),
        data_quality_status="VALID",
        data_quality_issues=None,
    )
    defaults.update(overrides)
    return SafetyEvent(**defaults)


def make_org(db_session: Session, name: str = "Test Org") -> Organization:
    org = Organization(name=name)
    db_session.add(org)
    db_session.commit()
    return org


def make_site(db_session: Session, organization_id: uuid.UUID, name: str = "Test Site") -> Site:
    site = Site(organization_id=organization_id, name=name)
    db_session.add(site)
    db_session.commit()
    return site


def make_raw_payload(**overrides) -> RawSafetyEventPayload:
    defaults = dict(
        event_type="INCIDENT",
        event_time="2026-06-01T00:00:00Z",
        source_system="test-system",
        source_record_id=str(uuid.uuid4()),
    )
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)
