"""SafetyEventIngestionService — milestone items 8, 11, 38, 46. Runs
against the ordinary SQLite `db_session` fixture — nothing here needs
pgvector.
"""

import uuid

from app.intelligence.adapters import GenericJSONAdapter
from app.intelligence.enums import IngestionOutcome
from app.intelligence.ingestion_service import safety_event_ingestion_service
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from tests.intelligence_test_helpers import make_raw_payload

adapter = GenericJSONAdapter()


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Ingestion Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


# --- Single event -------------------------------------------------------------------


def test_ingesting_a_new_event_creates_a_row(db_session):
    org_id = _make_org(db_session)
    result = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=make_raw_payload(), adapter=adapter
    )
    assert result.outcome == IngestionOutcome.CREATED
    assert result.event_id is not None
    stored = db_session.get(SafetyEvent, result.event_id)
    assert stored.organization_id == org_id
    assert stored.data_quality_status == "VALID"


def test_rejected_invalid_payload_writes_no_row(db_session):
    org_id = _make_org(db_session)
    result = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=make_raw_payload(source_system=None), adapter=adapter
    )
    assert result.outcome == IngestionOutcome.REJECTED_INVALID
    assert result.event_id is None
    assert db_session.query(SafetyEvent).count() == 0


def test_quarantined_payload_is_still_stored(db_session):
    org_id = _make_org(db_session)
    result = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=make_raw_payload(event_time=None), adapter=adapter
    )
    assert result.outcome == IngestionOutcome.CREATED
    stored = db_session.get(SafetyEvent, result.event_id)
    assert stored.data_quality_status == "QUARANTINED"


# --- Idempotency (milestone item 11) -------------------------------------------------


def test_resending_the_identical_record_is_idempotent_not_duplicated(db_session):
    org_id = _make_org(db_session)
    payload = make_raw_payload(source_record_id="OBS-2026-00125")

    first = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=payload, adapter=adapter
    )
    second = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=payload, adapter=adapter
    )

    assert first.outcome == IngestionOutcome.CREATED
    assert second.outcome == IngestionOutcome.SKIPPED_IDEMPOTENT
    assert second.event_id == first.event_id
    assert db_session.query(SafetyEvent).count() == 1


def test_resending_with_changed_content_updates_in_place(db_session):
    org_id = _make_org(db_session)
    record_id = "OBS-2026-00125"

    first = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id,
        payload=make_raw_payload(source_record_id=record_id, severity="low"),
        adapter=adapter,
    )
    second = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id,
        payload=make_raw_payload(source_record_id=record_id, severity="critical"),
        adapter=adapter,
    )

    assert first.outcome == IngestionOutcome.CREATED
    assert second.outcome == IngestionOutcome.UPDATED
    assert second.event_id == first.event_id
    assert db_session.query(SafetyEvent).count() == 1
    stored = db_session.get(SafetyEvent, first.event_id)
    assert stored.severity == "CRITICAL"


def test_the_same_source_record_id_from_a_different_source_system_is_a_separate_event(db_session):
    org_id = _make_org(db_session)
    a = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id,
        payload=make_raw_payload(source_system="system-a", source_record_id="1"), adapter=adapter,
    )
    b = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id,
        payload=make_raw_payload(source_system="system-b", source_record_id="1"), adapter=adapter,
    )
    assert a.event_id != b.event_id
    assert db_session.query(SafetyEvent).count() == 2


def test_the_same_source_record_id_in_a_different_organization_is_a_separate_event(db_session):
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    payload = make_raw_payload(source_record_id="shared-id")
    a = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_a, payload=payload, adapter=adapter
    )
    b = safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_b, payload=payload, adapter=adapter
    )
    assert a.event_id != b.event_id


# --- Batch ingestion (milestone item 38) ---------------------------------------------


def test_batch_ingestion_reports_per_record_outcomes_and_a_summary(db_session):
    org_id = _make_org(db_session)
    payloads = [
        make_raw_payload(source_record_id="a"),
        make_raw_payload(source_record_id="b", event_time=None),  # quarantined, still created
        make_raw_payload(source_record_id=None),  # rejected
    ]
    result = safety_event_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, payloads=payloads, adapter=adapter
    )
    assert result.created_count == 2
    assert result.rejected_count == 1
    assert len(result.records) == 3


def test_one_malformed_record_does_not_abort_the_rest_of_the_batch(db_session):
    org_id = _make_org(db_session)
    payloads = [
        make_raw_payload(source_record_id="good-1"),
        make_raw_payload(source_record_id=None),  # malformed
        make_raw_payload(source_record_id="good-2"),
    ]
    result = safety_event_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, payloads=payloads, adapter=adapter
    )
    assert result.created_count == 2
    assert result.rejected_count == 1
    assert db_session.query(SafetyEvent).count() == 2


def test_a_repeated_record_within_the_same_batch_is_flagged_duplicate_in_batch(db_session):
    org_id = _make_org(db_session)
    payloads = [
        make_raw_payload(source_record_id="dup", severity="low"),
        make_raw_payload(source_record_id="dup", severity="high"),
    ]
    result = safety_event_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, payloads=payloads, adapter=adapter
    )
    assert result.duplicate_in_batch_count == 1
    assert result.records[0].duplicate_in_batch is False
    assert result.records[1].duplicate_in_batch is True
    # Still just one stored row -- last write wins, not two rows.
    assert db_session.query(SafetyEvent).count() == 1


# --- Audit (milestone item 46) --------------------------------------------------------


def test_single_event_ingestion_writes_one_audit_entry(db_session):
    org_id = _make_org(db_session)
    safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id, payload=make_raw_payload(), adapter=adapter
    )
    entries = db_session.query(AuditLog).filter(AuditLog.action == "SAFETY_EVENT_INGESTED").all()
    assert len(entries) == 1
    assert entries[0].organization_id == org_id
    assert entries[0].event_metadata["outcome"] == "CREATED"


def test_batch_ingestion_writes_one_summary_audit_entry_not_one_per_record(db_session):
    org_id = _make_org(db_session)
    payloads = [make_raw_payload(source_record_id=str(i)) for i in range(5)]
    safety_event_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, payloads=payloads, adapter=adapter
    )
    per_record_entries = db_session.query(AuditLog).filter(AuditLog.action == "SAFETY_EVENT_INGESTED").all()
    batch_entries = db_session.query(AuditLog).filter(AuditLog.action == "SAFETY_EVENT_BATCH_INGESTED").all()
    assert per_record_entries == []
    assert len(batch_entries) == 1
    assert batch_entries[0].event_metadata["record_count"] == 5
    assert batch_entries[0].event_metadata["created_count"] == 5


def test_audit_metadata_never_contains_the_raw_description(db_session):
    org_id = _make_org(db_session)
    safety_event_ingestion_service.ingest_event(
        db_session, organization_id=org_id,
        payload=make_raw_payload(description="Jane Doe was injured on shift."), adapter=adapter,
    )
    entry = db_session.query(AuditLog).filter(AuditLog.action == "SAFETY_EVENT_INGESTED").one()
    assert "Jane Doe" not in str(entry.event_metadata)
