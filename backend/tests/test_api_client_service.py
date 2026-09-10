"""ApiClientService — machine-client credential lifecycle (milestone item
10). Runs against `db_session` (SQLite).
"""

import uuid

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="API Client Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def test_create_returns_the_raw_secret_exactly_once(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Safelytic Integration", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    assert credential.secret
    assert len(credential.secret) > 20
    assert credential.api_client.status == "ACTIVE"


def test_the_raw_secret_is_never_stored_only_a_hash(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    assert credential.api_client.hashed_secret != credential.secret
    assert credential.secret not in credential.api_client.hashed_secret


def test_secret_prefix_is_a_short_safe_to_display_fragment(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    assert credential.api_client.secret_prefix == credential.secret[: len(credential.api_client.secret_prefix)]
    assert len(credential.api_client.secret_prefix) < len(credential.secret)


def test_authenticate_succeeds_with_the_correct_client_id_and_secret(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    result = api_client_service.authenticate(
        db_session, client_id=credential.client_id, secret=credential.secret
    )
    assert result is not None
    assert result.id == credential.api_client.id


def test_authenticate_fails_with_the_wrong_secret(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    result = api_client_service.authenticate(
        db_session, client_id=credential.client_id, secret="wrong-secret"
    )
    assert result is None


def test_authenticate_fails_for_an_unknown_client_id(db_session):
    result = api_client_service.authenticate(db_session, client_id="sie_doesnotexist", secret="anything")
    assert result is None


def test_revoked_client_can_no_longer_authenticate(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    api_client_service.revoke(db_session, api_client=credential.api_client)

    result = api_client_service.authenticate(
        db_session, client_id=credential.client_id, secret=credential.secret
    )
    assert result is None


def test_rotating_the_secret_invalidates_the_old_one(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    old_secret = credential.secret
    new_credential = api_client_service.rotate_secret(db_session, api_client=credential.api_client)

    assert api_client_service.authenticate(db_session, client_id=credential.client_id, secret=old_secret) is None
    assert (
        api_client_service.authenticate(db_session, client_id=credential.client_id, secret=new_credential.secret)
        is not None
    )


def test_authenticate_updates_last_used_at(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    assert credential.api_client.last_used_at is None
    api_client_service.authenticate(db_session, client_id=credential.client_id, secret=credential.secret)
    db_session.refresh(credential.api_client)
    assert credential.api_client.last_used_at is not None


def test_scopes_are_explicit_not_inherited_from_any_role(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Read-only client", scopes=[Permission.SAFETY_DATA_READ]
    )
    assert credential.api_client.scopes == ["safety_data:read"]
    assert "safety_data:write" not in credential.api_client.scopes


def test_create_and_revoke_write_audit_entries(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Audited Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    api_client_service.revoke(db_session, api_client=credential.api_client)

    actions = {entry.action for entry in db_session.query(AuditLog).all()}
    assert "API_CLIENT_CREATED" in actions
    assert "API_CLIENT_REVOKED" in actions


def test_audit_entries_never_contain_the_raw_secret(db_session):
    org_id = _make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org_id, name="Test Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )
    entries = db_session.query(AuditLog).filter(AuditLog.action == "API_CLIENT_CREATED").all()
    assert credential.secret not in str(entries[0].event_metadata)
