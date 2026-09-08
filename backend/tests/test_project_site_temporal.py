"""SIE Milestone 36: Project/Site Temporal Scope Integrity — direct
`is_project_site_associated_as_of()`/`project_site_ids_as_of()`
query-level tests, mirroring `tests/test_project_attribution_temporal.py`'s
own established shape: construct `ProjectSiteHistory` rows directly with
explicit `created_at` values (the real write path always uses
`utcnow()` and cannot be backdated), call the temporal functions,
assert on the result. HTTP-layer coverage lives in
`tests/test_projects_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.intelligence.temporal import is_project_site_associated_as_of, project_site_ids_as_of
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_enums import ProjectStatus
from app.models.project_site_history import ProjectSiteHistory, ProjectSiteHistoryAction
from app.models.site import Site


def _make_org(db_session, name="M36 Temporal Test Org") -> uuid.UUID:
    org = Organization(name=name)
    db_session.add(org)
    db_session.commit()
    return org.id


def _make_project(db_session, org_id, name="Project") -> Project:
    project = Project(organization_id=org_id, name=name, status=ProjectStatus.ACTIVE)
    db_session.add(project)
    db_session.commit()
    return project


def _make_site(db_session, org_id, name="Site") -> Site:
    site = Site(organization_id=org_id, name=name)
    db_session.add(site)
    db_session.commit()
    return site


def _write_history(db_session, org_id, project_id, site_id, action, created_at) -> None:
    db_session.add(
        ProjectSiteHistory(
            organization_id=org_id, project_id=project_id, site_id=site_id, action=action, created_at=created_at
        )
    )
    db_session.commit()


def _associated(db_session, org_id, project_id, site_id, day) -> bool:
    return is_project_site_associated_as_of(
        db_session, organization_id=org_id, project_id=project_id, site_id=site_id,
        as_of=datetime(2026, 6, day, tzinfo=timezone.utc),
    )


# --- The user's own explicit worked example ------------------------------------------------


def test_full_worked_example_link_unlink_relink_different_project(db_session):
    """June 1: Alpha linked to Site A. June 20: Alpha unlinked. June 25:
    Beta linked to Site A. as_of=June 15 -> Alpha TRUE, Beta FALSE.
    as_of=June 22 -> Alpha FALSE. as_of=June 26 -> Beta TRUE."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    beta = _make_project(db_session, org_id, "Beta")
    site_a = _make_site(db_session, org_id, "Site A")

    _write_history(
        db_session, org_id, alpha.id, site_a.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, alpha.id, site_a.id, 15) is True
    assert _associated(db_session, org_id, beta.id, site_a.id, 15) is False

    _write_history(
        db_session, org_id, alpha.id, site_a.id, ProjectSiteHistoryAction.UNLINKED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, alpha.id, site_a.id, 22) is False

    _write_history(
        db_session, org_id, beta.id, site_a.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 25, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, beta.id, site_a.id, 26) is True
    # Alpha stays unassociated after its own unlink, regardless of Beta.
    assert _associated(db_session, org_id, alpha.id, site_a.id, 26) is False


def test_query_before_any_link_is_false(db_session):
    """Item 12: link -> historical query before link = false."""
    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, project.id, site.id, 5) is False


def test_query_after_link_is_true(db_session):
    """Item 13: link -> historical query after link = true."""
    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, project.id, site.id, 12) is True


def test_query_before_unlink_is_still_true(db_session):
    """Item 14: unlink -> historical query before unlink = true."""
    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.UNLINKED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, project.id, site.id, 10) is True


def test_query_after_unlink_is_false(db_session):
    """Item 15: unlink -> historical query after unlink = false."""
    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    _write_history(
        db_session, org_id, project.id, site.id, ProjectSiteHistoryAction.UNLINKED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    assert _associated(db_session, org_id, project.id, site.id, 25) is False


def test_multiple_projects_at_one_site_are_distinguished_independently(db_session):
    """Items 16-18: Alpha and Beta both linked to Site A (at different
    times); historical queries must distinguish them independently, and
    `project_site_ids_as_of()` must never conflate the two."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    beta = _make_project(db_session, org_id, "Beta")
    site_a = _make_site(db_session, org_id, "Site A")

    _write_history(
        db_session, org_id, alpha.id, site_a.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    _write_history(
        db_session, org_id, beta.id, site_a.id, ProjectSiteHistoryAction.LINKED,
        datetime(2026, 6, 5, tzinfo=timezone.utc),
    )

    as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
    assert is_project_site_associated_as_of(
        db_session, organization_id=org_id, project_id=alpha.id, site_id=site_a.id, as_of=as_of
    )
    assert is_project_site_associated_as_of(
        db_session, organization_id=org_id, project_id=beta.id, site_id=site_a.id, as_of=as_of
    )
    assert project_site_ids_as_of(db_session, organization_id=org_id, project_id=alpha.id, as_of=as_of) == [site_a.id]
    assert project_site_ids_as_of(db_session, organization_id=org_id, project_id=beta.id, as_of=as_of) == [site_a.id]

    # Unlinking Alpha must not affect Beta's own independent history.
    _write_history(
        db_session, org_id, alpha.id, site_a.id, ProjectSiteHistoryAction.UNLINKED,
        datetime(2026, 6, 12, tzinfo=timezone.utc),
    )
    later = datetime(2026, 6, 15, tzinfo=timezone.utc)
    assert not is_project_site_associated_as_of(
        db_session, organization_id=org_id, project_id=alpha.id, site_id=site_a.id, as_of=later
    )
    assert is_project_site_associated_as_of(
        db_session, organization_id=org_id, project_id=beta.id, site_id=site_a.id, as_of=later
    )


def test_no_history_at_all_is_false(db_session):
    """Preserves existing behavior: a project/site pair with no history
    row at all is correctly unassociated at any instant."""
    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    assert _associated(db_session, org_id, project.id, site.id, 15) is False
    assert project_site_ids_as_of(
        db_session, organization_id=org_id, project_id=project.id, as_of=datetime(2026, 6, 15, tzinfo=timezone.utc)
    ) == []


def test_live_as_of_now_matches_current_project_site_ids(db_session):
    """Live "as of right now" reconstruction must agree with the
    current-state project_sites table -- this milestone changes how a
    *historical* as_of is answered, not the live case (mirrors SIE
    Milestone 35B's own identical regression check)."""
    from app.services.project_site_service import link_project_site, project_site_ids

    org_id = _make_org(db_session)
    project = _make_project(db_session, org_id)
    site = _make_site(db_session, org_id)
    link_project_site(
        db_session, organization_id=org_id, project_id=project.id, site_id=site.id,
        created_by_user_id=None, created_by_api_client_id=None,
    )

    now = datetime.now(timezone.utc)
    assert project_site_ids_as_of(db_session, organization_id=org_id, project_id=project.id, as_of=now) == [site.id]
    assert project_site_ids(db_session, organization_id=org_id, project_id=project.id) == [site.id]


def test_tenant_isolation_cross_organization_reconstruction_is_false(db_session):
    """Item 20: a project from Organization A cannot be used to
    reconstruct membership with a site from Organization B -- even if a
    (malformed/bypassing) history row existed naming both, the
    organization_id filter in the reconstruction query itself must
    still scope correctly (defense in depth, not merely relying on the
    caller having pre-validated ownership)."""
    org_a = _make_org(db_session, "Org A")
    org_b = _make_org(db_session, "Org B")
    project_a = _make_project(db_session, org_a, "Project A")
    site_b = _make_site(db_session, org_b, "Site B")

    # No cross-tenant history row can even be created through the
    # governed write path (composite FKs -- see the migration test for
    # the DB-level proof) -- confirm the read side is equally safe:
    # querying with org_a's own id, a project genuinely in org_a, but a
    # site genuinely in org_b, must not spuriously report association
    # even though no such row (correctly) exists.
    assert not is_project_site_associated_as_of(
        db_session, organization_id=org_a, project_id=project_a.id, site_id=site_b.id,
        as_of=datetime.now(timezone.utc),
    )
