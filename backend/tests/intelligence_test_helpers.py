"""Shared test helpers for the intelligence & predictive analytics test
suite — mirrors `tests/rag_test_helpers.py`'s "build the domain object
with sane defaults, override what the test cares about" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.intelligence.schemas import RawSafetyEventPayload
from app.models.ontology_concept import OntologyConcept
from app.models.organization import Organization
from app.models.safety_event import SafetyEvent
from app.models.site import Site
from app.models.user import User
from app.risk_assessment.risk_area_ontology_seed import RISK_AREA_SEED_CONCEPTS, RISK_AREA_SEED_ONTOLOGY_VERSION
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services import ontology_governance_service as ogs
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
    """Seeds the 11 GLOBAL, `APPROVED`, `is_risk_area_eligible`
    ontology concepts SIE Milestone 25A's migration 0017 seeds on a real
    Postgres database. The SQLite `client`/`db_session` test fixtures
    build their schema straight from the SQLAlchemy models
    (`Base.metadata.create_all()` -- see `tests/conftest.py`'s own
    docstring), which never runs a migration's own data-seeding step, so
    any test exercising a governed risk area needs this fixture first.
    Returns `{legacy_risk_area: concept_id}` so a test can build a
    `risk_area_concept_id` request body value by the same familiar name
    Milestone 25 originally used. Mirrors migration 0017's own seed list
    (`app/risk_assessment/risk_area_ontology_seed.py`) exactly, but
    through the real, unmodified `ontology_governance_service.py`
    lifecycle (`propose_concept()`/`approve_concept()`) rather than raw
    SQL -- a test fixture has no reason to bypass the one real
    governance path."""
    admin = make_platform_admin_user(db_session, name="Ontology Seed Admin")
    concept_ids: dict[str, uuid.UUID] = {}
    for seed in RISK_AREA_SEED_CONCEPTS:
        concept = ogs.propose_concept(
            db_session, layer=seed.layer, parent_domain=seed.parent_domain, concept_key=seed.concept_key,
            definition=seed.definition, justification=seed.justification, acting_user_id=admin.id,
            is_risk_area_eligible=True,
        )
        ogs.approve_concept(
            db_session, concept_id=concept.id, acting_user_id=admin.id, ontology_version=RISK_AREA_SEED_ONTOLOGY_VERSION
        )
        concept_ids[seed.legacy_risk_area] = concept.id
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
    """Builds an ontology concept at any governance state (`PROPOSED`/
    `APPROVED`/`REJECTED`/`DEPRECATED`), GLOBAL (`organization_id=None`)
    or organization-specific -- the general-purpose fixture for SIE
    Milestone 25A's governance-state and tenant-isolation tests. Goes
    through the real, unmodified lifecycle (never sets `status` directly)."""
    concept = ogs.propose_concept(
        db_session, layer=layer, parent_domain=parent_domain, concept_key=concept_key, definition=definition,
        justification=justification, acting_user_id=acting_user_id, organization_id=organization_id,
        is_risk_area_eligible=is_risk_area_eligible,
    )
    if status == "PROPOSED":
        return concept
    if status == "APPROVED":
        return ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=acting_user_id, ontology_version=ontology_version)
    if status == "REJECTED":
        return ogs.reject_concept(db_session, concept_id=concept.id, acting_user_id=acting_user_id, reason="Test rejection.")
    if status == "DEPRECATED":
        ogs.approve_concept(db_session, concept_id=concept.id, acting_user_id=acting_user_id, ontology_version=ontology_version)
        return ogs.deprecate_concept(db_session, concept_id=concept.id, acting_user_id=acting_user_id, reason="Test deprecation.")
    raise ValueError(f"Unrecognized status {status!r}.")


def make_raw_payload(**overrides) -> RawSafetyEventPayload:
    defaults = dict(
        event_type="INCIDENT",
        event_time="2026-06-01T00:00:00Z",
        source_system="test-system",
        source_record_id=str(uuid.uuid4()),
    )
    defaults.update(overrides)
    return RawSafetyEventPayload(**defaults)
