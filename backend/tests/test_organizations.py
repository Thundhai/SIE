import uuid

from app.schemas.user import UserCreate
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers, platform_admin_headers


def create_org(client, name="Acme Industrial"):
    return client.post(
        "/api/v1/organizations",
        json={"name": name, "industry": "manufacturing", "country": "US"},
        headers=platform_admin_headers(),
    )


def test_create_organization(client):
    response = create_org(client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Industrial"
    assert body["industry"] == "manufacturing"
    assert body["status"] == "active"
    assert uuid.UUID(body["id"])
    assert "created_at" in body
    assert "updated_at" in body


# --- G3-BE-01: organization creation authorization -----------------------


def test_create_organization_requires_authentication(client):
    """The exploit this milestone closes: creating an organization with
    no credentials at all must now be rejected, not succeed with 201."""
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Unauthenticated Org"},
    )
    assert response.status_code == 401


def test_create_organization_denied_for_non_platform_admin(client, db_session):
    """An ordinary authenticated human -- with no organization to hold a
    membership in yet -- has no path to the required authority. There is
    no organization-scoped permission that could apply here (see
    app/api/v1/organizations.py's own docstring)."""
    user = user_service.create(db_session, obj_in=UserCreate(email="human@example.com", name="Human"))

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Denied Org"},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 403


def test_create_organization_succeeds_for_platform_admin(client):
    """The one correct authority this codebase already establishes for a
    GLOBAL/no-tenant-yet action (mirrors app/api/v1/knowledge.py's and
    app/api/v1/ingestion.py's GLOBAL-write rule)."""
    response = create_org(client, "Platform Admin Org")
    assert response.status_code == 201
    assert response.json()["name"] == "Platform Admin Org"


def test_get_organization(client):
    created = create_org(client).json()

    response = client.get(f"/api/v1/organizations/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_organization_not_found(client):
    response = client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert response.status_code == 404
