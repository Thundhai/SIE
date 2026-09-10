"""Real-data safety tests — SIE Enterprise Ontology & Data Model
Expansion v0.1. Proves that building the ontology governance layer
cannot accidentally mutate real enterprise data: no automatic
reprocessing, no call to `reprocess_quarantined_records()`, no
modification of any existing `SafetyEvent` or `TerminologyMappingDecision`
row, and no loading of the real enterprise workbook. All fixtures here
are synthetic. Requires real PostgreSQL (`@requires_postgres`,
`pg_session`) for the runtime checks; the static checks need no
database.
"""

from __future__ import annotations

import inspect

from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
from app.intelligence.schemas import RawSafetyEventPayload
from app.intelligence.terminology_calibration_adapter import (
    CalibratedTerminologyMappingAdapter,
)
from app.models.safety_event import SafetyEvent
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.services import ontology_concept_artifact_service, ontology_governance_service
from app.services.ontology_concept_artifact_service import (
    apply_ontology_concept_artifact,
)
from tests.intelligence_test_helpers import make_org, make_platform_admin_user
from tests.postgres_support import requires_postgres

# --- Static checks: neither new module references the forbidden operations ----------------------


def test_ontology_governance_service_never_imports_reprocessing_or_the_real_loader():
    """The meaningful safety property: neither module IMPORTS
    `reprocess_quarantined_records`, `terminology_reprocessing_service`,
    or `real_dataset_loader` at all -- if it isn't imported, it cannot be
    called. (Both modules' own docstrings *mention* `reprocess_quarantined_records()`
    in prose, by design, to document that it is never called -- that
    prose mention is expected and is not itself a safety issue, so this
    check inspects actual `import` statements, not free text.)"""
    for module in (ontology_governance_service, ontology_concept_artifact_service):
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            module_path = getattr(value, "__module__", None)
            if module_path:
                assert "terminology_reprocessing_service" not in module_path
                assert "real_dataset_loader" not in module_path
        import_lines = [line for line in inspect.getsource(module).splitlines() if line.startswith(("import ", "from "))]
        joined = "\n".join(import_lines)
        assert "terminology_reprocessing_service" not in joined
        assert "real_dataset_loader" not in joined


# --- Runtime checks: applying the ontology artifact touches nothing real -------------------------


@requires_postgres
def test_applying_the_ontology_artifact_does_not_modify_a_pre_existing_safety_event(pg_session):
    """Ingests one synthetic, already-classified SafetyEvent BEFORE
    applying the ontology artifact, then proves it is byte-for-byte
    unchanged afterward -- the same guarantee the milestone requires for
    the real dataset's own 13 previously-reprocessed records, verified
    here against a synthetic stand-in (the real workbook is never loaded
    in this test suite)."""
    org = make_org(pg_session, "Ontology Real-Data Safety - Pre-existing Event")
    enterprise_ingestion_service.ingest_batch(
        pg_session, organization_id=org.id,
        payloads=[RawSafetyEventPayload(
            event_type="Injury", event_time="2026-01-01T00:00:00Z", source_system="synthetic-hse-xlsx",
            source_record_id="PRE-EXISTING-1",
        )],
        adapter=CalibratedTerminologyMappingAdapter(), source_id=None,
    )
    before = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "PRE-EXISTING-1").one()
    before_snapshot = (before.event_type, before.event_subtype, before.data_quality_status, before.ingestion_time, before.updated_at)

    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)

    pg_session.expire_all()
    after = pg_session.query(SafetyEvent).filter(SafetyEvent.source_record_id == "PRE-EXISTING-1").one()
    after_snapshot = (after.event_type, after.event_subtype, after.data_quality_status, after.ingestion_time, after.updated_at)
    assert before_snapshot == after_snapshot


@requires_postgres
def test_applying_the_ontology_artifact_does_not_modify_a_pre_existing_terminology_decision(pg_session):
    from app.services import terminology_calibration_service as svc
    from tests.intelligence_test_helpers import make_org_member

    org = make_org(pg_session, "Ontology Real-Data Safety - Pre-existing Decision")
    org_admin = make_org_member(pg_session, org.id)
    from app.intelligence.terminology_review import (
        TerminologyReviewEntry,
        TerminologyReviewStatus,
    )

    entry = TerminologyReviewEntry(
        domain="event_type", context=None, source_term="QuasiPreExisting", proposed_canonical_term=None,
        status=TerminologyReviewStatus.UNKNOWN, reason="r", occurrence_count=1,
    )
    created = svc.create_review_candidates(pg_session, organization_id=org.id, source_system="synthetic-hse-xlsx", entries=[entry])
    proposed = svc.propose_mapping(
        pg_session, organization_id=org.id, decision_id=created[0].id, proposed_canonical_term="INCIDENT",
        rationale="r", acting_user_id=org_admin.id,
    )
    approved = svc.approve_mapping(pg_session, organization_id=org.id, decision_id=proposed.id, acting_user_id=org_admin.id)
    before_snapshot = (approved.status, approved.proposed_canonical_term, approved.mapping_version, approved.decided_at)

    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)

    pg_session.expire_all()
    after = pg_session.query(TerminologyMappingDecision).filter(TerminologyMappingDecision.id == approved.id).one()
    after_snapshot = (after.status, after.proposed_canonical_term, after.mapping_version, after.decided_at)
    assert before_snapshot == after_snapshot


@requires_postgres
def test_the_real_enterprise_decision_artifact_is_completely_unaffected_by_the_ontology_artifact(pg_session):
    """The 3 previously-approved real-dataset decisions
    (NearMiss/PropertyDamage/VehicleAccident) and the 15 rejected ones
    are represented ONLY by backend/config/real_enterprise_terminology_decisions_v1.json
    (unchanged by this milestone -- see the milestone's own instruction
    'must remain unchanged unless there is a compelling technical
    reason'). This test proves applying the NEW ontology artifact does
    not touch that file or its own apply mechanism at all."""
    import hashlib

    from app.services.terminology_decision_artifact_service import (
        DEFAULT_ARTIFACT_PATH as TERMINOLOGY_ARTIFACT_PATH,
    )

    before_hash = hashlib.sha256(TERMINOLOGY_ARTIFACT_PATH.read_bytes()).hexdigest()

    admin = make_platform_admin_user(pg_session)
    apply_ontology_concept_artifact(pg_session, acting_user_id=admin.id)

    after_hash = hashlib.sha256(TERMINOLOGY_ARTIFACT_PATH.read_bytes()).hexdigest()
    assert before_hash == after_hash
