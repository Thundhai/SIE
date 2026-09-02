"""Deterministic terminology mapping — Real-World Data Validation &
Intelligence Calibration v0.1, item 4. Runs against `db_session`
(SQLite) — no pgvector needed for any of this.
"""

import uuid

from app.intelligence.enums import DataQualityStatus, SafetyEventType
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_mapping import (
    MappingOutcome,
    TerminologyMappingAdapter,
    map_event_subtype,
    map_event_type,
    map_maintenance_status,
    map_training_status,
)
from app.models.organization import Organization


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="Terminology Mapping Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


# --- event_type: known aliases across heterogeneous spellings --------------------------


def test_near_miss_resolves_from_every_realistic_spelling():
    for raw in ("Near Miss", "Near-Miss", "near_miss", "NM", "nm", "Potential Incident", "close call"):
        result = map_event_type(raw)
        assert result.outcome == MappingOutcome.MAPPED, raw
        assert result.canonical_value == SafetyEventType.NEAR_MISS.value


def test_incident_types_resolve_to_the_canonical_domain():
    for raw in ("Incident", "Safety Incident", "injury"):
        result = map_event_type(raw)
        assert result.outcome == MappingOutcome.MAPPED
        assert result.canonical_value == SafetyEventType.INCIDENT.value


def test_permit_to_work_aliases_resolve():
    for raw in ("Permit", "Permit To Work", "PTW", "ptw"):
        assert map_event_type(raw).canonical_value == SafetyEventType.PERMIT.value


def test_maintenance_and_equipment_terminology_both_resolve_to_equipment():
    assert map_event_type("Equipment").canonical_value == SafetyEventType.EQUIPMENT.value
    assert map_event_type("Maintenance").canonical_value == SafetyEventType.EQUIPMENT.value
    assert map_event_type("Asset").canonical_value == SafetyEventType.EQUIPMENT.value


# --- event_type: ambiguity is flagged, never guessed ------------------------------------


def test_a_genuinely_ambiguous_term_is_flagged_not_guessed():
    result = map_event_type("finding")
    assert result.outcome == MappingOutcome.AMBIGUOUS
    assert set(result.candidates) == {"AUDIT", "INSPECTION"}
    assert result.canonical_value is None  # never a guessed single answer


def test_an_unrecognized_term_is_unknown_not_a_fallback_guess():
    result = map_event_type("completely made up terminology xyz123")
    assert result.outcome == MappingOutcome.UNKNOWN
    assert result.canonical_value is None


def test_none_and_empty_input_are_unknown():
    assert map_event_type(None).outcome == MappingOutcome.UNKNOWN
    assert map_event_type("").outcome == MappingOutcome.UNKNOWN
    assert map_event_type("   ").outcome == MappingOutcome.UNKNOWN


# --- event_subtype: domain-scoped resolution ---------------------------------------------


def test_incident_subtype_aliases_resolve_within_the_incident_domain():
    cases = {
        "First Aid Case": "FIRST_AID_CASE",
        "FAC": "FIRST_AID_CASE",
        "Medical Treatment Case": "MEDICAL_TREATMENT_CASE",
        "Lost Time Incident": "LOST_TIME_INCIDENT",
        "LTI": "LOST_TIME_INCIDENT",
        "Vehicle Incident": "VEHICLE_INCIDENT",
        "MVA": "VEHICLE_INCIDENT",
        "Property Damage": "PROPERTY_DAMAGE",
        "Environmental Event": "ENVIRONMENTAL_EVENT",
    }
    for raw, expected in cases.items():
        result = map_event_subtype(SafetyEventType.INCIDENT.value, raw)
        assert result.outcome == MappingOutcome.MAPPED, raw
        assert result.canonical_value == expected


def test_near_miss_subtype_aliases_resolve():
    cases = {
        "Dropped Object": "DROPPED_OBJECT",
        "Vehicle Near Miss": "VEHICLE_NEAR_MISS",
        "Fall From Height Near Miss": "FALL_FROM_HEIGHT_NEAR_MISS",
        "Process Deviation": "PROCESS_DEVIATION",
    }
    for raw, expected in cases.items():
        assert map_event_subtype(SafetyEventType.NEAR_MISS.value, raw).canonical_value == expected


def test_observation_subtype_aliases_resolve():
    cases = {
        "Unsafe Act": "UNSAFE_ACT",
        "Unsafe Condition": "UNSAFE_CONDITION",
        "Positive Observation": "POSITIVE_OBSERVATION",
        "Housekeeping Deficiency": "HOUSEKEEPING_DEFICIENCY",
        "PPE Issue": "PPE_ISSUE",
    }
    for raw, expected in cases.items():
        assert map_event_subtype(SafetyEventType.OBSERVATION.value, raw).canonical_value == expected


def test_inspection_subtype_aliases_resolve():
    cases = {
        "Equipment Inspection": "EQUIPMENT_INSPECTION",
        "Site Inspection": "SITE_INSPECTION",
        "Safety Inspection": "SAFETY_INSPECTION",
        "Environmental Inspection": "ENVIRONMENTAL_INSPECTION",
    }
    for raw, expected in cases.items():
        assert map_event_subtype(SafetyEventType.INSPECTION.value, raw).canonical_value == expected


def test_audit_finding_subtype_aliases_resolve():
    cases = {
        "Compliance Finding": "COMPLIANCE_FINDING",
        "Management System Finding": "MANAGEMENT_SYSTEM_FINDING",
        "Repeat Finding": "REPEAT_FINDING",
        "Recurring Finding": "REPEAT_FINDING",
    }
    for raw, expected in cases.items():
        assert map_event_subtype(SafetyEventType.AUDIT.value, raw).canonical_value == expected


def test_permit_subtype_aliases_resolve():
    cases = {
        "Hot Work": "HOT_WORK",
        "Confined Space": "CONFINED_SPACE",
        "Work At Height": "WORK_AT_HEIGHT",
        "Lifting Operation": "LIFTING_OPERATION",
    }
    for raw, expected in cases.items():
        assert map_event_subtype(SafetyEventType.PERMIT.value, raw).canonical_value == expected


def test_subtype_resolution_is_domain_scoped_not_global():
    """The same raw term means nothing under a domain that has no
    curated subtype table for it -- resolution never falls back to
    searching every domain's table."""
    result = map_event_subtype(SafetyEventType.WORKFORCE.value, "Hot Work")
    assert result.outcome == MappingOutcome.UNKNOWN


def test_a_subtype_ambiguous_within_one_domain_is_flagged():
    result = map_event_subtype(SafetyEventType.INCIDENT.value, "damage")
    assert result.outcome == MappingOutcome.AMBIGUOUS
    assert set(result.candidates) == {"PROPERTY_DAMAGE", "VEHICLE_INCIDENT"}


# --- Training status / maintenance status ------------------------------------------------


def test_training_status_aliases_resolve():
    cases = {
        "Completed": "COMPLETED",
        "Training Complete": "COMPLETED",
        "Overdue": "OVERDUE",
        "Overdue Training": "OVERDUE",
        "Competency Gap": "COMPETENCY_GAP",
        "Skills Gap": "COMPETENCY_GAP",
        "Expired Certification": "EXPIRED_CERTIFICATION",
        "Expired Cert": "EXPIRED_CERTIFICATION",
    }
    for raw, expected in cases.items():
        assert map_training_status(raw).canonical_value == expected


def test_maintenance_status_aliases_resolve():
    cases = {
        "Overdue Preventive Maintenance": "OVERDUE_PREVENTIVE_MAINTENANCE",
        "Overdue PM": "OVERDUE_PREVENTIVE_MAINTENANCE",
        "Maintenance Backlog": "OVERDUE_PREVENTIVE_MAINTENANCE",
        "Equipment Failure": "EQUIPMENT_FAILURE",
        "Breakdown": "EQUIPMENT_FAILURE",
    }
    for raw, expected in cases.items():
        assert map_maintenance_status(raw).canonical_value == expected


def test_unrecognized_training_and_maintenance_terms_are_unknown():
    assert map_training_status("some bespoke internal code XJ9").outcome == MappingOutcome.UNKNOWN
    assert map_maintenance_status("some bespoke internal code XJ9").outcome == MappingOutcome.UNKNOWN


# --- The adapter: mapping is actually wired into a real ingestion run --------------------


def test_adapter_maps_heterogeneous_terminology_into_the_canonical_type(db_session):
    org_id = _make_org(db_session)
    adapter = TerminologyMappingAdapter()
    result = adapter.ingest(
        db_session,
        organization_id=org_id,
        raw=RawSafetyEventPayload(
            event_type="Near Miss",
            event_subtype="Dropped Object",
            event_time="2026-01-01T00:00:00Z",
            source_system="legacy-ehs",
            source_record_id="rec-1",
        ),
        batch_id=uuid.uuid4(),
    )
    from app.models.safety_event import SafetyEvent

    event = db_session.get(SafetyEvent, result.event_id)
    assert event.event_type == "NEAR_MISS"
    assert event.event_subtype == "DROPPED_OBJECT"
    # The original, unmapped terminology is never lost.
    assert event.source_value["event_type"] == "Near Miss"
    assert event.source_value["event_subtype"] == "Dropped Object"
    assert event.data_quality_status == DataQualityStatus.VALID.value


def test_adapter_quarantines_an_ambiguous_event_type_rather_than_guessing(db_session):
    org_id = _make_org(db_session)
    adapter = TerminologyMappingAdapter()
    result = adapter.ingest(
        db_session,
        organization_id=org_id,
        raw=RawSafetyEventPayload(
            event_type="finding",  # ambiguous: AUDIT or INSPECTION
            event_time="2026-01-01T00:00:00Z",
            source_system="legacy-ehs",
            source_record_id="rec-ambiguous",
        ),
        batch_id=uuid.uuid4(),
    )
    from app.models.safety_event import SafetyEvent

    event = db_session.get(SafetyEvent, result.event_id)
    assert event is not None  # stored, per item 12 -- never silently dropped
    assert event.data_quality_status == DataQualityStatus.QUARANTINED.value
    assert any(issue["code"] == "AMBIGUOUS_EVENT_TYPE_MAPPING" for issue in event.data_quality_issues)
    # The unresolved raw terminology is preserved (case-normalized by
    # the existing, unmodified validate_and_normalize() pipeline, same
    # as any other unrecognized event_type) -- never silently assigned
    # to one of the ambiguous candidates.
    assert event.event_type == "FINDING"
    assert event.source_value["event_type"] == "finding"


def test_adapter_quarantines_an_unknown_event_type_rather_than_guessing(db_session):
    org_id = _make_org(db_session)
    adapter = TerminologyMappingAdapter()
    result = adapter.ingest(
        db_session,
        organization_id=org_id,
        raw=RawSafetyEventPayload(
            event_type="Zorbnak Category 7",
            event_time="2026-01-01T00:00:00Z",
            source_system="legacy-ehs",
            source_record_id="rec-unknown",
        ),
        batch_id=uuid.uuid4(),
    )
    from app.models.safety_event import SafetyEvent

    event = db_session.get(SafetyEvent, result.event_id)
    assert event.data_quality_status == DataQualityStatus.QUARANTINED.value
    assert any(issue["code"] == "UNKNOWN_EVENT_TYPE_MAPPING" for issue in event.data_quality_issues)


def test_a_quarantined_mapping_record_is_excluded_from_analytics_by_default(db_session):
    """Quarantined records must not silently become trusted intelligence
    (item 3's own scenario-D expectation) -- reuses the existing,
    unmodified events_as_of() exclusion rule."""
    org_id = _make_org(db_session)
    adapter = TerminologyMappingAdapter()
    adapter.ingest(
        db_session,
        organization_id=org_id,
        raw=RawSafetyEventPayload(
            event_type="finding",
            event_time="2026-01-01T00:00:00Z",
            source_system="legacy-ehs",
            source_record_id="rec-ambiguous-2",
        ),
        batch_id=uuid.uuid4(),
    )

    from datetime import datetime, timezone

    from app.intelligence.temporal import events_as_of

    visible = db_session.execute(
        events_as_of(organization_id=org_id, as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    ).scalars().all()
    assert visible == []


def test_adapter_still_rejects_records_missing_identity_fields(db_session):
    """The mapping layer adds a check; it never removes the existing
    ones -- a record with no source_record_id is still REJECTED_INVALID,
    exactly as it would be through GenericJSONAdapter."""
    org_id = _make_org(db_session)
    adapter = TerminologyMappingAdapter()
    result = adapter.ingest(
        db_session,
        organization_id=org_id,
        raw=RawSafetyEventPayload(
            event_type="Near Miss", event_time="2026-01-01T00:00:00Z", source_system="legacy-ehs",
            source_record_id=None,
        ),
        batch_id=uuid.uuid4(),
    )
    assert result.outcome.value == "REJECTED_INVALID"
    assert result.event_id is None
