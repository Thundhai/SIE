"""G3-BE-01: Organization & site authorization hardening — regression
coverage for the full matrix.

Before this milestone, `POST /organizations`, `POST .../sites`, and
`GET .../sites` had no authentication or authorization at all (see
app/api/v1/organizations.py's and app/api/v1/sites.py's own docstrings,
and backend/README.md's "Existing organization-scoped APIs" section for
why — these three routes predate the authorization pipeline and were
deliberately left unretrofitted until now).

This file demonstrates the exploit is closed over plain HTTP (not just at
the service layer), covers the complete authorization matrix the G3-BE-01
task spec requires, and confirms the fix does not reintroduce the G1
class of bug (an authorization denial degrading into an unhandled 500).
"""

import uuid

from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers, platform_admin_headers
from tests.intelligence_test_helpers import make_org, make_org_member

# --- Organization creation: direct HTTP exploit regression ---------------


def test_exploit_closed_organization_creation_without_credentials(client):
    """Before G3-BE-01: `curl -X POST /api/v1/organizations` with no
    credentials returned 201. This is the live exploit the task closes."""
    response = client.post("/api/v1/organizations", json={"name": "Exploit Org"})
    assert response.status_code == 401
    assert response.json()["detail"]


def test_exploit_closed_organization_creation_malformed_dev_header(client):
    """A caller that presents *something* but not a valid identity must
    still be denied — not silently treated as anonymous-but-allowed."""
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Exploit Org"},
        headers={"X-SIE-Dev-User-Id": "not-a-uuid"},
    )
    assert response.status_code == 401


# --- Site list/create: full authorization matrix --------------------------


def _create_site_url(org_id) -> str:
    return f"/api/v1/organizations/{org_id}/sites"


def test_site_list_requires_authentication(client, db_session):
    org = make_org(db_session)

    response = client.get(_create_site_url(org.id))

    assert response.status_code == 401


def test_site_create_requires_authentication(client, db_session):
    org = make_org(db_session)

    response = client.post(_create_site_url(org.id), json={"name": "Plant 1"})

    assert response.status_code == 401


def test_site_list_denied_for_user_from_another_organization(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    outsider = make_org_member(db_session, org_b.id, role="ORG_ADMIN")

    response = client.get(_create_site_url(org_a.id), headers=dev_auth_headers(outsider.id))

    assert response.status_code == 403


def test_site_create_denied_for_user_from_another_organization(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    outsider = make_org_member(db_session, org_b.id, role="ORG_ADMIN")

    response = client.post(
        _create_site_url(org_a.id), json={"name": "Plant 1"}, headers=dev_auth_headers(outsider.id)
    )

    assert response.status_code == 403


def test_site_create_denied_for_insufficient_permission(client, db_session):
    """VIEWER has SITE_READ but not SITE_MANAGE (see
    app/services/permissions.py's ROLE_PERMISSIONS) -- a real member of
    the *correct* organization, still correctly denied a write."""
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role="VIEWER")

    response = client.post(_create_site_url(org.id), json={"name": "Plant 1"}, headers=dev_auth_headers(viewer.id))

    assert response.status_code == 403


def test_site_list_allowed_for_viewer(client, db_session):
    """SITE_READ is granted to every role (see ROLE_PERMISSIONS) --
    reading is not restricted the way creating is."""
    org = make_org(db_session)
    viewer = make_org_member(db_session, org.id, role="VIEWER")

    response = client.get(_create_site_url(org.id), headers=dev_auth_headers(viewer.id))

    assert response.status_code == 200
    assert response.json() == []


def test_site_create_allowed_for_org_admin(client, db_session):
    org = make_org(db_session)
    admin = make_org_member(db_session, org.id, role="ORG_ADMIN")

    response = client.post(
        _create_site_url(org.id), json={"name": "Plant 1"}, headers=dev_auth_headers(admin.id)
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == str(org.id)


def test_site_create_allowed_for_hse_manager(client, db_session):
    org = make_org(db_session)
    manager = make_org_member(db_session, org.id, role="HSE_MANAGER")

    response = client.post(
        _create_site_url(org.id), json={"name": "Plant 1"}, headers=dev_auth_headers(manager.id)
    )

    assert response.status_code == 201


# --- PLATFORM_ADMIN: elevated authority, no membership required -----------


def test_platform_admin_can_create_and_list_sites_without_membership(client, db_session):
    """A PLATFORM_ADMIN has no OrganizationMembership row in this
    organization at all -- `authorize_tenant_context`'s documented,
    narrow exception is what must still let this through."""
    org = make_org(db_session)
    headers = platform_admin_headers()

    create_response = client.post(_create_site_url(org.id), json={"name": "Plant 1"}, headers=headers)
    list_response = client.get(_create_site_url(org.id), headers=headers)

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_platform_admin_organization_creation_still_requires_platform_admin(client, db_session):
    """A PLATFORM_ADMIN is the authority for creating an organization; an
    ordinary member of some *other* organization is not, no matter how
    privileged their role is there."""
    org = make_org(db_session)
    admin = make_org_member(db_session, org.id, role="ORG_ADMIN")

    response = client.post(
        "/api/v1/organizations", json={"name": "New Org"}, headers=dev_auth_headers(admin.id)
    )

    assert response.status_code == 403


# --- Machine credentials: never applicable to this administrative surface -


def test_machine_credential_cannot_authenticate_to_site_routes(client, db_session):
    """Sites are part of the human-only administrative surface (same
    category as memberships, API clients, governing standards) -- see
    app/api/deps_context.py's own "item 7" docstring section. A machine
    client, even one scoped and pinned to the correct organization,
    cannot use this surface at all."""
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session,
        organization_id=org.id,
        name="Ingestion Bot",
        scopes=[Permission.SITE_MANAGE, Permission.SITE_READ],
    )
    headers = {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}

    create_response = client.post(_create_site_url(org.id), json={"name": "Plant 1"}, headers=headers)
    list_response = client.get(_create_site_url(org.id), headers=headers)

    assert create_response.status_code == 401
    assert list_response.status_code == 401


# --- Error semantics: an authorization denial must never surface as 500 ---


def test_platform_admin_against_nonexistent_organization_returns_404_not_500(client):
    """A PLATFORM_ADMIN's elevated authority bypasses the membership
    check, but must never bypass the organization's own existence check
    -- otherwise `site_service.create()` would attempt to insert a row
    with a foreign key to an organization that doesn't exist, which
    would surface as an unhandled IntegrityError/500 (the exact class of
    bug G1 fixed elsewhere). `get_organization_or_404` running ahead of
    `require_permission` is what prevents that here."""
    response = client.post(
        _create_site_url(uuid.uuid4()),
        json={"name": "Plant 1"},
        headers=platform_admin_headers(),
    )
    assert response.status_code == 404
    assert response.status_code != 500


def test_denied_organization_creation_does_not_touch_the_audit_log(client, db_session):
    """app/api/v1/organizations.py's new check calls
    `authorization_service.can()` directly -- it never constructs an
    `AuditLog` row itself, so there is no new call site that could
    repeat the G1 class of bug (an unvalidated organization_id reaching
    `AuditLog.organization_id`, a real FK). A 403 here must stay a clean
    403, with no IntegrityError, regardless of how many times it's
    exercised in the same test run."""
    org = make_org(db_session)
    non_admin = make_org_member(db_session, org.id, role="ORG_ADMIN")

    for _ in range(3):
        response = client.post(
            "/api/v1/organizations", json={"name": "Denied"}, headers=dev_auth_headers(non_admin.id)
        )
        assert response.status_code == 403
