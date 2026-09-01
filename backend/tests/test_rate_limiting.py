"""Rate limiting — Intelligence Platform Integration & Enterprise API
v0.1, items 13, 40. Off by default (`RATE_LIMIT_ENABLED=False`) —
these tests explicitly opt in via monkeypatch to prove the mechanism
itself works, without asserting anything about the disabled-by-default
production posture."""

from app.core.config import settings
from app.core.rate_limit import LocalRateLimiter, get_rate_limiter
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org
from tests.test_intelligence_api import _bearer, _make_client_credential
from tests.test_predictions_api import _make_authorized_user


def test_local_rate_limiter_allows_up_to_the_limit_then_blocks(monkeypatch):
    limiter = LocalRateLimiter()
    for _ in range(5):
        result = limiter.check("k", limit=5, window_seconds=60)
        assert result.allowed
    blocked = limiter.check("k", limit=5, window_seconds=60)
    assert not blocked.allowed
    assert blocked.remaining == 0


def test_local_rate_limiter_keys_are_independent(monkeypatch):
    limiter = LocalRateLimiter()
    for _ in range(3):
        assert limiter.check("a", limit=3, window_seconds=60).allowed
    # A different key has its own, untouched budget.
    assert limiter.check("b", limit=3, window_seconds=60).allowed


def test_disabled_by_default_never_limits_anything(client, db_session):
    assert settings.RATE_LIMIT_ENABLED is False
    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)
    for _ in range(10):
        response = client.get(
            f"/api/v1/knowledge/sources?organization_id={org.id}", headers=dev_auth_headers(user.id)
        )
        assert response.status_code == 200


def test_enabled_rate_limit_returns_429_with_the_standard_error_code(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_READ_REQUESTS_PER_MINUTE", 2)
    get_rate_limiter().reset()

    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)
    url = f"/api/v1/knowledge/sources?organization_id={org.id}"

    first = client.get(url, headers=dev_auth_headers(user.id))
    second = client.get(url, headers=dev_auth_headers(user.id))
    third = client.get(url, headers=dev_auth_headers(user.id))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    body = third.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert third.headers["x-ratelimit-limit"] == "2"
    assert third.headers["x-ratelimit-remaining"] == "0"
    get_rate_limiter().reset()


def test_read_and_write_budgets_are_independent(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_READ_REQUESTS_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_WRITE_REQUESTS_PER_MINUTE", 5)
    get_rate_limiter().reset()

    from app.services.permissions import OrganizationRole

    org = make_org(db_session)
    admin = _make_authorized_user(db_session, org.id, role=OrganizationRole.ORG_ADMIN)

    read_url = f"/api/v1/knowledge/sources?organization_id={org.id}"
    assert client.get(read_url, headers=dev_auth_headers(admin.id)).status_code == 200
    assert client.get(read_url, headers=dev_auth_headers(admin.id)).status_code == 429

    # Exhausting the read budget above never touched the write budget.
    write_response = client.post(
        "/api/v1/knowledge/sources",
        json={
            "scope_type": "ORGANIZATION",
            "organization_id": str(org.id),
            "publisher": "Acme",
            "name": "Still allowed",
            "source_type": "internal_procedure",
        },
        headers=dev_auth_headers(admin.id),
    )
    assert write_response.status_code == 201
    get_rate_limiter().reset()


def test_rate_limit_is_per_client_not_global(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_READ_REQUESTS_PER_MINUTE", 1)
    get_rate_limiter().reset()

    org = make_org(db_session)
    from app.services.permissions import OrganizationRole

    user_a = _make_authorized_user(db_session, org.id, role=OrganizationRole.ORG_ADMIN)
    user_b = _make_authorized_user(db_session, org.id, role=OrganizationRole.ORG_ADMIN)
    url = f"/api/v1/knowledge/sources?organization_id={org.id}"

    assert client.get(url, headers=dev_auth_headers(user_a.id)).status_code == 200
    assert client.get(url, headers=dev_auth_headers(user_a.id)).status_code == 429
    # A different caller's budget is untouched by user_a's usage.
    assert client.get(url, headers=dev_auth_headers(user_b.id)).status_code == 200
    get_rate_limiter().reset()


def test_machine_client_rate_limit_is_scoped_to_its_own_client_id(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_READ_REQUESTS_PER_MINUTE", 1)
    get_rate_limiter().reset()

    from app.services.permissions import Permission

    org = make_org(db_session)
    credential_a = _make_client_credential(db_session, org.id, scopes=[Permission.INTELLIGENCE_READ])
    credential_b = _make_client_credential(db_session, org.id, scopes=[Permission.INTELLIGENCE_READ])
    url = f"/api/v1/intelligence/analytics/summary?organization_id={org.id}"

    assert client.get(url, headers=_bearer(credential_a)).status_code == 200
    assert client.get(url, headers=_bearer(credential_a)).status_code == 429
    assert client.get(url, headers=_bearer(credential_b)).status_code == 200
    get_rate_limiter().reset()
