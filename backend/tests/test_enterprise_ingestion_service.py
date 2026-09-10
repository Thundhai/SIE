"""Service-layer tests for the Enterprise Data Ingestion & Validation
Foundation v0.1 orchestration layer — validation states, deterministic
normalization pass-through, deduplication/source-record-versioning
scenarios (item 8's full checklist), and provenance (item 9).

Runs against `db_session` (SQLite) -- no pgvector needed for any of this
(structured record validation/normalization/upsert only).
"""

import uuid

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.enums import DataQualityStatus, IngestionOutcome
from app.intelligence.schemas import RawSafetyEventPayload
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Enterprise Ingestion Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _payload(**overrides) -> RawSafetyEventPayload:
    defaults = dict(
        event_type="INCIDENT",
        event_time="2026-01-01T00:00:00Z",
        source_system="sap-erp",
        source_record_id="INC-001",
    )
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)


# --- Validation states ----------------------------------------------------------------


def test_a_fully_valid_record_is_accepted_and_classified_valid(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload()]
    )
    assert result.batch.accepted_records == 1
    assert result.records[0].outcome == IngestionOutcome.CREATED.value
    assert result.records[0].quality_state == DataQualityStatus.VALID.value
    assert result.records[0].canonical_event_id is not None


def test_a_record_with_an_unrecognized_but_present_severity_is_partial(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload(severity="not-a-real-severity")]
    )
    assert result.batch.partial_records == 1
    assert result.records[0].quality_state == DataQualityStatus.PARTIAL.value
    assert result.records[0].canonical_event_id is not None


def test_a_record_missing_event_time_is_quarantined_but_still_stored(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload(event_time=None)]
    )
    assert result.batch.quarantined_records == 1
    assert result.records[0].quality_state == DataQualityStatus.QUARANTINED.value
    assert result.records[0].canonical_event_id is not None  # stored, per item 12 -- never silently dropped


def test_a_record_missing_identity_fields_is_rejected_with_no_canonical_event(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload(source_record_id=None)]
    )
    assert result.batch.rejected_records == 1
    record = result.records[0]
    assert record.outcome == IngestionOutcome.REJECTED_INVALID.value
    assert record.quality_state is None
    assert record.canonical_event_id is None
    # The one outcome where the payload is preserved on the record itself
    # (no canonical event exists to hold it) -- see the model's own docstring.
    assert record.payload is not None
    assert record.rejection_reason


def test_a_malformed_payload_never_aborts_the_rest_of_the_batch(db_session):
    org_id = _make_org(db_session)
    payloads = [_payload(source_record_id="ok-1"), _payload(event_type=None, source_record_id="bad"), _payload(source_record_id="ok-2")]
    result = enterprise_ingestion_service.ingest_batch(db_session, organization_id=org_id, source_id=None, payloads=payloads)
    assert result.batch.total_records == 3
    assert result.batch.accepted_records == 2
    assert result.batch.rejected_records == 1


# --- Deduplication / source-record versioning (item 8's full checklist) ---------------


def test_exact_replay_is_idempotent_and_never_creates_a_second_event(db_session):
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(db_session, organization_id=org_id, source_id=None, payloads=[_payload()])
    result = enterprise_ingestion_service.ingest_batch(db_session, organization_id=org_id, source_id=None, payloads=[_payload()])
    assert result.records[0].outcome == IngestionOutcome.SKIPPED_IDEMPOTENT.value
    assert result.batch.duplicate_records == 1
    count = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).count()
    assert count == 1


def test_same_external_id_with_the_same_version_and_unchanged_content_is_a_no_op(db_session):
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload(source_record_version="1")]
    )
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload(source_record_version="1")]
    )
    assert result.records[0].outcome == IngestionOutcome.SKIPPED_IDEMPOTENT.value


def test_same_external_id_with_a_newer_integer_version_applies_the_update(db_session):
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="1", description="first version")],
    )
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="2", description="second version")],
    )
    assert result.records[0].outcome == IngestionOutcome.UPDATED.value
    event = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).one()
    assert event.description == "second version"
    assert event.source_record_version == "2"


def test_same_external_id_with_a_conflicting_version_is_rejected_not_silently_applied(db_session):
    """Same declared version, different content -- SIE must never guess
    which is authoritative; the existing row stays exactly as it was."""
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="1", description="original")],
    )
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="1", description="a different claim under the same version")],
    )
    assert result.records[0].outcome == IngestionOutcome.REJECTED_VERSION_CONFLICT.value
    event = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).one()
    assert event.description == "original"  # completely untouched


def test_same_external_id_with_an_older_stale_version_is_skipped_not_applied(db_session):
    """An out-of-order, late-arriving older revision must never regress
    the canonical timeline back over a newer one already applied."""
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="5", description="already-applied newer version")],
    )
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="2", description="a stale, late-arriving older version")],
    )
    assert result.records[0].outcome == IngestionOutcome.SKIPPED_STALE_VERSION.value
    event = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).one()
    assert event.description == "already-applied newer version"  # untouched
    assert event.source_record_version == "5"


def test_non_numeric_versions_fall_back_to_the_documented_unversioned_behavior(db_session):
    """The safest-minimal-foundation limitation, made concrete: a
    non-integer-parseable version scheme (e.g. 'v2.1-rc') cannot be
    safely ordered, so ingestion falls back to today's exact
    content-hash-based last-write-wins behavior, never a guessed
    ordering."""
    org_id = _make_org(db_session)
    enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="v1-rc", description="first")],
    )
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="v2-rc", description="second")],
    )
    assert result.records[0].outcome == IngestionOutcome.UPDATED.value
    event = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).one()
    assert event.description == "second"


def test_different_external_ids_with_identical_payloads_remain_distinct_events(db_session):
    """Two genuinely distinct source records that happen to describe
    identical content must never be silently collapsed into one --
    identity is (source_system, source_record_id), never payload
    similarity."""
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="A-1"), _payload(source_record_id="A-2")],
    )
    assert result.batch.accepted_records == 2
    assert {r.canonical_event_id for r in result.records} == {r.canonical_event_id for r in result.records if r.canonical_event_id}
    assert len({r.canonical_event_id for r in result.records}) == 2
    count = db_session.query(SafetyEvent).filter(SafetyEvent.organization_id == org_id).count()
    assert count == 2


def test_duplicate_external_id_within_the_same_batch_is_flagged(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_id="dup"), _payload(source_record_id="dup")],
    )
    assert result.records[0].duplicate_in_batch is False
    assert result.records[1].duplicate_in_batch is True
    assert result.batch.error_summary["duplicate_in_batch_count"] == 1


# --- Provenance (item 9) ---------------------------------------------------------------


def test_every_created_event_traces_back_to_its_batch_and_record(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None,
        payloads=[_payload(source_record_version="7", correlation_id="TXN-9")],
    )
    record = result.records[0]
    event = db_session.get(SafetyEvent, record.canonical_event_id)

    assert record.batch_id == result.batch.id
    assert event.ingestion_batch_id == result.batch.id  # the pre-existing UUID column, matched by value
    assert event.source_record_version == "7"
    assert event.correlation_id == "TXN-9"
    assert record.content_hash == event.source_content_hash
    assert record.external_record_id == event.source_record_id


def test_batch_carries_received_timestamp_and_completed_status(db_session):
    org_id = _make_org(db_session)
    result = enterprise_ingestion_service.ingest_batch(
        db_session, organization_id=org_id, source_id=None, payloads=[_payload()]
    )
    assert result.batch.status == "COMPLETED"
    assert result.batch.received_at is not None
    assert result.batch.total_records == 1
