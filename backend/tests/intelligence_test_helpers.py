"""Shared test helpers for the intelligence & predictive analytics test
suite — mirrors `tests/rag_test_helpers.py`'s "build the domain object
with sane defaults, override what the test cares about" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.intelligence.schemas import RawSafetyEventPayload
from app.models.ontology_concept import OntologyConcept, OntologyConceptStatus
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from app.models.site import Site
from app.models.user import User
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.membership_service import membership_service
from app.services.permissions import PLATFORM_ADMIN, OrganizationRole
from app.services.user_service import user_service


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


def make_reviewer_user(db_session: Session, name: str = "Reviewer") -> User:
    """A real `User` row for tests exercising `model_registry.py::approve()`/
    `reject()`, which require a genuine `reviewer_user_id` (milestone item
    23: the model can never approve itself) — not just any UUID."""
    return user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name=name))


def make_platform_admin_user(db_session: Session, name: str = "Platform Admin") -> User:
    """A `User` with `platform_role == PLATFORM_ADMIN` — the one identity
    that can write GLOBAL knowledge (see `app/api/v1/knowledge.py`'s own
    docstring, mirroring `app/api/v1/ingestion.py`'s established rule)."""
    user = user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name=name))
    return user_service.set_platform_role(db_session, user=user, platform_role=PLATFORM_ADMIN)


def make_org_member(
    db_session: Session, organization_id: uuid.UUID, *, role: OrganizationRole = OrganizationRole.ORG_ADMIN, name: str = "Member"
) -> User:
    """A `User` with an ACTIVE `OrganizationMembership` in `organization_id`
    under `role` — the general-purpose "an authenticated, authorized human
    caller" fixture every HTTP-layer test in this suite needs."""
    user = user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name=name))
    membership_service.create(
        db_session, organization_id=organization_id, obj_in=OrganizationMembershipCreate(user_id=user.id, role=role)
    )
    return user


def seed_risk_area_ontology_concepts(db_session: Session) -> dict[str, uuid.UUID]:
    """M43-IP-03: the real ontology-governance lifecycle
    (`propose_concept()`/`approve_concept()`) and the proprietary risk-
    area taxonomy seed data this fixture used to replay through it have
    both been extracted to the private Commercial Core repository (the
    governance workflow is private business logic; the seed list is
    proprietary taxonomy data -- see docs/M43_IP_03_PUBLIC_EXTRACTION.md).
    Public SIE's own `resolve_risk_area_concept()`
    (`app/risk_assessment/risk_area_resolution.py`, kept, reclassified
    PUBLIC by that same milestone) only cares that a row exists with
    `status=APPROVED` and `is_risk_area_eligible=True` -- it never
    replays a governance history -- so this fixture builds a small,
    synthetic set of GLOBAL rows directly via the ORM instead. Returns
    `{legacy_risk_area: concept_id}`, same shape as before."""
    concept_ids: dict[str, uuid.UUID] = {}
    for legacy_risk_area, concept_key in (
        ("dropped_objects", "DROPPED_OBJECTS"),
        ("confined_space", "CONFINED_SPACE"),
        ("working_at_height", "WORKING_AT_HEIGHT"),
        ("vehicle_incident", "VEHICLE_INCIDENT"),  # tests/test_risk_assessment_api.py's own default
        ("ppe_compliance", "PPE_COMPLIANCE"),  # used by tests/test_risk_assessment_report.py
    ):
        concept = OntologyConcept(
            organization_id=None,
            layer="observation_topic",
            parent_domain="OBSERVATION",
            concept_key=concept_key,
            definition=f"Synthetic fixture risk-area concept ({concept_key}).",
            justification="Test fixture -- not a real governance decision.",
            status=OntologyConceptStatus.APPROVED,
            is_risk_area_eligible=True,
            ontology_version=1,
        )
        db_session.add(concept)
        db_session.commit()
        concept_ids[legacy_risk_area] = concept.id
    concept_ids["VEHICLE_SAFETY"] = concept_ids["vehicle_incident"]  # tests/test_risk_assessment_transaction_integrity.py's own legacy alias
    return concept_ids


def make_org_ontology_concept(
    db_session: Session,
    organization_id: uuid.UUID | None,
    *,
    acting_user_id: uuid.UUID,
    layer: str = "observation_topic",
    parent_domain: str | None = "OBSERVATION",
    concept_key: str = "DROPPED_OBJECTS",
    status: str = "APPROVED",
    is_risk_area_eligible: bool = True,
    definition: str = "Synthetic fixture risk-area concept.",
    justification: str = "Test evidence.",
    ontology_version: int = 1,
) -> OntologyConcept:
    """M43-IP-03: builds an `OntologyConcept` row directly at the
    requested governance state (`PROPOSED`/`APPROVED`/`REJECTED`/
    `DEPRECATED`), GLOBAL (`organization_id=None`) or organization-
    specific. Previously replayed the real `ontology_governance_service`
    lifecycle (`propose_concept()`/`approve_concept()`/...); that service
    is now private (extracted to Commercial Core), so this fixture
    constructs the row's fields directly instead -- `OntologyConcept`
    itself is a kept, public data model (see
    docs/M43_IP_03_PUBLIC_EXTRACTION.md), only its governance *workflow*
    moved. `acting_user_id` is accepted for call-site compatibility but
    unused (no audit trail is written by this direct-construction path)."""
    now = datetime.now(timezone.utc)
    concept = OntologyConcept(
        organization_id=organization_id,
        layer=layer,
        parent_domain=parent_domain,
        concept_key=concept_key,
        definition=definition,
        justification=justification,
        is_risk_area_eligible=is_risk_area_eligible,
        proposed_by_user_id=acting_user_id,
        proposed_at=now,
    )
    if status == "PROPOSED":
        concept.status = OntologyConceptStatus.PROPOSED
    elif status == "APPROVED":
        concept.status = OntologyConceptStatus.APPROVED
        concept.reviewer_user_id = acting_user_id
        concept.decided_at = now
        concept.ontology_version = ontology_version
    elif status == "REJECTED":
        concept.status = OntologyConceptStatus.REJECTED
        concept.reviewer_user_id = acting_user_id
        concept.decided_at = now
    elif status == "DEPRECATED":
        concept.status = OntologyConceptStatus.DEPRECATED
        concept.reviewer_user_id = acting_user_id
        concept.decided_at = now
        concept.ontology_version = ontology_version
    else:
        raise ValueError(f"Unrecognized status {status!r}.")
    db_session.add(concept)
    db_session.commit()
    return concept


def make_raw_payload(**overrides) -> RawSafetyEventPayload:
    defaults = dict(
        event_type="INCIDENT",
        event_time="2026-06-01T00:00:00Z",
        source_system="test-system",
        source_record_id=str(uuid.uuid4()),
    )
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)


def make_authorized_user(db_session: Session, organization_id: uuid.UUID, role: OrganizationRole = OrganizationRole.HSE_MANAGER) -> User:
    """M43-IP-03: moved here from the now-deleted `tests/test_predictions_api.py`
    (private, extracted to Commercial Core) -- this specific
    name/signature/default-role combination is still needed by
    generic, non-private tests (`test_rate_limiting.py`,
    `test_request_size_limits.py`). Identical in effect to
    `make_org_member()` above, just with `HSE_MANAGER` as the default
    role instead of `ORG_ADMIN`."""
    return make_org_member(db_session, organization_id, role=role)
