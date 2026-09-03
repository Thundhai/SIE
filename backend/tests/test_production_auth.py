"""Production authentication — HTTP layer. SIE Milestone 20: Production
Authentication & Identity Foundation v0.1, requirement #10's full case
list, exercised end to end through the real FastAPI app: a real signed
JWT (see tests/oidc_test_helpers.py) is presented on `Authorization:
Bearer <token>`, resolved through `IdentityResolverService`, and fed into
the *unchanged* `authorize_tenant_context`/`AuthorizationService`
pipeline — the same one `tests/test_auth_me_api.py` already exercises for
the dev-mode mechanism.
"""

import uuid
from datetime import timedelta

from app.models.audit_log import AuditLog
from app.models.enums import MembershipStatus
from app.models.identity import Identity
from app.schemas.organization_membership import OrganizationMembershipCreate
from app.services.audit_service import AuditAction
from app.services.membership_service import membership_service
from app.services.permissions import OrganizationRole, Permission
from tests.intelligence_test_helpers import make_org, make_org_member, make_platform_admin_user
from tests.oidc_test_helpers import (
    OTHER_KID,
    TEST_ISSUER,
    bearer,
    make_test_token,
    make_token_signed_by_other_key,
    production_auth,  # noqa: F401 -- fixture, referenced by name in test signatures
)

_ME_URL = "/api/v1/auth/me"
_ORGS_URL = "/api/v1/auth/organizations"
_EVENTS_URL = "/api/v1/intelligence/events"  # machine-only ingestion -- used for machine-vs-human disambiguation
_ACTIONS_URL = "/api/v1/actions"  # human-or-machine RequestContext write, requires INTERVENTION_MANAGE


def _event_payload(source_record_id: str = "rec-1") -> dict:
    return {
        "event_type": "NEAR_MISS",
        "event_time": "2026-01-01T00:00:00Z",
        "source_system": "test",
        "source_record_id": source_record_id,
    }


def _action_payload(title: str = "Follow up") -> dict:
    return {"title": title, "action_type": "CORRECTIVE"}


def _link_identity(db_session, *, user_id, subject: str, issuer: str = TEST_ISSUER) -> Identity:
    identity = Identity(user_id=user_id, subject=subject, issuer=issuer, provider="test-idp")
    db_session.add(identity)
    db_session.commit()
    return identity


# --- Token validation --------------------------------------------------------------------


def test_valid_production_token_authenticates(client, db_session, production_auth):
    org = make_org(db_session, "Acme")
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    _link_identity(db_session, user_id=user.id, subject="sub-valid")
    token = make_test_token(subject="sub-valid")

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["auth_mode"] == "production"
    assert body["identity_provider"] == "test-idp"


def test_expired_token_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(expires_delta=timedelta(hours=-1))
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_invalid_signature_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_token_signed_by_other_key()
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_wrong_issuer_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(issuer="https://not-the-configured-issuer.example.com")
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_wrong_audience_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(audience="some-other-audience")
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_missing_subject_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(subject=None)
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_malformed_token_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    response = client.get(
        f"{_ME_URL}?organization_id={org.id}", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401


def test_unknown_key_id_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(kid=OTHER_KID)
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 401


def test_missing_token_when_production_auth_is_configured(client, db_session, production_auth, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEV_MODE", False)
    org = make_org(db_session)
    response = client.get(f"{_ME_URL}?organization_id={org.id}")
    assert response.status_code == 401


def test_production_mode_with_incomplete_auth_configuration_fails_closed(client, db_session, monkeypatch):
    """No `production_auth` fixture here -- OIDC is genuinely unconfigured
    (the module default), and DEV_MODE is off, so there is no
    authentication mechanism available for this request at all."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEV_MODE", False)
    org = make_org(db_session)
    token = make_test_token()
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 501


def test_machine_credential_cannot_authenticate_as_a_human(client, db_session, production_auth):
    org = make_org(db_session)
    response = client.get(
        f"{_ME_URL}?organization_id={org.id}", headers={"Authorization": "Bearer some-client-id:some-secret"}
    )
    assert response.status_code == 401


# --- Identity ------------------------------------------------------------------------------


def test_known_identity_authenticates_without_creating_a_duplicate(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _link_identity(db_session, user_id=user.id, subject="known-sub")
    token = make_test_token(subject="known-sub")

    for _ in range(2):
        response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
        assert response.status_code == 200
        assert response.json()["user_id"] == str(user.id)

    identities = (
        db_session.query(Identity)
        .filter(Identity.issuer == TEST_ISSUER, Identity.subject == "known-sub")
        .all()
    )
    assert len(identities) == 1


def test_unknown_identity_is_provisioned_but_starts_with_no_organization_access(
    client, db_session, production_auth
):
    token = make_test_token(subject="brand-new-sub", extra_claims={"email": "new.hire@example.com"})

    response = client.get(_ORGS_URL, headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["memberships"] == []
    assert body["is_platform_admin"] is False
    # A User + Identity really were provisioned, auditable as such.
    identity = (
        db_session.query(Identity)
        .filter(Identity.issuer == TEST_ISSUER, Identity.subject == "brand-new-sub")
        .one()
    )
    assert identity.user_id is not None
    provisioned = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.IDENTITY_PROVISIONED, AuditLog.resource_id == identity.id)
        .one_or_none()
    )
    assert provisioned is not None


def test_inactive_user_identity_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_USER)
    _link_identity(db_session, user_id=user.id, subject="inactive-sub")
    user.status = "inactive"
    db_session.add(user)
    db_session.commit()

    token = make_test_token(subject="inactive-sub")
    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))

    assert response.status_code == 401
    rejected = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.AUTH_REJECTED, AuditLog.user_id == user.id)
        .one_or_none()
    )
    assert rejected is not None


def test_identity_with_one_organization(client, db_session, production_auth):
    org = make_org(db_session, "Only Org")
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    _link_identity(db_session, user_id=user.id, subject="one-org-sub")
    token = make_test_token(subject="one-org-sub")

    response = client.get(_ORGS_URL, headers=bearer(token))

    assert response.status_code == 200
    memberships = response.json()["memberships"]
    assert len(memberships) == 1
    assert memberships[0]["organization_id"] == str(org.id)
    assert memberships[0]["role"] == "HSE_MANAGER"


def test_identity_with_multiple_organizations_must_explicitly_select_one(client, db_session, production_auth):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    user = make_org_member(db_session, org_a.id, role=OrganizationRole.ORG_ADMIN)
    membership_service.create(
        db_session,
        organization_id=org_b.id,
        obj_in=OrganizationMembershipCreate(user_id=user.id, role=OrganizationRole.VIEWER),
    )
    _link_identity(db_session, user_id=user.id, subject="multi-org-sub")
    token = make_test_token(subject="multi-org-sub")

    orgs_response = client.get(_ORGS_URL, headers=bearer(token))
    assert orgs_response.status_code == 200
    listed_ids = {m["organization_id"] for m in orgs_response.json()["memberships"]}
    assert listed_ids == {str(org_a.id), str(org_b.id)}

    # Each organization must still be named explicitly -- neither call
    # implicitly reuses the other's context.
    me_a = client.get(f"{_ME_URL}?organization_id={org_a.id}", headers=bearer(token))
    me_b = client.get(f"{_ME_URL}?organization_id={org_b.id}", headers=bearer(token))
    assert me_a.status_code == 200 and me_a.json()["role"] == "ORG_ADMIN"
    assert me_b.status_code == 200 and me_b.json()["role"] == "VIEWER"

    # A third, unrelated organization is still refused.
    org_c = make_org(db_session, "Org C")
    me_c = client.get(f"{_ME_URL}?organization_id={org_c.id}", headers=bearer(token))
    assert me_c.status_code == 403


# --- Authorization ---------------------------------------------------------------------------


def test_permitted_operation_succeeds_with_a_production_identity(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    _link_identity(db_session, user_id=user.id, subject="writer-sub")
    token = make_test_token(subject="writer-sub")

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_action_payload(), headers=bearer(token)
    )
    assert response.status_code == 201


def test_denied_permission_with_a_production_identity(client, db_session, production_auth):
    org = make_org(db_session)
    # VIEWER holds INTERVENTION_READ but not INTERVENTION_MANAGE.
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _link_identity(db_session, user_id=user.id, subject="viewer-sub")
    token = make_test_token(subject="viewer-sub")

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_action_payload(), headers=bearer(token)
    )
    assert response.status_code == 403


def test_cross_tenant_access_is_denied_with_a_production_identity(client, db_session, production_auth):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    user = make_org_member(db_session, org_a.id, role=OrganizationRole.HSE_MANAGER)
    _link_identity(db_session, user_id=user.id, subject="cross-tenant-sub")
    token = make_test_token(subject="cross-tenant-sub")

    response = client.post(
        f"{_ACTIONS_URL}?organization_id={org_b.id}", json=_action_payload(), headers=bearer(token)
    )
    assert response.status_code == 403


def test_inactive_membership_is_denied_with_a_production_identity(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    _link_identity(db_session, user_id=user.id, subject="suspended-sub")
    membership = membership_service.get(db_session, organization_id=org.id, user_id=user.id)
    membership_service.set_status(db_session, membership=membership, status=MembershipStatus.SUSPENDED)
    token = make_test_token(subject="suspended-sub")

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 403


def test_organization_mismatch_is_denied_with_a_production_identity(client, db_session, production_auth):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    user = make_org_member(db_session, org_a.id, role=OrganizationRole.ORG_ADMIN)
    _link_identity(db_session, user_id=user.id, subject="mismatch-sub")
    token = make_test_token(subject="mismatch-sub")

    response = client.get(f"{_ME_URL}?organization_id={org_b.id}", headers=bearer(token))
    assert response.status_code == 403


def test_platform_admin_via_production_identity_has_full_access_without_membership(
    client, db_session, production_auth
):
    org = make_org(db_session)
    admin = make_platform_admin_user(db_session)
    _link_identity(db_session, user_id=admin.id, subject="admin-sub")
    token = make_test_token(subject="admin-sub")

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 200
    assert response.json()["is_platform_admin"] is True


# --- Audit logging -------------------------------------------------------------------------


def test_successful_authentication_is_audited_without_leaking_the_token(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _link_identity(db_session, user_id=user.id, subject="audit-success-sub")
    token = make_test_token(subject="audit-success-sub")

    response = client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))
    assert response.status_code == 200

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.AUTH_SUCCEEDED, AuditLog.user_id == user.id)
        .one()
    )
    serialized = str(entry.event_metadata)
    assert token not in serialized


def test_rejected_authentication_is_audited(client, db_session, production_auth):
    org = make_org(db_session)
    token = make_test_token(expires_delta=timedelta(hours=-1))
    client.get(f"{_ME_URL}?organization_id={org.id}", headers=bearer(token))

    entries = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.AUTH_REJECTED).all()
    assert len(entries) >= 1
    assert all(token not in str(e.event_metadata) for e in entries)


# --- Dual-mode (RequestContext) regression -------------------------------------------------


def test_production_human_and_machine_credentials_both_work_on_the_same_dual_mode_route(
    client, db_session, production_auth
):
    from app.services.api_client_service import api_client_service

    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.HSE_MANAGER)
    _link_identity(db_session, user_id=user.id, subject="dual-mode-sub")
    token = make_test_token(subject="dual-mode-sub")

    human_response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}", json=_action_payload("Human-created"), headers=bearer(token)
    )
    assert human_response.status_code == 201

    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Machine", scopes=[Permission.INTERVENTION_MANAGE]
    )
    machine_response = client.post(
        f"{_ACTIONS_URL}?organization_id={org.id}",
        json=_action_payload("Machine-created"),
        headers={"Authorization": f"Bearer {credential.client_id}:{credential.secret}"},
    )
    assert machine_response.status_code == 201
