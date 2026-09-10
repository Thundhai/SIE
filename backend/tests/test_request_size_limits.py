"""Request size limits — Intelligence Platform Integration & Enterprise
API v0.1, item 14, and abuse testing (item 40's "oversized request",
"excessive batch")."""

from app.core.config import settings
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_predictions_api import _make_authorized_user


def test_oversized_json_body_is_rejected_before_being_parsed(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_JSON_BODY_BYTES", 100)
    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)

    # A syntactically valid, but oversized, body -- rejected purely on
    # Content-Length, never even reaching Pydantic validation.
    huge_name = "x" * 1000
    response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": str(org.id),
            "publisher": "Acme",
            "name": huge_name,
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ordinary_sized_request_is_unaffected_by_the_limit(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_JSON_BODY_BYTES", settings.MAX_JSON_BODY_BYTES)  # the real, default limit
    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": str(org.id),
            "publisher": "Acme",
            "name": "Short",
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 201


def test_multipart_file_upload_is_exempt_from_the_json_body_limit(client, db_session, monkeypatch):
    """The JSON body limit must never apply to a legitimately larger file
    upload (`multipart/form-data`, not `application/json`) -- that has
    its own, more specific `MAX_UPLOAD_SIZE_BYTES` control (unchanged by
    this milestone)."""
    from tests.conftest import load_fixture
    from tests.intelligence_test_helpers import make_platform_admin_user

    admin = make_platform_admin_user(db_session)
    source = client.post(
        "/api/v1/knowledge/sources",
        json={"scope_type": "GLOBAL", "publisher": "OSHA", "name": "29 CFR 1910", "source_type": "regulation"},
        headers=dev_auth_headers(admin.id),
    ).json()

    # A real file, larger than the tiny JSON-body cap set below --
    # proving the exemption, not just that a small request happens to fit.
    file_bytes = load_fixture("sample_ppe_policy.txt")
    assert len(file_bytes) > 10
    monkeypatch.setattr(settings, "MAX_JSON_BODY_BYTES", 10)

    response = client.post(
        "/api/v1/knowledge/ingestion",
        headers=dev_auth_headers(admin.id),
        data={"source_id": source["id"], "title": "PPE Policy"},
        files={"file": ("sample_ppe_policy.txt", file_bytes, "text/plain")},
    )
    assert response.status_code == 201


def test_batch_ingestion_still_caps_at_the_existing_1000_event_limit(client, db_session):
    """Pre-existing, unchanged limit (`SafetyEventBatchCreate.events`,
    `max_length=1000`) -- confirmed still enforced post-milestone."""
    from app.services.api_client_service import api_client_service
    from app.services.permissions import Permission

    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Batch Test", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    headers = {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}

    too_many_events = [
        {
            "event_type": "OBSERVATION",
            "event_time": "2026-01-01T00:00:00Z",
            "source_system": "test",
            "source_record_id": f"rec-{i}",
        }
        for i in range(1001)
    ]
    response = client.post(
        "/api/v1/intelligence/events/batch", json={"events": too_many_events}, headers=headers
    )
    assert response.status_code == 422
