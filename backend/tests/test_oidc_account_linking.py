"""Account linking over HTTP: unknown identities are refused, and
invitations and account-link grants are the explicit ways in. Real
signed JWTs throughout (tests/oidc_test_helpers.py)."""

import uuid
from datetime import timedelta

import pytest

from app.models.audit_log import AuditLog
from app.models.base import utcnow
from app.models.identity import Identity
from app.models.identity_link_grant import IdentityLinkGrant
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services.audit_service import AuditAction
from app.services.identity_link_service import hash_code, identity_link_service
from app.services.permissions import PLATFORM_ADMIN, OrganizationRole
from app.services.user_service import user_service
from tests.intelligence_test_helpers import make_org, make_org_member, make_platform_admin_user
from tests.oidc_test_helpers import (
    TEST_ISSUER,
    bearer,
    make_test_token,
    production_auth,  # noqa: F401 -- fixture
)

_REDEEM = "/api/v1/auth/identity-links/redeem"
_ORGS = "/api/v1/auth/organizations"
_LINKS = "/api/v1/identity-links"


def _invitations(org_id) -> str:
    return f"/api/v1/organizations/{org_id}/invitations"


def _bind(db_session, user, subject: str) -> Identity:
    identity = Identity(user_id=user.id, subject=subject, issuer=TEST_ISSUER, provider="test-idp")
    db_session.add(identity)
    db_session.commit()
    return identity


def _as(subject: str, **extra) -> dict:
    return bearer(make_test_token(subject=subject, extra_claims=extra or None))


def _org_admin(db_session, org, subject="admin-sub"):
    admin = make_org_member(db_session, org.id, role=OrganizationRole.ORG_ADMIN)
    _bind(db_session, admin, subject)
    return admin


def _platform_admin(db_session, subject="platform-sub"):
    admin = make_platform_admin_user(db_session)
    _bind(db_session, admin, subject)
    return admin


def _invite(client, db_session, org, *, email="new.hire@example.com", role="HSE_ANALYST", admin_subject="admin-sub"):
    response = client.post(_invitations(org.id), json={"email": email, "role": role}, headers=_as(admin_subject))
    assert response.status_code == 201, response.text
    return response


def _signed_in_user_id(client, subject: str, org_id) -> str:
    response = client.get(f"/api/v1/auth/me?organization_id={org_id}", headers=_as(subject))
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _audit(db_session, action):
    return db_session.query(AuditLog).filter(AuditLog.action == action).all()


# --- Login with an existing or unknown identity ----------------------------------------


def test_existing_identity_login_succeeds(client, db_session, production_auth):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _bind(db_session, user, "existing-sub")

    assert _signed_in_user_id(client, "existing-sub", org.id) == str(user.id)


def test_unknown_identity_without_invitation_is_rejected(client, db_session, production_auth):
    users_before = db_session.query(User).count()

    response = client.get(_ORGS, headers=_as("stranger-sub", email="stranger@example.com", email_verified=True))

    assert response.status_code == 403
    assert db_session.query(User).count() == users_before
    assert db_session.query(Identity).filter(Identity.subject == "stranger-sub").count() == 0
    (rejected,) = _audit(db_session, AuditAction.IDENTITY_LINK_REJECTED)
    assert rejected.event_metadata["reason"] == "unknown_identity_no_grant"


def test_verified_email_matching_an_existing_user_is_still_rejected_by_default(client, db_session, production_auth):
    org = make_org(db_session)
    victim = make_org_member(db_session, org.id)

    response = client.get(_ORGS, headers=_as("attacker-sub", email=victim.email, email_verified=True))

    assert response.status_code == 403
    assert db_session.query(Identity).filter(Identity.user_id == victim.id).count() == 0


# --- Invitations -------------------------------------------------------------------------


def test_invitation_based_provisioning_succeeds(client, db_session, production_auth):
    org = make_org(db_session, "Inviting Org")
    _org_admin(db_session, org)
    created = _invite(client, db_session, org).json()

    assert created["code"].startswith("sie_link_")
    redeemed = client.post(_REDEEM, json={"code": created["code"]}, headers=_as("invitee-sub"))

    assert redeemed.status_code == 200, redeemed.text
    new_user_id = uuid.UUID(redeemed.json()["user_id"])
    user = db_session.get(User, new_user_id)
    assert user.email == "new.hire@example.com"
    membership = db_session.query(OrganizationMembership).filter_by(user_id=new_user_id, organization_id=org.id).one()
    assert membership.role == "HSE_ANALYST"
    # And the identity now signs in normally.
    me = client.get(_ORGS, headers=_as("invitee-sub"))
    assert me.status_code == 200
    assert [m["organization_id"] for m in me.json()["memberships"]] == [str(org.id)]
    (linked,) = _audit(db_session, AuditAction.IDENTITY_LINKED)
    assert linked.event_metadata["method"] == "invitation"


def test_creation_response_is_not_cacheable_and_only_the_hash_is_stored(client, db_session, production_auth):
    org = make_org(db_session)
    _org_admin(db_session, org)
    response = _invite(client, db_session, org)

    assert response.headers["cache-control"] == "no-store"
    code = response.json()["code"]
    grant = db_session.get(IdentityLinkGrant, uuid.UUID(response.json()["grant_id"]))
    assert grant.token_sha256 == hash_code(code)
    assert code not in repr([r.event_metadata for r in db_session.query(AuditLog).all()])


def test_invitation_code_is_single_use(client, db_session, production_auth):
    org = make_org(db_session)
    _org_admin(db_session, org)
    code = _invite(client, db_session, org).json()["code"]
    assert client.post(_REDEEM, json={"code": code}, headers=_as("first-sub")).status_code == 200

    second = client.post(_REDEEM, json={"code": code}, headers=_as("second-sub"))

    assert second.status_code == 404
    assert db_session.query(Identity).filter(Identity.subject == "second-sub").count() == 0


def test_expired_invitation_is_rejected(client, db_session, production_auth):
    org = make_org(db_session)
    _org_admin(db_session, org)
    created = _invite(client, db_session, org).json()
    grant = db_session.get(IdentityLinkGrant, uuid.UUID(created["grant_id"]))
    grant.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()

    response = client.post(_REDEEM, json={"code": created["code"]}, headers=_as("late-sub"))

    assert response.status_code == 404


def test_unknown_code_is_rejected_and_audited(client, db_session, production_auth):
    response = client.post(_REDEEM, json={"code": "sie_link_not-a-real-code"}, headers=_as("guess-sub"))

    assert response.status_code == 404
    (row,) = _audit(db_session, AuditAction.IDENTITY_LINK_REJECTED)
    assert row.event_metadata["reason"] == "grant_invalid_or_expired"
    assert "not-a-real-code" not in repr(row.event_metadata)


def test_invitation_never_attaches_to_an_existing_account(client, db_session, production_auth):
    org = make_org(db_session)
    _org_admin(db_session, org)
    other_org = make_org(db_session, "Elsewhere")
    victim = make_org_member(db_session, other_org.id)
    code = _invite(client, db_session, org, email=victim.email).json()["code"]

    response = client.post(_REDEEM, json={"code": code}, headers=_as("attacker-sub"))

    assert response.status_code == 409
    assert db_session.query(Identity).filter(Identity.subject == "attacker-sub").count() == 0
    assert db_session.query(Identity).filter(Identity.user_id == victim.id).count() == 0


def test_already_bound_identity_cannot_redeem_an_invitation(client, db_session, production_auth):
    org = make_org(db_session)
    admin = _org_admin(db_session, org)
    code = _invite(client, db_session, org).json()["code"]

    response = client.post(_REDEEM, json={"code": code}, headers=_as("admin-sub"))

    assert response.status_code == 409
    identity = db_session.query(Identity).filter(Identity.subject == "admin-sub").one()
    assert identity.user_id == admin.id


def test_only_org_admins_can_invite(client, db_session, production_auth):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    _bind(db_session, analyst, "analyst-sub")

    response = client.post(
        _invitations(org.id), json={"email": "x@example.com", "role": "VIEWER"}, headers=_as("analyst-sub")
    )

    assert response.status_code == 403


def test_org_admin_cannot_invite_into_another_organization(client, db_session, production_auth):
    org_a = make_org(db_session, "A")
    org_b = make_org(db_session, "B")
    _org_admin(db_session, org_a)

    response = client.post(
        _invitations(org_b.id), json={"email": "x@example.com", "role": "ORG_ADMIN"}, headers=_as("admin-sub")
    )

    assert response.status_code == 403
    assert db_session.query(IdentityLinkGrant).count() == 0


# --- Account links (explicit, approved linking of an existing account) -----------------


def test_explicit_account_link_flow_succeeds(client, db_session, production_auth):
    _platform_admin(db_session)
    org = make_org(db_session)
    existing = make_org_member(db_session, org.id)  # an account with no identity yet
    created = client.post(_LINKS, json={"user_id": str(existing.id)}, headers=_as("platform-sub"))
    assert created.status_code == 201, created.text

    redeemed = client.post(_REDEEM, json={"code": created.json()["code"]}, headers=_as("migrated-sub"))

    assert redeemed.status_code == 200
    assert redeemed.json()["user_id"] == str(existing.id)
    assert _signed_in_user_id(client, "migrated-sub", org.id) == str(existing.id)
    (linked,) = _audit(db_session, AuditAction.IDENTITY_LINKED)
    assert linked.event_metadata["method"] == "account_link"


def test_only_platform_admins_can_issue_account_links(client, db_session, production_auth):
    org = make_org(db_session)
    _org_admin(db_session, org)
    target = make_org_member(db_session, org.id)

    response = client.post(_LINKS, json={"user_id": str(target.id)}, headers=_as("admin-sub"))

    assert response.status_code == 403


def test_api_cannot_issue_an_account_link_for_a_platform_admin(client, db_session, production_auth):
    _platform_admin(db_session)
    other_admin = make_platform_admin_user(db_session, name="Other Admin")

    response = client.post(_LINKS, json={"user_id": str(other_admin.id)}, headers=_as("platform-sub"))

    assert response.status_code == 403
    assert db_session.query(IdentityLinkGrant).count() == 0


def test_operator_grant_links_a_platform_admin(client, db_session, production_auth):
    admin = make_platform_admin_user(db_session)
    created = identity_link_service.create_account_link(
        db_session, target_user_id=admin.id, actor_user_id=None, allow_platform_admin=True
    )

    response = client.post(_REDEEM, json={"code": created.code}, headers=_as("admin-new-sub"))

    assert response.status_code == 200
    assert response.json()["user_id"] == str(admin.id)


def test_user_promoted_to_platform_admin_after_issue_cannot_be_linked(client, db_session, production_auth):
    _platform_admin(db_session)
    org = make_org(db_session)
    target = make_org_member(db_session, org.id)
    code = client.post(_LINKS, json={"user_id": str(target.id)}, headers=_as("platform-sub")).json()["code"]
    user_service.set_platform_role(db_session, user=target, platform_role=PLATFORM_ADMIN)

    response = client.post(_REDEEM, json={"code": code}, headers=_as("late-sub"))

    assert response.status_code == 403
    assert db_session.query(Identity).filter(Identity.subject == "late-sub").count() == 0


def test_identity_of_another_user_cannot_be_reassigned(client, db_session, production_auth):
    _platform_admin(db_session)
    org = make_org(db_session)
    owner = make_org_member(db_session, org.id, name="Owner")
    _bind(db_session, owner, "owned-sub")
    target = make_org_member(db_session, org.id, name="Target")
    code = client.post(_LINKS, json={"user_id": str(target.id)}, headers=_as("platform-sub")).json()["code"]

    response = client.post(_REDEEM, json={"code": code}, headers=_as("owned-sub"))

    assert response.status_code == 409
    identity = db_session.query(Identity).filter(Identity.subject == "owned-sub").one()
    db_session.refresh(identity)
    assert identity.user_id == owner.id
    grant = db_session.query(IdentityLinkGrant).one()
    assert grant.redeemed_at is None  # a refusal does not burn the code


def test_account_already_linked_for_the_issuer_is_not_given_a_second_identity(client, db_session, production_auth):
    _platform_admin(db_session)
    org = make_org(db_session)
    target = make_org_member(db_session, org.id)
    _bind(db_session, target, "target-sub")
    code = client.post(_LINKS, json={"user_id": str(target.id)}, headers=_as("platform-sub")).json()["code"]

    response = client.post(_REDEEM, json={"code": code}, headers=_as("second-sub"))

    assert response.status_code == 409


def test_orphaned_identity_is_recovered_only_through_an_account_link(client, db_session, production_auth):
    _platform_admin(db_session)
    org = make_org(db_session)
    owner = make_org_member(db_session, org.id)
    db_session.add(Identity(user_id=None, subject="orphan-sub", issuer=TEST_ISSUER, provider="test-idp"))
    db_session.commit()

    assert client.get(_ORGS, headers=_as("orphan-sub", email=owner.email, email_verified=True)).status_code == 403

    code = client.post(_LINKS, json={"user_id": str(owner.id)}, headers=_as("platform-sub")).json()["code"]
    response = client.post(_REDEEM, json={"code": code}, headers=_as("orphan-sub"))

    assert response.status_code == 200
    assert _signed_in_user_id(client, "orphan-sub", org.id) == str(owner.id)
    assert db_session.query(Identity).filter(Identity.subject == "orphan-sub").count() == 1


# --- Redemption endpoint authentication --------------------------------------------------


def test_redeem_requires_a_bearer_token(client, db_session, production_auth):
    assert client.post(_REDEEM, json={"code": "sie_link_whatever"}).status_code == 401


def test_redeem_refuses_a_machine_credential(client, db_session, production_auth):
    response = client.post(_REDEEM, json={"code": "sie_link_whatever"}, headers={"Authorization": "Bearer id:secret"})
    assert response.status_code == 401


def test_redeem_refuses_an_invalid_token(client, db_session, production_auth):
    response = client.post(_REDEEM, json={"code": "sie_link_whatever"}, headers={"Authorization": "Bearer a.b.c"})
    assert response.status_code == 401


def test_operator_script_refuses_without_confirmation(monkeypatch):
    from scripts.create_identity_link_grant import main

    monkeypatch.delenv("SIE_CONFIRM_IDENTITY_LINK_GRANT", raising=False)
    assert main(["--user-id", str(uuid.uuid4())]) == 2


@pytest.mark.parametrize("email", ["no-at-sign", "a@nodot", "a b@example.com"])
def test_invitation_email_is_validated(client, db_session, production_auth, email):
    org = make_org(db_session)
    _org_admin(db_session, org)
    response = client.post(_invitations(org.id), json={"email": email, "role": "VIEWER"}, headers=_as("admin-sub"))
    assert response.status_code == 422
