"""HTTP-level ingestion tests — milestone items 18-20 (tenant isolation,
global knowledge authorization, organization knowledge authorization),
plus API-shape coverage for the endpoint itself.
"""

import uuid

from app.schemas.organization_membership import OrganizationMembershipCreate
from app.schemas.user import UserCreate
from app.services.membership_service import membership_service
from app.services.permissions import PLATFORM_ADMIN
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers, load_fixture


def create_org(client, name="Acme Industrial"):
    return client.post("/api/v1/organizations", json={"name": name}).json()


def create_org_source(client, organization_id, name="Internal Procedure"):
    return client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": organization_id,
            "publisher": "Acme",
            "name": name,
            "source_type": "internal_procedure",
        },
    ).json()


def create_global_source(client, name="29 CFR 1910"):
    return client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "GLOBAL",
            "publisher": "OSHA",
            "name": name,
            "source_type": "regulation",
        },
    ).json()


def make_user(db_session, email, name="User", platform_role=None):
    user = user_service.create(db_session, obj_in=UserCreate(email=email, name=name))
    if platform_role is not None:
        user = user_service.set_platform_role(db_session, user=user, platform_role=platform_role)
    return user


def make_membership(db_session, *, user_id, organization_id, role):
    return membership_service.create(
        db_session,
        organization_id=organization_id,
        obj_in=OrganizationMembershipCreate(user_id=user_id, role=role),
    )


def upload(client, *, headers, source_id, organization_id=None, document_id=None, title=None):
    data = {"source_id": str(source_id)}
    if organization_id is not None:
        data["organization_id"] = str(organization_id)
    if document_id is not None:
        data["document_id"] = str(document_id)
    if title is not None:
        data["title"] = title
    file_bytes = load_fixture("sample_ppe_policy.txt")
    return client.post(
        "/api/v1/knowledge/ingestion",
        headers=headers,
        data=data,
        files={"file": ("sample_ppe_policy.txt", file_bytes, "text/plain")},
    )


def test_ingestion_endpoint_requires_authentication(client):
    org = create_org(client)
    source = create_org_source(client, org["id"])

    response = upload(
        client, headers={}, source_id=source["id"], organization_id=org["id"], title="X"
    )

    assert response.status_code == 401


# --- 20. Organization knowledge authorization ------------------------------


def test_org_member_with_knowledge_manage_can_ingest(client, db_session):
    org = create_org(client)
    source = create_org_source(client, org["id"])
    user = make_user(db_session, "manager@example.com")
    make_membership(
        db_session, user_id=user.id, organization_id=uuid.UUID(org["id"]), role="HSE_MANAGER"
    )

    response = upload(
        client,
        headers=dev_auth_headers(user.id),
        source_id=source["id"],
        organization_id=org["id"],
        title="PPE Policy",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] is not None
    assert body["version_id"] is not None
    assert body["ingestion_status"] == "COMPLETED"


def test_org_member_without_knowledge_manage_cannot_ingest(client, db_session):
    org = create_org(client)
    source = create_org_source(client, org["id"])
    viewer = make_user(db_session, "viewer@example.com")
    make_membership(
        db_session, user_id=viewer.id, organization_id=uuid.UUID(org["id"]), role="VIEWER"
    )

    response = upload(
        client,
        headers=dev_auth_headers(viewer.id),
        source_id=source["id"],
        organization_id=org["id"],
        title="PPE Policy",
    )

    assert response.status_code == 403


def test_non_member_cannot_ingest_into_an_organization(client, db_session):
    org = create_org(client)
    source = create_org_source(client, org["id"])
    outsider = make_user(db_session, "outsider@example.com")
    # No membership created for outsider in org at all.

    response = upload(
        client,
        headers=dev_auth_headers(outsider.id),
        source_id=source["id"],
        organization_id=org["id"],
        title="PPE Policy",
    )

    assert response.status_code == 403


# --- 18. Tenant isolation ---------------------------------------------------


def test_org_a_member_cannot_ingest_into_org_b(client, db_session):
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    source_b = create_org_source(client, org_b["id"], name="Org B Procedure")
    admin_a = make_user(db_session, "admina@example.com")
    make_membership(
        db_session, user_id=admin_a.id, organization_id=uuid.UUID(org_a["id"]), role="ORG_ADMIN"
    )

    response = upload(
        client,
        headers=dev_auth_headers(admin_a.id),
        source_id=source_b["id"],
        organization_id=org_b["id"],  # admin_a has no membership here
        title="Should Not Be Created",
    )

    assert response.status_code == 403


def test_asserting_a_different_organization_than_the_sources_own_is_rejected(client, db_session):
    """Even a caller authorized for *an* organization can't attach a
    document to a different organization's source by asserting it in the
    body — this is the existing Knowledge Foundation cross-check,
    exercised through the ingestion endpoint."""
    org_a = create_org(client, "Org A")
    org_b = create_org(client, "Org B")
    source_a = create_org_source(client, org_a["id"], name="Org A Procedure")
    admin_b = make_user(db_session, "adminb@example.com")
    make_membership(
        db_session, user_id=admin_b.id, organization_id=uuid.UUID(org_b["id"]), role="ORG_ADMIN"
    )

    response = upload(
        client,
        headers=dev_auth_headers(admin_b.id),
        source_id=source_a["id"],
        organization_id=org_b["id"],  # admin_b IS authorized for org_b...
        title="Mismatched",
    )

    # ...but org_b is not source_a's organization, so KnowledgeDocumentService
    # .create()'s existing consistency check (unchanged by this milestone)
    # rejects the mismatch with 400, not 201.
    assert response.status_code == 400


# --- 19. Global knowledge authorization -------------------------------------


def test_platform_admin_can_ingest_global_knowledge(client, db_session):
    source = create_global_source(client)
    admin = make_user(db_session, "platformadmin@example.com", platform_role=PLATFORM_ADMIN)

    response = upload(
        client, headers=dev_auth_headers(admin.id), source_id=source["id"], title="Global Doc"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] is not None


def test_ordinary_org_admin_cannot_ingest_global_knowledge_by_omitting_organization_id(
    client, db_session
):
    """Omitting organization_id is not a lesser-privilege path to global
    knowledge — it requires platform-wide access, which an ordinary
    (non-platform-admin) org admin does not have, even in their own org."""
    org = create_org(client)
    source = create_global_source(client)
    org_admin = make_user(db_session, "orgadmin@example.com")
    make_membership(
        db_session, user_id=org_admin.id, organization_id=uuid.UUID(org["id"]), role="ORG_ADMIN"
    )

    response = upload(
        client, headers=dev_auth_headers(org_admin.id), source_id=source["id"], title="Global Doc"
    )

    assert response.status_code == 403


def test_unaffiliated_user_cannot_ingest_global_knowledge(client, db_session):
    source = create_global_source(client)
    user = make_user(db_session, "plainuser@example.com")

    response = upload(client, headers=dev_auth_headers(user.id), source_id=source["id"], title="X")

    assert response.status_code == 403


# --- Response shape / misc --------------------------------------------------


def test_unsupported_file_type_returns_415(client, db_session):
    source = create_global_source(client)
    admin = make_user(db_session, "admin415@example.com", platform_role=PLATFORM_ADMIN)

    response = client.post(
        "/api/v1/knowledge/ingestion",
        headers=dev_auth_headers(admin.id),
        data={"source_id": source["id"], "title": "Bad"},
        files={
            "file": (
                "unsupported.bin",
                load_fixture("unsupported.bin"),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 415


def test_ingestion_response_does_not_include_extracted_content(client, db_session):
    source = create_global_source(client)
    admin = make_user(db_session, "admin2@example.com", platform_role=PLATFORM_ADMIN)

    response = upload(client, headers=dev_auth_headers(admin.id), source_id=source["id"], title="X")

    assert response.status_code == 201
    body = response.json()
    assert "text" not in body
    assert "content" not in body
    assert "extracted_text" not in body
    assert set(body.keys()) == {
        "ingestion_job_id",
        "file_id",
        "detected_media_type",
        "file_size",
        "content_hash",
        "ingestion_status",
        "extraction_status",
        "extraction_method",
        "document_id",
        "version_id",
        "chunk_count",
        "warnings",
    }
