"""Standardized error contract (item 15) and health/readiness endpoints
(items 33-34) — Intelligence Platform Integration & Enterprise API v0.1.
"""

from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org

# --- Error contract ------------------------------------------------------------------


def test_401_carries_the_standardized_authentication_required_code(client):
    response = client.get("/api/v1/knowledge/sources")
    assert response.status_code == 401
    body = response.json()
    assert "detail" in body  # unchanged, existing shape
    assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert body["error"]["request_id"]


def test_404_carries_the_standardized_resource_not_found_code(client, db_session):
    from tests.intelligence_test_helpers import make_platform_admin_user

    admin = make_platform_admin_user(db_session)
    response = client.get(
        "/api/v1/knowledge/sources/00000000-0000-0000-0000-000000000000", headers=dev_auth_headers(admin.id)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_403_carries_the_standardized_authorization_denied_code(client, db_session):
    from tests.test_predictions_api import _make_authorized_user

    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    user = _make_authorized_user(db_session, org_a.id)

    response = client.get(f"/api/v1/knowledge/sources?organization_id={org_b.id}", headers=dev_auth_headers(user.id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTHORIZATION_DENIED"


def test_pydantic_validation_error_keeps_fastapis_own_detail_shape_and_gains_the_error_object(client, db_session):
    from tests.intelligence_test_helpers import make_platform_admin_user

    admin = make_platform_admin_user(db_session)
    response = client.post(
        "/api/v1/knowledge/sources",
        json={"scope_type": "GLOBAL"},  # missing required fields
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)  # FastAPI's own default shape, unchanged
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_a_model_validator_raised_value_error_is_still_json_serializable(client, db_session):
    """Regression test for a real bug caught while wiring the custom
    validation-error handler: a Pydantic model_validator's raised
    ValueError ends up in exc.errors()[i]['ctx']['error'] as a raw
    exception object -- plain json.dumps chokes on it; the handler must
    use jsonable_encoder (see app/core/errors.py)."""
    from tests.intelligence_test_helpers import make_platform_admin_user

    admin = make_platform_admin_user(db_session)
    org = make_org(db_session)
    response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "GLOBAL",
            "organization_id": str(org.id),  # rejected by KnowledgeSourceCreate's own model_validator
            "publisher": "OSHA",
            "name": "29 CFR 1910",
            "source_type": "regulation",
        },
        headers=dev_auth_headers(admin.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_no_endpoint_ever_leaks_a_stack_trace_or_database_error_text(db_session, monkeypatch):
    """A genuinely unexpected exception (not a deliberate HTTPException)
    must still produce the one fixed, generic INTERNAL_ERROR body --
    never the real exception's own message.

    Uses its own `TestClient(..., raise_server_exceptions=False)` rather
    than the shared `client` fixture: Starlette's `ServerErrorMiddleware`
    sends the real (already-correct) response over the wire and *then*
    re-raises the original exception so it's visible to server-side
    logging/WSGI error handling -- `TestClient`'s default
    `raise_server_exceptions=True` surfaces that re-raise in-process,
    which would otherwise fail this test on the very re-raise this test
    exists to prove is client-invisible."""
    from starlette.testclient import TestClient

    from app.main import app
    from tests.intelligence_test_helpers import make_platform_admin_user

    admin = make_platform_admin_user(db_session)

    def _boom(*args, **kwargs):
        raise RuntimeError("super secret internal database connection string leaked here")

    monkeypatch.setattr("app.api.v1.knowledge.knowledge_source_service.list", _boom)

    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.get("/api/v1/knowledge/sources", headers=dev_auth_headers(admin.id))

    assert response.status_code == 500
    body = response.json()
    assert "super secret" not in response.text
    assert "RuntimeError" not in response.text
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["detail"] == "An internal error occurred."


# --- Health / readiness ---------------------------------------------------------------


def test_health_is_a_plain_liveness_check_with_no_database_dependency(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_live_matches_health(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_reports_the_database_as_up_against_the_test_database(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "UP"


def test_health_endpoints_require_no_authentication(client):
    # Health checks are infrastructure-facing (load balancers, orchestrators)
    # -- never gated behind the same auth every other route requires.
    for path in ("/health", "/health/live", "/health/ready"):
        assert client.get(path).status_code in (200, 503)
