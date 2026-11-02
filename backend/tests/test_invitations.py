"""Invitation-based registration over HTTP, with real signed JWTs
(tests/oidc_test_helpers.py). See app/services/invitation_service.py."""

import uuid
from datetime import timedelta

import pytest

from app.api import deps_public_rate_limit
from app.core.config import settings
from app.core.rate_limit import LocalRateLimiter
from app.models.audit_log import AuditLog
from app.models.base import utcnow
from app.models.identity import Identity
from app.models.identity_link_grant import IdentityLinkGrant
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services import verified_email as verified_email_module
from app.services.audit_service import AuditAction
from app.services.identity_link_service import hash_code
from app.services.invitation_service import InvitationError, invitation_service
from app.services.permissions import ROLE_PERMISSIONS, OrganizationRole, Permission
from tests.intelligence_test_helpers import make_org, make_org_member, make_platform_admin_user
from tests.oidc_test_helpers import (
    TEST_ISSUER,
    bearer,
    make_test_token,
    production_auth,  # noqa: F401 -- fixture
)

_INSPECT = "/api/v1/invitations/inspect"
_START = "/api/v1/invitations/start"
_ACCEPT = "/api/v1/auth/invitations/accept"


@pytest.fixture(autouse=True)
def _fresh_rate_limiter(monkeypatch):
    """Each test gets its own limiter state, so request counts don't leak
    between tests."""
    limiter = LocalRateLimiter()
    monkeypatch.setattr(deps_public_rate_limit, "get_rate_limiter", lambda: limiter)


@pytest.fixture
def trusted_issuer(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_EMAIL_LINKING_TRUSTED_ISSUERS", TEST_ISSUER)


def _invitations(org_id) -> str:
    return f"/api/v1/organizations/{org_id}/invitations"


def _bind(db_session, user, subject: str) -> Identity:
    identity = Identity(user_id=user.id, subject=subject, issuer=TEST_ISSUER, provider="test-idp")
    db_session.add(identity)
    db_session.commit()
    return identity


def _as(subject: str, *, email: str | None = None, verified: bool | None = None, **token_kwargs) -> dict:
    claims = {}
    if email is not None:
        claims["email"] = email
    if verified is not None:
        claims["email_verified"] = verified
    return bearer(make_test_token(subject=subject, extra_claims=claims or None, **token_kwargs))


def _org_with_admin(db_session, name="Inviting Org", subject="admin-sub"):
    org = make_org(db_session, name)
    admin = make_org_member(db_session, org.id, role=OrganizationRole.ORG_ADMIN)
    _bind(db_session, admin, subject)
    return org, admin


def _invite(client, org, *, email="new.hire@example.com", role="HSE_ANALYST", admin_subject="admin-sub", **extra):
    response = client.post(
        _invitations(org.id), json={"email": email, "role": role, **extra}, headers=_as(admin_subject)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reason(response) -> str:
    return response.json()["error"]["details"]["reason"]


def _audit(db_session, action):
    return db_session.query(AuditLog).filter(AuditLog.action == action).all()


def _grant(db_session, invitation_id) -> IdentityLinkGrant:
    grant = db_session.get(IdentityLinkGrant, uuid.UUID(invitation_id))
    db_session.refresh(grant)
    return grant


# --- Creating invitations ----------------------------------------------------------------


def test_admin_creates_an_invitation_and_the_code_is_shown_once(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)

    response = client.post(
        _invitations(org.id), json={"email": "New.Hire@Example.com", "role": "HSE_ANALYST"}, headers=_as("admin-sub")
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["code"].startswith("sie_link_")
    assert body["invitation"]["email"] == "new.hire@example.com"
    assert body["invitation"]["status"] == "PENDING"
    grant = _grant(db_session, body["invitation"]["id"])
    assert grant.token_sha256 == hash_code(body["code"])
    assert body["code"] not in repr([row.event_metadata for row in db_session.query(AuditLog).all()])
    assert len(_audit(db_session, AuditAction.INVITATION_CREATED)) == 1


def test_custom_expiry_is_applied(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    body = _invite(client, org, expires_in_hours=2)
    grant = _grant(db_session, body["invitation"]["id"])
    expires = grant.expires_at if grant.expires_at.tzinfo else grant.expires_at.replace(tzinfo=utcnow().tzinfo)
    assert timedelta(hours=1, minutes=55) < expires - utcnow() <= timedelta(hours=2)


@pytest.mark.parametrize("email", ["no-at-sign", "a@nodot", "a b@example.com"])
def test_invitation_email_is_validated(client, db_session, production_auth, email):
    org, _ = _org_with_admin(db_session)
    response = client.post(_invitations(org.id), json={"email": email, "role": "VIEWER"}, headers=_as("admin-sub"))
    assert response.status_code == 422


def test_second_open_invitation_for_the_same_email_is_refused(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    _invite(client, org, email="dup@example.com")

    response = client.post(
        _invitations(org.id), json={"email": "DUP@example.com", "role": "VIEWER"}, headers=_as("admin-sub")
    )

    assert response.status_code == 409
    assert _reason(response) == "open_invitation_exists"


def test_existing_member_cannot_be_invited_again(client, db_session, production_auth):
    org, admin = _org_with_admin(db_session)

    response = client.post(
        _invitations(org.id), json={"email": admin.email, "role": "VIEWER"}, headers=_as("admin-sub")
    )

    assert response.status_code == 409
    assert _reason(response) == "already_member"


def test_only_users_managers_can_invite(client, db_session, production_auth):
    org = make_org(db_session)
    analyst = make_org_member(db_session, org.id, role=OrganizationRole.HSE_ANALYST)
    _bind(db_session, analyst, "analyst-sub")

    response = client.post(
        _invitations(org.id), json={"email": "x@example.com", "role": "VIEWER"}, headers=_as("analyst-sub")
    )

    assert response.status_code == 403


def test_inviter_cannot_grant_a_role_beyond_their_own_permissions(db_session):
    org = make_org(db_session)
    admin = make_org_member(db_session, org.id)
    limited = ROLE_PERMISSIONS[OrganizationRole.HSE_ANALYST] | {Permission.USERS_MANAGE}

    with pytest.raises(InvitationError) as exc:
        invitation_service.create(
            db_session,
            organization_id=org.id,
            email="x@example.com",
            role=OrganizationRole.ORG_ADMIN,
            actor_user_id=admin.id,
            actor_permissions=frozenset(limited),
        )

    assert exc.value.reason == "role_exceeds_authority"


def test_platform_admin_can_invite_into_any_organization(client, db_session, production_auth):
    org = make_org(db_session)
    platform_admin = make_platform_admin_user(db_session)
    _bind(db_session, platform_admin, "platform-sub")

    response = client.post(
        _invitations(org.id), json={"email": "p@example.com", "role": "ORG_ADMIN"}, headers=_as("platform-sub")
    )

    assert response.status_code == 201


# --- Cross-tenant isolation of the administrator routes ----------------------------------


def test_admin_cannot_list_resend_or_revoke_another_organizations_invitations(client, db_session, production_auth):
    org_a, _ = _org_with_admin(db_session, "A", subject="admin-a")
    org_b, _ = _org_with_admin(db_session, "B", subject="admin-b")
    b_invitation = _invite(client, org_b, admin_subject="admin-b")["invitation"]["id"]
    headers = _as("admin-a")

    assert client.get(_invitations(org_b.id), headers=headers).status_code == 403
    assert client.post(f"{_invitations(org_b.id)}/{b_invitation}/revoke", headers=headers).status_code == 403
    assert client.post(f"{_invitations(org_b.id)}/{b_invitation}/resend", headers=headers).status_code == 403
    # Through its own organization's path, B's invitation simply doesn't exist.
    assert client.post(f"{_invitations(org_a.id)}/{b_invitation}/revoke", headers=headers).status_code == 404
    assert client.post(f"{_invitations(org_a.id)}/{b_invitation}/resend", headers=headers).status_code == 404
    assert _grant(db_session, b_invitation).status == "PENDING"


def test_admin_list_shows_status_and_never_the_code(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    listed = client.get(_invitations(org.id), headers=_as("admin-sub")).json()

    assert [row["status"] for row in listed] == ["PENDING"]
    assert created["code"] not in repr(listed)
    assert "token_sha256" not in repr(listed)
    filtered = client.get(f"{_invitations(org.id)}?status=REVOKED", headers=_as("admin-sub")).json()
    assert filtered == []


# --- Invitee: inspect and start ----------------------------------------------------------


def test_inspect_shows_what_the_invitation_is_for(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session, "Acme Safety")
    code = _invite(client, org)["code"]

    response = client.post(_INSPECT, json={"token": code})

    assert response.status_code == 200
    body = response.json()
    assert body["organization_name"] == "Acme Safety"
    assert body["invited_email"] == "new.hire@example.com"
    assert body["role"] == "HSE_ANALYST"
    assert body["status"] == "PENDING"
    assert set(body["methods"]) == {"password", "sso"}


def test_inspect_unknown_token_is_404(client, db_session, production_auth):
    response = client.post(_INSPECT, json={"token": "sie_link_not-a-real-code"})
    assert response.status_code == 404
    assert _reason(response) == "invitation_not_found"


@pytest.mark.parametrize("method", ["password", "sso"])
def test_start_records_registration_started(client, db_session, production_auth, method):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    response = client.post(_START, json={"token": created["code"], "method": method})

    assert response.json()["status"] == "REGISTRATION_STARTED"
    assert _grant(db_session, created["invitation"]["id"]).registration_started_at is not None
    (started,) = _audit(db_session, AuditAction.INVITATION_REGISTRATION_STARTED)
    assert started.event_metadata["method"] == method


def test_start_rejects_an_unknown_method(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]
    assert client.post(_START, json={"token": code, "method": "magic"}).status_code == 422


# --- Accept: new user --------------------------------------------------------------------


def test_new_user_with_verified_matching_email_registers_and_joins(client, db_session, production_auth, trusted_issuer):
    org, admin = _org_with_admin(db_session)
    created = _invite(client, org)
    client.post(_START, json={"token": created["code"], "method": "password"})

    response = client.post(
        _ACCEPT,
        json={"token": created["code"], "full_name": "New Hire"},
        headers=_as("invitee-sub", email="New.Hire@example.com", verified=True),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "account_created"
    assert body["organization_id"] == str(org.id)
    assert body["role"] == "HSE_ANALYST"
    user = db_session.get(User, uuid.UUID(body["user_id"]))
    assert (user.email, user.name) == ("new.hire@example.com", "New Hire")
    membership = db_session.query(OrganizationMembership).filter_by(user_id=user.id, organization_id=org.id).one()
    assert (membership.role, membership.status.value) == ("HSE_ANALYST", "ACTIVE")
    grant = _grant(db_session, created["invitation"]["id"])
    assert grant.status == "ACCEPTED"
    assert grant.verified_at is not None and grant.redeemed_at is not None
    assert grant.accepted_membership_id == membership.id
    me = client.get(f"/api/v1/auth/me?organization_id={org.id}", headers=_as("invitee-sub"))
    assert me.status_code == 200
    (accepted,) = _audit(db_session, AuditAction.INVITATION_ACCEPTED)
    assert accepted.organization_id == org.id
    assert accepted.event_metadata["outcome"] == "account_created"


def test_no_organization_access_before_acceptance(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    _invite(client, org)

    response = client.get(f"/api/v1/auth/me?organization_id={org.id}", headers=_as("invitee-sub"))

    assert response.status_code == 403


def test_unverified_email_is_refused_then_accepted_once_verified(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    first = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=False),
    )

    assert first.status_code == 403
    assert _reason(first) == "email_not_verified"
    assert _grant(db_session, created["invitation"]["id"]).status == "REGISTRATION_STARTED"
    assert db_session.query(User).filter(User.email == "new.hire@example.com").count() == 0

    second = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )
    assert second.status_code == 200


def test_missing_email_verified_claim_is_refused(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("invitee-sub", email="new.hire@example.com"))

    assert response.status_code == 403
    assert _reason(response) == "email_not_verified"


def test_issuer_not_trusted_for_email_is_refused_by_default(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(
        _ACCEPT, json={"token": code}, headers=_as("invitee-sub", email="new.hire@example.com", verified=True)
    )

    assert response.status_code == 403
    assert _reason(response) == "issuer_not_trusted_for_email"


@pytest.mark.parametrize(
    "token_kwargs",
    [{"issuer": "https://evil.example.com"}, {"audience": "some-other-api"}, {"expires_delta": timedelta(seconds=-5)}],
    ids=["wrong issuer", "wrong audience", "expired token"],
)
def test_accept_requires_a_valid_token_for_this_deployment(
    client, db_session, production_auth, trusted_issuer, token_kwargs
):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(
        _ACCEPT,
        json={"token": code},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True, **token_kwargs),
    )

    assert response.status_code == 401


def test_accept_requires_a_bearer_token(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]
    assert client.post(_ACCEPT, json={"token": code}).status_code == 401
    assert client.post(_ACCEPT, json={"token": code}, headers={"Authorization": "Bearer id:secret"}).status_code == 401


def test_email_mismatch_is_refused_and_counted(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    response = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("attacker-sub", email="attacker@example.com", verified=True),
    )

    assert response.status_code == 403
    assert _reason(response) == "email_mismatch"
    assert _grant(db_session, created["invitation"]["id"]).failed_attempts == 1
    assert db_session.query(Identity).filter(Identity.subject == "attacker-sub").count() == 0


def test_repeated_mismatches_revoke_the_invitation(client, db_session, production_auth, trusted_issuer, monkeypatch):
    monkeypatch.setattr(settings, "INVITATION_MAX_FAILED_ATTEMPTS", 3)
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    headers = _as("attacker-sub", email="attacker@example.com", verified=True)

    for _ in range(3):
        client.post(_ACCEPT, json={"token": created["code"]}, headers=headers)
    grant = _grant(db_session, created["invitation"]["id"])
    assert grant.status == "REVOKED"

    legit = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )
    assert legit.status_code == 410
    assert _reason(legit) == "invitation_revoked"


def test_new_identity_for_an_existing_accounts_email_is_refused(client, db_session, production_auth, trusted_issuer):
    """Duplicate-account and takeover prevention: an existing account is
    joined only by signing in with its already-linked identity."""
    org, _ = _org_with_admin(db_session)
    other = make_org(db_session, "Elsewhere")
    existing = make_org_member(db_session, other.id)
    code = _invite(client, org, email=existing.email)["code"]

    response = client.post(
        _ACCEPT, json={"token": code}, headers=_as("new-idp-sub", email=existing.email, verified=True)
    )

    assert response.status_code == 409
    assert _reason(response) == "existing_account_sign_in_required"
    assert db_session.query(Identity).filter(Identity.subject == "new-idp-sub").count() == 0
    assert db_session.query(User).filter(User.email == existing.email).count() == 1


def test_platform_admin_email_cannot_be_claimed_by_a_new_identity(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    platform_admin = make_platform_admin_user(db_session)
    code = _invite(client, org, email=platform_admin.email)["code"]

    response = client.post(
        _ACCEPT, json={"token": code}, headers=_as("impostor-sub", email=platform_admin.email, verified=True)
    )

    assert response.status_code == 409
    assert db_session.query(Identity).filter(Identity.user_id == platform_admin.id).count() == 0


# --- Accept: existing user ---------------------------------------------------------------


def test_existing_user_signs_in_and_accepts_keeping_other_memberships(
    client, db_session, production_auth, trusted_issuer
):
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home Org")
    existing = make_org_member(db_session, home.id, role=OrganizationRole.HSE_MANAGER)
    _bind(db_session, existing, "existing-sub")
    created = _invite(client, org, email=existing.email.upper(), role="VIEWER")

    response = client.post(
        _ACCEPT, json={"token": created["code"]}, headers=_as("existing-sub", email=existing.email, verified=True)
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "existing_account"
    assert response.json()["user_id"] == str(existing.id)
    roles = {m.organization_id: m.role for m in db_session.query(OrganizationMembership).filter_by(user_id=existing.id)}
    assert roles == {home.id: "HSE_MANAGER", org.id: "VIEWER"}
    assert db_session.query(Identity).filter(Identity.user_id == existing.id).count() == 1


def test_legacy_account_with_an_unverified_email_cannot_accept_by_its_stored_email(
    client, db_session, production_auth, trusted_issuer
):
    """Before #69, accounts were provisioned from the token's email with no
    email_verified check, so a matching User.email proves nothing. The
    sign-in must itself verify the invited address."""
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    squatter = make_org_member(db_session, home.id)  # User.email == the address about to be invited
    _bind(db_session, squatter, "squatter-sub")
    code = _invite(client, org, email=squatter.email)["code"]

    for headers in (
        _as("squatter-sub"),  # no email claims at all
        _as("squatter-sub", email=squatter.email),  # email_verified missing
        _as("squatter-sub", email=squatter.email, verified=False),
    ):
        response = client.post(_ACCEPT, json={"token": code}, headers=headers)
        assert response.status_code == 403, response.text
        assert _reason(response) in {"email_claim_missing", "email_not_verified"}

    assert db_session.query(OrganizationMembership).filter_by(user_id=squatter.id, organization_id=org.id).count() == 0


def test_existing_account_needs_a_trusted_issuer_to_accept(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    existing = make_org_member(db_session, home.id)
    _bind(db_session, existing, "existing-sub")
    code = _invite(client, org, email=existing.email)["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("existing-sub", email=existing.email, verified=True))

    assert response.status_code == 403
    assert _reason(response) == "issuer_not_trusted_for_email"
    assert db_session.query(OrganizationMembership).filter_by(user_id=existing.id, organization_id=org.id).count() == 0


def test_existing_user_with_a_different_email_is_refused(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    someone = make_org_member(db_session, home.id)
    _bind(db_session, someone, "someone-sub")
    code = _invite(client, org, email="intended.person@example.com")["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("someone-sub"))

    assert response.status_code == 403
    assert _reason(response) == "email_mismatch"
    assert db_session.query(OrganizationMembership).filter_by(user_id=someone.id, organization_id=org.id).count() == 0


def test_existing_membership_is_never_overwritten(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    member = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)
    _bind(db_session, member, "member-sub")
    membership = db_session.query(OrganizationMembership).filter_by(user_id=member.id, organization_id=org.id).one()
    membership.status = membership.status.__class__("SUSPENDED")
    db_session.commit()
    code = invitation_service.create(
        db_session,
        organization_id=org.id,
        email="placeholder@example.com",
        role=OrganizationRole.ORG_ADMIN,
        actor_user_id=member.id,
        actor_permissions=frozenset(Permission),
    ).code
    grant = db_session.query(IdentityLinkGrant).filter(IdentityLinkGrant.token_sha256 == hash_code(code)).one()
    grant.invited_email = member.email.lower()
    db_session.commit()

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("member-sub", email=member.email, verified=True))

    assert response.status_code == 409
    assert _reason(response) == "membership_exists"
    db_session.refresh(membership)
    assert (membership.role, membership.status.value) == ("VIEWER", "SUSPENDED")


def test_inactive_existing_account_cannot_accept(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    user = make_org_member(db_session, home.id)
    _bind(db_session, user, "inactive-sub")
    code = _invite(client, org, email=user.email)["code"]
    user.status = "inactive"
    db_session.commit()

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("inactive-sub"))

    assert response.status_code == 403


# --- Organization and role cannot be changed by the invitee ------------------------------


@pytest.mark.parametrize("field", [{"organization_id": str(uuid.uuid4())}, {"role": "ORG_ADMIN"}])
def test_accept_body_cannot_carry_organization_or_role(client, db_session, production_auth, trusted_issuer, field):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org, role="VIEWER")["code"]

    response = client.post(
        _ACCEPT,
        json={"token": code, **field},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )

    assert response.status_code == 422
    assert db_session.query(Identity).filter(Identity.subject == "invitee-sub").count() == 0


# --- Expired, revoked, reused, resent ----------------------------------------------------


def test_expired_invitation_shows_expired_and_cannot_be_accepted(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    grant = _grant(db_session, created["invitation"]["id"])
    grant.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()

    assert client.post(_INSPECT, json={"token": created["code"]}).json()["status"] == "EXPIRED"
    response = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )

    assert response.status_code == 410
    assert _reason(response) == "invitation_expired"
    assert _grant(db_session, created["invitation"]["id"]).status == "EXPIRED"


def test_revoked_invitation_cannot_be_accepted(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    revoked = client.post(f"{_invitations(org.id)}/{created['invitation']['id']}/revoke", headers=_as("admin-sub"))
    assert revoked.json()["status"] == "REVOKED"

    response = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )

    assert response.status_code == 410
    assert _reason(response) == "invitation_revoked"
    assert len(_audit(db_session, AuditAction.INVITATION_REVOKED)) == 1


def test_redeemed_invitation_cannot_be_reused(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]
    headers = _as("invitee-sub", email="new.hire@example.com", verified=True)
    assert client.post(_ACCEPT, json={"token": code}, headers=headers).status_code == 200

    again = client.post(
        _ACCEPT, json={"token": code}, headers=_as("other-sub", email="new.hire@example.com", verified=True)
    )

    assert again.status_code == 410
    assert _reason(again) == "invitation_already_used"


def test_accepted_invitation_cannot_be_revoked_or_resent(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )
    base = f"{_invitations(org.id)}/{created['invitation']['id']}"

    assert client.post(f"{base}/revoke", headers=_as("admin-sub")).status_code == 409
    assert client.post(f"{base}/resend", headers=_as("admin-sub")).status_code == 409


def test_resend_replaces_the_code_and_the_old_link_stops_working(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    resent = client.post(f"{_invitations(org.id)}/{created['invitation']['id']}/resend", headers=_as("admin-sub"))

    assert resent.status_code == 200
    new_code = resent.json()["code"]
    assert new_code != created["code"]
    assert resent.json()["invitation"]["issue_count"] == 2
    assert client.post(_INSPECT, json={"token": created["code"]}).status_code == 404
    accept = client.post(
        _ACCEPT, json={"token": new_code}, headers=_as("invitee-sub", email="new.hire@example.com", verified=True)
    )
    assert accept.status_code == 200
    assert len(_audit(db_session, AuditAction.INVITATION_RESENT)) == 1


def test_resend_revives_an_expired_invitation(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    grant = _grant(db_session, created["invitation"]["id"])
    grant.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()

    resent = client.post(f"{_invitations(org.id)}/{created['invitation']['id']}/resend", headers=_as("admin-sub"))

    assert resent.status_code == 200
    assert resent.json()["invitation"]["status"] == "PENDING"


def test_new_invitation_is_allowed_once_the_previous_one_expired(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    first = _invite(client, org)
    grant = _grant(db_session, first["invitation"]["id"])
    grant.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()

    second = client.post(
        _invitations(org.id), json={"email": "new.hire@example.com", "role": "VIEWER"}, headers=_as("admin-sub")
    )

    assert second.status_code == 201
    assert _grant(db_session, first["invitation"]["id"]).status == "EXPIRED"


# --- Rate limiting -------------------------------------------------------------------------


def test_public_invitation_endpoints_are_rate_limited(client, db_session, production_auth, monkeypatch):
    monkeypatch.setattr(settings, "INVITATION_RATE_LIMIT_PER_MINUTE", 3)
    statuses = [client.post(_INSPECT, json={"token": f"sie_link_guess-{i:04d}"}).status_code for i in range(5)]

    assert statuses[:3] == [404, 404, 404]
    assert statuses[3:] == [429, 429]
    limited = client.post(_INSPECT, json={"token": "sie_link_guess-xxxx"})
    assert int(limited.headers["retry-after"]) >= 1


def test_accept_is_rate_limited(client, db_session, production_auth, trusted_issuer, monkeypatch):
    monkeypatch.setattr(settings, "INVITATION_RATE_LIMIT_PER_MINUTE", 2)
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]
    headers = _as("attacker-sub", email="attacker@example.com", verified=True)

    statuses = [client.post(_ACCEPT, json={"token": code}, headers=headers).status_code for _ in range(3)]

    assert statuses == [403, 403, 429]


def test_client_ip_honours_only_the_configured_proxy_hops(monkeypatch):
    class _Req:
        def __init__(self, xff, peer):
            self.headers = {"x-forwarded-for": xff} if xff else {}
            self.client = type("C", (), {"host": peer})()

    req = _Req("1.1.1.1, 203.0.113.9", "10.0.0.1")
    assert deps_public_rate_limit.client_ip(req) == "10.0.0.1"  # 0 hops: socket peer
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    assert deps_public_rate_limit.client_ip(req) == "203.0.113.9"  # the value the proxy appended
    assert deps_public_rate_limit.client_ip(_Req(None, "10.0.0.1")) == "10.0.0.1"


# --- Email from the UserInfo endpoint -----------------------------------------------------


def test_userinfo_endpoint_supplies_the_verified_email(
    client, db_session, production_auth, trusted_issuer, monkeypatch
):
    monkeypatch.setattr(settings, "OIDC_USERINFO_URL", "https://test-issuer.example.com/userinfo")
    monkeypatch.setattr(
        verified_email_module,
        "_fetch_userinfo",
        lambda url, token: {"sub": "invitee-sub", "email": "new.hire@example.com", "email_verified": True},
    )
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    # The access token itself carries no email at all.
    response = client.post(_ACCEPT, json={"token": code}, headers=_as("invitee-sub"))

    assert response.status_code == 200


def test_userinfo_for_a_different_subject_is_ignored(client, db_session, production_auth, trusted_issuer, monkeypatch):
    monkeypatch.setattr(settings, "OIDC_USERINFO_URL", "https://test-issuer.example.com/userinfo")
    monkeypatch.setattr(
        verified_email_module,
        "_fetch_userinfo",
        lambda url, token: {"sub": "someone-else", "email": "new.hire@example.com", "email_verified": True},
    )
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("invitee-sub"))

    assert response.status_code == 403
    assert _reason(response) == "email_verification_failed"


def test_userinfo_outage_is_a_retryable_refusal_that_counts_no_attempt(
    client, db_session, production_auth, trusted_issuer, monkeypatch
):
    """A provider outage is not "your sign-in has no email": nothing is
    verified (fail closed), but the invitee is told to retry and the
    invitation is not charged a failed attempt."""
    monkeypatch.setattr(settings, "OIDC_USERINFO_URL", "https://test-issuer.example.com/userinfo")

    def unavailable(url, token):
        raise verified_email_module._Unavailable

    monkeypatch.setattr(verified_email_module, "_fetch_userinfo", unavailable)
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("invitee-sub"))

    assert response.status_code == 503
    assert _reason(response) == "email_verification_unavailable"
    assert response.json()["error"]["details"]["retryable"] is True
    assert response.headers["retry-after"] == "5"
    grant = db_session.query(IdentityLinkGrant).filter(IdentityLinkGrant.token_sha256 == hash_code(code)).one()
    db_session.refresh(grant)
    assert grant.failed_attempts == 0
    assert grant.status in ("PENDING", "REGISTRATION_STARTED")
    assert db_session.query(User).filter(User.email == "new.hire@example.com").count() == 0


@pytest.mark.parametrize(
    "status_code, exc",
    [(500, None), (404, None), (None, "timeout")],
)
def test_userinfo_transport_failures_are_unavailable(monkeypatch, status_code, exc):
    import httpx

    from app.services.identity_service import ExternalIdentityClaims

    monkeypatch.setattr(settings, "OIDC_USERINFO_URL", "https://idp.example.com/userinfo")

    def fake_get(url, **kwargs):
        if exc:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(status_code, json={"error": "x"})

    monkeypatch.setattr(verified_email_module.httpx, "get", fake_get)
    claims = ExternalIdentityClaims(subject="s", issuer=TEST_ISSUER, email=None, display_name=None, provider="t")

    result = verified_email_module.resolve_verified_email(claims, "token")

    assert (result.email, result.email_verified, result.source) == (None, None, "userinfo_unavailable")


def test_a_plaintext_userinfo_url_never_receives_the_token_on_a_deployment(
    client, db_session, production_auth, trusted_issuer, monkeypatch
):
    monkeypatch.setattr(settings, "OIDC_USERINFO_URL", "http://test-issuer.example.com/userinfo")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    calls = []
    monkeypatch.setattr(verified_email_module.httpx, "get", lambda *a, **k: calls.append(a))
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    response = client.post(_ACCEPT, json={"token": code}, headers=_as("invitee-sub"))

    assert calls == []
    assert response.status_code == 403
    assert _reason(response) == "email_verification_failed"


# --- Audit -----------------------------------------------------------------------------------


def test_rejections_are_audited_without_secrets(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    code = _invite(client, org)["code"]

    client.post(
        _ACCEPT, json={"token": code}, headers=_as("secret-subject", email="private@example.com", verified=True)
    )

    (row,) = _audit(db_session, AuditAction.INVITATION_REJECTED)
    assert row.organization_id == org.id
    assert row.event_metadata["reason"] == "email_mismatch"
    flat = repr(row.event_metadata)
    for secret in (code, "secret-subject", "private@example.com"):
        assert secret not in flat


# --- Viewing one invitation ------------------------------------------------------------------


def test_admin_views_one_invitations_status(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)

    response = client.get(f"{_invitations(org.id)}/{created['invitation']['id']}", headers=_as("admin-sub"))

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["email"], body["role"]) == ("PENDING", "new.hire@example.com", "HSE_ANALYST")
    assert created["code"] not in repr(body)


def test_viewing_another_organizations_invitation_is_refused(client, db_session, production_auth):
    org_a, _ = _org_with_admin(db_session, "A", subject="admin-a")
    org_b, _ = _org_with_admin(db_session, "B", subject="admin-b")
    b_id = _invite(client, org_b, admin_subject="admin-b")["invitation"]["id"]

    assert client.get(f"{_invitations(org_b.id)}/{b_id}", headers=_as("admin-a")).status_code == 403
    assert client.get(f"{_invitations(org_a.id)}/{b_id}", headers=_as("admin-a")).status_code == 404


# --- Transaction rollback --------------------------------------------------------------------


def test_a_failure_during_acceptance_leaves_nothing_behind(
    client, db_session, production_auth, trusted_issuer, monkeypatch
):
    """If anything fails after the user, identity and membership are
    written but before commit, all of it rolls back and the invitation
    stays open."""
    from app.services import invitation_service as module

    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    real_log = module.audit_service.log

    def failing_log(db, *, action, **kwargs):
        if action == AuditAction.INVITATION_ACCEPTED:
            raise RuntimeError("simulated failure before commit")
        return real_log(db, action=action, **kwargs)

    monkeypatch.setattr(module.audit_service, "log", failing_log)

    with pytest.raises(RuntimeError):
        client.post(
            _ACCEPT,
            json={"token": created["code"]},
            headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
        )

    db_session.expire_all()
    assert db_session.query(User).filter(User.email == "new.hire@example.com").count() == 0
    assert db_session.query(Identity).filter(Identity.subject == "invitee-sub").count() == 0
    assert db_session.query(OrganizationMembership).filter_by(organization_id=org.id).count() == 1  # the admin only
    grant = _grant(db_session, created["invitation"]["id"])
    assert grant.status == "PENDING" and grant.redeemed_at is None

    monkeypatch.setattr(module.audit_service, "log", real_log)
    retry = client.post(
        _ACCEPT,
        json={"token": created["code"]},
        headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
    )
    assert retry.status_code == 200


# --- Write rate limits on administration ---------------------------------------------------


def test_invitation_writes_share_the_write_rate_limit(client, db_session, production_auth, monkeypatch):
    """Create, resend and revoke are write requests: with RATE_LIMIT_ENABLED
    they are limited like every other write (#69's create route was)."""
    from app.api import deps_rate_limit

    limiter = LocalRateLimiter()
    monkeypatch.setattr(deps_rate_limit, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WRITE_REQUESTS_PER_MINUTE", 3)
    org, _ = _org_with_admin(db_session)

    created = _invite(client, org)  # write 1
    invitation_id = created["invitation"]["id"]
    assert client.post(f"{_invitations(org.id)}/{invitation_id}/resend", headers=_as("admin-sub")).status_code == 200
    assert client.post(f"{_invitations(org.id)}/{invitation_id}/revoke", headers=_as("admin-sub")).status_code == 200

    for path, body in (
        (_invitations(org.id), {"email": "another@example.com", "role": "VIEWER"}),
        (f"{_invitations(org.id)}/{invitation_id}/resend", None),
        (f"{_invitations(org.id)}/{invitation_id}/revoke", None),
    ):
        response = client.post(path, json=body, headers=_as("admin-sub"))
        assert response.status_code == 429, path
    # Reads are not charged to the write budget.
    assert client.get(_invitations(org.id), headers=_as("admin-sub")).status_code == 200


# --- Cache-Control -----------------------------------------------------------------------------


def test_every_invitation_response_is_no_store_including_errors(client, db_session, production_auth, trusted_issuer):
    org, _ = _org_with_admin(db_session)
    created = _invite(client, org)
    invitation_id = created["invitation"]["id"]
    responses = {
        "list": client.get(_invitations(org.id), headers=_as("admin-sub")),
        "get": client.get(f"{_invitations(org.id)}/{invitation_id}", headers=_as("admin-sub")),
        "get 404": client.get(f"{_invitations(org.id)}/{uuid.uuid4()}", headers=_as("admin-sub")),
        "list 401": client.get(_invitations(org.id)),
        "create 422": client.post(_invitations(org.id), json={"email": "x"}, headers=_as("admin-sub")),
        "inspect 404": client.post(_INSPECT, json={"token": "sie_link_" + "x" * 40}),
        "accept 200": client.post(
            _ACCEPT,
            json={"token": created["code"]},
            headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
        ),
        "accept 410": client.post(
            _ACCEPT,
            json={"token": created["code"]},
            headers=_as("invitee-sub", email="new.hire@example.com", verified=True),
        ),
        "redeem 401": client.post("/api/v1/auth/identity-links/redeem", json={"code": "sie_link_" + "y" * 40}),
    }
    expected = {
        "list": 200, "get": 200, "get 404": 404, "list 401": 401, "create 422": 422,
        "inspect 404": 404, "accept 200": 200, "accept 410": 410, "redeem 401": 401,
    }
    for name, response in responses.items():
        assert response.status_code == expected[name], (name, response.text)
        assert response.headers.get("cache-control") == "no-store", name


def test_no_store_is_scoped_to_invitation_and_identity_link_paths():
    from app.core.cache_control import is_no_store_path

    for path in (
        "/api/v1/invitations/inspect",
        "/api/v1/auth/invitations/accept",
        "/api/v1/organizations/abc/invitations",
        "/api/v1/organizations/abc/invitations/def/resend",
        "/api/v1/identity-links",
        "/api/v1/auth/identity-links/redeem",
    ):
        assert is_no_store_path(path), path
    for path in ("/health", "/api/v1/organizations/abc", "/api/v1/organizations/abc/members", "/api/v1/invitationsx"):
        assert not is_no_store_path(path), path


# --- Resend after expiry -----------------------------------------------------------------------


def test_resending_an_expired_invitation_is_not_blocked_by_a_newer_expired_one(
    client, db_session, production_auth
):
    """A expires; creating B marks A expired; B expires too but is still
    stored as open. Resending A must succeed: nothing live holds the slot."""
    org, _ = _org_with_admin(db_session)
    first = _invite(client, org)["invitation"]["id"]
    _expire(db_session, first)
    second = _invite(client, org)["invitation"]["id"]  # marks the first EXPIRED
    _expire(db_session, second)  # past expiry, status still PENDING

    response = client.post(f"{_invitations(org.id)}/{first}/resend", headers=_as("admin-sub"))

    assert response.status_code == 200, response.text
    rows = {str(g.id): g.status for g in db_session.query(IdentityLinkGrant).populate_existing()}
    assert rows[first] == "PENDING"
    assert rows[second] == "EXPIRED"


def test_resend_still_refuses_while_another_invitation_is_live(client, db_session, production_auth):
    org, _ = _org_with_admin(db_session)
    first = _invite(client, org)["invitation"]["id"]
    _expire(db_session, first)
    _invite(client, org)  # live

    response = client.post(f"{_invitations(org.id)}/{first}/resend", headers=_as("admin-sub"))

    assert response.status_code == 409
    assert _reason(response) == "open_invitation_exists"


def _expire(db_session, invitation_id: str) -> None:
    grant = db_session.get(IdentityLinkGrant, uuid.UUID(invitation_id))
    grant.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()
