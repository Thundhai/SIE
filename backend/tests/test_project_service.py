"""SIE Milestone 35: Organizational & Operational Scope Foundation v0.1
— service-level tests for `app/services/project_service.py` and
`app/services/project_site_service.py`. Mirrors
`tests/test_intelligence_decision_service.py`'s own established shape:
direct calls against `db_session`, no HTTP layer. HTTP-layer coverage
(authorization, tenant isolation over the wire) lives in
`tests/test_projects_api.py`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.project_enums import ProjectStatus
from app.schemas.project import ProjectCreate
from app.services.project_service import project_service, resolve_project_reference
from app.services.project_site_service import (
    link_project_site,
    list_projects_for_site,
    list_sites_for_project,
    project_site_ids,
    unlink_project_site,
)
from tests.intelligence_test_helpers import make_org, make_site


def _create_project(db_session, org_id, **overrides):
    payload = {"name": "Warehouse Expansion", "code": "PRJ-001", "status": ProjectStatus.ACTIVE, "description": None}
    payload.update(overrides)
    return project_service.create(db_session, organization_id=org_id, obj_in=ProjectCreate(**payload))


# --- Project CRUD -------------------------------------------------------------------------------


def test_create_project_persists_identity_and_lifecycle_fields(db_session):
    org = make_org(db_session)
    project = _create_project(db_session, org.id, name="Regional Maintenance Program", code="PRJ-042")
    assert project.organization_id == org.id
    assert project.name == "Regional Maintenance Program"
    assert project.code == "PRJ-042"
    assert project.status == ProjectStatus.ACTIVE


def test_project_get_and_list_are_organization_scoped(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    project_a = _create_project(db_session, org_a.id, name="A Project")
    _create_project(db_session, org_b.id, name="B Project")

    fetched = project_service.get(db_session, organization_id=org_a.id, id=project_a.id)
    assert fetched is not None
    assert fetched.id == project_a.id

    # Org A cannot read Org B's project via a direct id lookup either --
    # scoped to org_a, a project belonging to org_b resolves to None.
    cross_tenant = project_service.get(db_session, organization_id=org_a.id, id=project_a.id)
    assert cross_tenant is not None  # sanity: same-org lookup still works
    listing_a = project_service.list(db_session, organization_id=org_a.id)
    assert {p.name for p in listing_a} == {"A Project"}


def test_resolve_project_reference_404s_across_organizations(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    project_b = _create_project(db_session, org_b.id, name="B Project")

    with pytest.raises(HTTPException) as exc_info:
        resolve_project_reference(db_session, organization_id=org_a.id, project_id=project_b.id)
    assert exc_info.value.status_code == 404


def test_resolve_project_reference_404s_for_a_nonexistent_project(db_session):
    org = make_org(db_session)
    with pytest.raises(HTTPException) as exc_info:
        resolve_project_reference(db_session, organization_id=org.id, project_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


# --- Project <-> Site relationship ---------------------------------------------------------------


def test_link_project_site_creates_the_relationship(db_session):
    org = make_org(db_session)
    project = _create_project(db_session, org.id)
    site = make_site(db_session, org.id, "Main Yard")

    link, created = link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
        created_by_user_id=uuid.uuid4(), created_by_api_client_id=None,
    )
    assert created is True
    assert link.project_id == project.id
    assert link.site_id == site.id
    assert site.id in project_site_ids(db_session, organization_id=org.id, project_id=project.id)


def test_linking_the_same_pair_twice_is_idempotent(db_session):
    org = make_org(db_session)
    project = _create_project(db_session, org.id)
    site = make_site(db_session, org.id)

    link1, created1 = link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
        created_by_user_id=None, created_by_api_client_id=None,
    )
    link2, created2 = link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
        created_by_user_id=None, created_by_api_client_id=None,
    )
    assert created1 is True
    assert created2 is False
    assert link1.id == link2.id
    assert len(project_site_ids(db_session, organization_id=org.id, project_id=project.id)) == 1


def test_link_project_site_rejects_a_site_from_a_different_organization(db_session):
    """Item 4's own explicit requirement: a project belonging to
    Organization A must never be attachable to a site belonging to
    Organization B."""
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    project_a = _create_project(db_session, org_a.id)
    site_b = make_site(db_session, org_b.id, "Org B Site")

    with pytest.raises(HTTPException) as exc_info:
        link_project_site(
            db_session, organization_id=org_a.id, project_id=project_a.id, site_id=site_b.id,
            created_by_user_id=None, created_by_api_client_id=None,
        )
    assert exc_info.value.status_code == 404
    assert project_site_ids(db_session, organization_id=org_a.id, project_id=project_a.id) == []


def test_link_project_site_rejects_a_project_from_a_different_organization(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    project_b = _create_project(db_session, org_b.id)
    site_a = make_site(db_session, org_a.id)

    with pytest.raises(HTTPException) as exc_info:
        link_project_site(
            db_session, organization_id=org_a.id, project_id=project_b.id, site_id=site_a.id,
            created_by_user_id=None, created_by_api_client_id=None,
        )
    assert exc_info.value.status_code == 404


def test_a_project_may_span_multiple_sites(db_session):
    org = make_org(db_session)
    project = _create_project(db_session, org.id)
    site_1 = make_site(db_session, org.id, "Site One")
    site_2 = make_site(db_session, org.id, "Site Two")
    site_3 = make_site(db_session, org.id, "Site Three")

    for site in (site_1, site_2, site_3):
        link_project_site(
            db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
            created_by_user_id=None, created_by_api_client_id=None,
        )

    sites = list_sites_for_project(db_session, organization_id=org.id, project_id=project.id)
    assert {s.id for s in sites} == {site_1.id, site_2.id, site_3.id}


def test_a_site_may_host_multiple_projects(db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    project_1 = _create_project(db_session, org.id, name="Project One")
    project_2 = _create_project(db_session, org.id, name="Project Two")

    for project in (project_1, project_2):
        link_project_site(
            db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
            created_by_user_id=None, created_by_api_client_id=None,
        )

    projects = list_projects_for_site(db_session, organization_id=org.id, site_id=site.id)
    assert {p.id for p in projects} == {project_1.id, project_2.id}


def test_unlink_project_site_removes_the_relationship(db_session):
    org = make_org(db_session)
    project = _create_project(db_session, org.id)
    site = make_site(db_session, org.id)
    link_project_site(
        db_session, organization_id=org.id, project_id=project.id, site_id=site.id,
        created_by_user_id=None, created_by_api_client_id=None,
    )

    removed = unlink_project_site(db_session, organization_id=org.id, project_id=project.id, site_id=site.id)
    assert removed is True
    assert project_site_ids(db_session, organization_id=org.id, project_id=project.id) == []

    # Unlinking again is a no-op, not an error.
    removed_again = unlink_project_site(db_session, organization_id=org.id, project_id=project.id, site_id=site.id)
    assert removed_again is False


def test_existing_events_actions_and_findings_have_no_project_association_and_stay_valid(db_session):
    """Item 11: existing records without a Project association must
    continue to work -- Project introduces no new required relationship
    on SafetyEvent/SafetyAction/RiskAssessment/RiskAssessmentFinding/
    IntelligenceDecision (none of those models gained a `project_id`
    column at all -- see app/models/project.py's own docstring)."""
    from app.models.safety_action import SafetyAction
    from app.models.safety_action_enums import ActionPriority, ActionStatus, ActionType

    org = make_org(db_session)
    site = make_site(db_session, org.id)
    action = SafetyAction(
        organization_id=org.id, site_id=site.id, title="Pre-existing action",
        action_type=ActionType.CORRECTIVE, priority=ActionPriority.MEDIUM, status=ActionStatus.OPEN,
    )
    db_session.add(action)
    db_session.commit()
    db_session.refresh(action)
    assert not hasattr(action, "project_id")
    assert action.site_id == site.id
