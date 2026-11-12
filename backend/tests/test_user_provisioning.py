"""Administrator-added users over HTTP, with real signed JWTs and a fake
Auth0 Management client. See app/services/user_provisioning_service.py."""

import uuid

import pytest

from app.core.config import settings
from app.integrations import auth0_management
from app.integrations.auth0_management import Auth0ManagementError, Auth0User
from app.models.audit_log import AuditLog
from app.models.identity import Identity
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services.audit_service import AuditAction
from app.services.permissions import OrganizationRole
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_platform_admin_user,
)
from tests.oidc_test_helpers import (
    TEST_ISSUER,
    bearer,
    make_test_token,
    production_auth,  # noqa: F401 -- fixture
)


class FakeAuth0:
    """In-memory stand-in for Auth0ManagementClient."""

    def __init__(self):
        self.users: dict[str, Auth0User] = {}
        self.emails_sent: list[str] = []
        self.fail_lookup = False
        self.fail_email = False

    def add(self, email, *, verified=False, provisioned=False) -> Auth0User:
        user = Auth0User(
            user_id=f"auth0|{uuid.uuid4().hex[:24]}",
            email=email.lower(),
            email_verified=verified,
            sie_provisioned=provisioned,
        )
        self.users[user.user_id] = user
        return user

    def find_user_by_email(self, email):
        if self.fail_lookup:
            raise Auth0ManagementError("Auth0 answered GET /api/v2/users-by-email with HTTP 500.")
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    def get_user(self, user_id):
        if self.fail_lookup:
            raise Auth0ManagementError("down")
        return self.users.get(user_id)

    def create_user(self, email, name):
        return self.add(email, provisioned=True)

    def send_set_password_email(self, email):
        if self.fail_email:
            raise Auth0ManagementError("Auth0 answered POST /dbconnections/change_password with HTTP 429.")
        self.emails_sent.append(email)


@pytest.fixture
def auth0(monkeypatch):
    fake = FakeAuth0()
    monkeypatch.setattr(auth0_management, "get_auth0_management_client", lambda: fake)
    return fake


def _as(subject: str) -> dict:
    return bearer(make_test_token(subject=subject))


def _bind(db_session, user, subject: str) -> Identity:
    identity = Identity(user_id=user.id, subject=subject, issuer=TEST_ISSUER, provider="test-idp")
    db_session.add(identity)
    db_session.commit()
    return identity


def _org_with_admin(db_session, name="Adding Org", subject="admin-sub", role=OrganizationRole.ORG_ADMIN):
    org = make_org(db_session, name)
    admin = make_org_member(db_session, org.id, role=role)
    _bind(db_session, admin, subject)
    return org, admin


def _add(client, org, *, email="new.person@example.com", role="VIEWER", name="New Person", subject="admin-sub"):
    body = {"email": email, "role": role}
    if name is not None:
        body["name"] = name
    return client.post(f"/api/v1/organizations/{org.id}/users", json=body, headers=_as(subject))


def _reason(response) -> str:
    assert response.json()["error"]["code"] == "USER_ADD_REJECTED"
    return response.json()["error"]["details"]["reason"]


def _audit(db_session, action):
    return db_session.query(AuditLog).filter(AuditLog.action == action).all()


# --- New person -----------------------------------------------------------------------------


def test_new_person_gets_an_auth0_account_a_bound_sie_account_and_a_set_password_email(
    client, db_session, production_auth, auth0
):
    org, _ = _org_with_admin(db_session)

    response = _add(client, org, email="New.Person@Example.com")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "account_created"
    assert body["email_sent"] is True and body["email_failed"] is False
    assert response.headers["Cache-Control"] == "no-store"
    (auth0_user,) = auth0.users.values()
    assert auth0_user.email == "new.person@example.com" and auth0_user.sie_provisioned
    assert auth0.emails_sent == ["new.person@example.com"]
    user = db_session.get(User, uuid.UUID(body["user_id"]))
    assert user.email == "new.person@example.com" and user.name == "New Person"
    identity = db_session.query(Identity).filter_by(user_id=user.id).one()
    assert (identity.issuer, identity.subject) == (TEST_ISSUER, auth0_user.user_id)
    membership = db_session.query(OrganizationMembership).filter_by(user_id=user.id, organization_id=org.id).one()
    assert membership.role == "VIEWER" and membership.status == "ACTIVE"


def test_the_added_person_can_sign_in_and_reach_the_organization(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    body = _add(client, org).json()
    (auth0_user,) = auth0.users.values()

    me = client.get(f"/api/v1/auth/me?organization_id={org.id}", headers=_as(auth0_user.user_id))

    assert me.status_code == 200, me.text
    assert me.json()["user_id"] == body["user_id"]
    assert me.json()["role"] == "VIEWER"


def test_an_unverified_auth0_account_sie_did_not_create_is_refused(client, db_session, production_auth, auth0):
    """Anyone can sign up with someone else's address; an unverified
    account proves nothing, so it is never bound."""
    org, _ = _org_with_admin(db_session)
    squatter = auth0.add("victim@example.com", verified=False)

    response = _add(client, org, email="victim@example.com")

    assert response.status_code == 409
    assert _reason(response) == "auth0_account_unverified"
    assert db_session.query(Identity).filter_by(subject=squatter.user_id).count() == 0
    assert db_session.query(User).filter(User.email == "victim@example.com").count() == 0
    assert auth0.emails_sent == []


def test_a_verified_auth0_account_is_bound_without_an_email(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    existing = auth0.add("has.login@example.com", verified=True)

    response = _add(client, org, email="has.login@example.com")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "existing_sign_in"
    assert response.json()["email_sent"] is False
    assert auth0.emails_sent == []
    assert db_session.query(Identity).filter_by(subject=existing.user_id).one().issuer == TEST_ISSUER


def test_retrying_after_a_partial_failure_reuses_the_account_sie_created(client, db_session, production_auth, auth0):
    """Auth0 account created but the SIE write failed: the retry finds an
    unverified account tagged sie_provisioned and completes the job."""
    org, _ = _org_with_admin(db_session)
    leftover = auth0.add("retry.me@example.com", verified=False, provisioned=True)

    response = _add(client, org, email="retry.me@example.com")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "account_created"
    assert auth0.emails_sent == ["retry.me@example.com"]
    assert len(auth0.users) == 1
    assert db_session.query(Identity).filter_by(subject=leftover.user_id).count() == 1


def test_an_email_that_fails_to_send_still_adds_the_person_and_can_be_resent(
    client, db_session, production_auth, auth0
):
    org, _ = _org_with_admin(db_session)
    auth0.fail_email = True

    added = _add(client, org).json()

    assert added["outcome"] == "account_created"
    assert added["email_sent"] is False and added["email_failed"] is True
    auth0.fail_email = False
    resend = client.post(
        f"/api/v1/organizations/{org.id}/users/{added['user_id']}/password-email", headers=_as("admin-sub")
    )
    assert resend.status_code == 200, resend.text
    assert resend.json() == {"email_sent": True}
    assert auth0.emails_sent == ["new.person@example.com"]
    assert len(_audit(db_session, AuditAction.USER_PASSWORD_EMAIL_SENT)) == 1


def test_auth0_unavailable_changes_nothing(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    auth0.fail_lookup = True

    response = _add(client, org)

    assert response.status_code == 503
    assert _reason(response) == "auth0_unavailable"
    assert response.json()["error"]["details"]["retryable"] is True
    assert response.headers["Retry-After"] == "5"
    assert db_session.query(User).filter(User.email == "new.person@example.com").count() == 0


def test_not_configured_is_a_clear_501(client, db_session, production_auth, monkeypatch):
    monkeypatch.setattr(auth0_management, "get_auth0_management_client", lambda: None)
    org, _ = _org_with_admin(db_session)

    response = _add(client, org)

    assert response.status_code == 501
    assert _reason(response) == "not_configured"


# --- People SIE already knows ------------------------------------------------------------------


def test_an_existing_sie_user_only_gets_a_membership(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    person = make_org_member(db_session, home.id, role=OrganizationRole.HSE_MANAGER)
    login = auth0.add(person.email, verified=True)
    _bind(db_session, person, login.user_id)

    response = _add(client, org, email=person.email.upper(), role="HSE_ANALYST")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "existing_sie_account"
    assert response.json()["user_id"] == str(person.id)
    roles = {m.organization_id: m.role for m in db_session.query(OrganizationMembership).filter_by(user_id=person.id)}
    assert roles == {home.id: "HSE_MANAGER", org.id: "HSE_ANALYST"}
    assert auth0.emails_sent == []


def test_an_existing_sie_user_whose_sign_in_is_unverified_is_refused(client, db_session, production_auth, auth0):
    """A legacy account's stored email came from an unverified claim, so the
    sign-in provider must confirm the address before it is reused."""
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    person = make_org_member(db_session, home.id)
    login = auth0.add(person.email, verified=False)
    _bind(db_session, person, login.user_id)

    response = _add(client, org, email=person.email)

    assert response.status_code == 409
    assert _reason(response) == "existing_account_unverified"
    assert db_session.query(OrganizationMembership).filter_by(user_id=person.id, organization_id=org.id).count() == 0


def test_a_placeholder_email_account_is_found_through_its_verified_sign_in(
    client, db_session, production_auth, auth0
):
    """The owner's case: SIE stores a placeholder email, Auth0 knows the
    real (verified) one. The bound account gets the membership."""
    org, _ = _org_with_admin(db_session)
    home = make_org(db_session, "Home")
    person = make_org_member(db_session, home.id)
    person.email = "subject@issuer.identity.invalid"
    db_session.commit()
    login = auth0.add("real.address@example.com", verified=True)
    _bind(db_session, person, login.user_id)

    response = _add(client, org, email="real.address@example.com")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "existing_sie_account"
    assert response.json()["user_id"] == str(person.id)


def test_existing_membership_is_never_changed(client, db_session, production_auth, auth0):
    org, admin = _org_with_admin(db_session)
    login = auth0.add(admin.email, verified=True)
    db_session.query(Identity).filter_by(user_id=admin.id).one().subject = login.user_id
    db_session.commit()

    response = _add(client, org, email=admin.email, role="VIEWER", subject=login.user_id)

    assert response.status_code == 409
    assert _reason(response) == "already_member"
    assert db_session.query(OrganizationMembership).filter_by(user_id=admin.id, organization_id=org.id).one().role == "ORG_ADMIN"


def test_a_platform_administrator_is_never_touched(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    platform_admin = make_platform_admin_user(db_session)
    login = auth0.add(platform_admin.email, verified=True)
    _bind(db_session, platform_admin, login.user_id)

    response = _add(client, org, email=platform_admin.email)

    assert response.status_code == 403
    assert _reason(response) == "platform_admin_account"


# --- Authority, tenancy, audit --------------------------------------------------------------


def test_nobody_can_grant_more_than_they_hold(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session, role=OrganizationRole.HSE_MANAGER)

    response = _add(client, org, role="ORG_ADMIN")

    # HSE_MANAGER lacks users:manage, so the route itself refuses.
    assert response.status_code == 403
    assert auth0.users == {}


def test_an_admin_of_one_organization_cannot_add_to_another(client, db_session, production_auth, auth0):
    _org_with_admin(db_session)
    other = make_org(db_session, "Other")

    response = client.post(
        f"/api/v1/organizations/{other.id}/users",
        json={"email": "x@example.com", "role": "VIEWER"},
        headers=_as("admin-sub"),
    )

    assert response.status_code == 403
    assert auth0.users == {}


def test_resend_is_tenant_isolated_and_only_for_sign_ins_sie_created(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    other_org, _ = _org_with_admin(db_session, name="Other", subject="other-admin")
    added = _add(client, org).json()
    outsider = client.post(
        f"/api/v1/organizations/{other_org.id}/users/{added['user_id']}/password-email", headers=_as("other-admin")
    )
    assert outsider.status_code == 404
    assert _reason(outsider) == "member_not_found"

    existing = auth0.add("has.login@example.com", verified=True)
    bound = _add(client, org, email="has.login@example.com").json()
    refused = client.post(
        f"/api/v1/organizations/{org.id}/users/{bound['user_id']}/password-email", headers=_as("admin-sub")
    )
    assert refused.status_code == 409
    assert _reason(refused) == "not_sie_created"
    assert existing.user_id in auth0.users


def test_refusals_and_additions_are_audited_without_the_email(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    auth0.add("victim@example.com", verified=False)
    _add(client, org, email="victim@example.com")
    _add(client, org, email="fine@example.com")

    (refusal,) = _audit(db_session, AuditAction.USER_ADD_REJECTED)
    assert refusal.organization_id == org.id
    assert refusal.event_metadata == {"reason": "auth0_account_unverified", "operation": "add"}
    added = [r for r in _audit(db_session, AuditAction.MEMBER_ADDED) if r.event_metadata.get("via") == "admin_added"]
    assert len(added) == 1 and added[0].event_metadata["outcome"] == "account_created"
    linked = _audit(db_session, AuditAction.IDENTITY_LINKED)
    assert linked[-1].event_metadata["method"] == "admin_added"
    flat = repr([row.event_metadata for row in db_session.query(AuditLog).all()])
    assert "victim@example.com" not in flat and "fine@example.com" not in flat


def test_request_body_rejects_unknown_fields_and_bad_emails(client, db_session, production_auth, auth0):
    org, _ = _org_with_admin(db_session)
    for body in (
        {"email": "not-an-email", "role": "VIEWER"},
        {"email": "a@example.com", "role": "VIEWER", "organization_id": str(uuid.uuid4())},
        {"email": "a@example.com", "role": "SUPERUSER"},
    ):
        response = client.post(f"/api/v1/organizations/{org.id}/users", json=body, headers=_as("admin-sub"))
        assert response.status_code == 422, body
    assert auth0.users == {}


def test_settings_require_all_or_none_of_the_auth0_management_values(monkeypatch):
    from app.core.config import (
        Settings,
        UnsafeConfigurationError,
        validate_startup_settings,
    )

    base = {"APP_ENV": "test", "OIDC_ISSUER": TEST_ISSUER}
    validate_startup_settings(Settings(**base))
    with pytest.raises(UnsafeConfigurationError, match="missing: AUTH0_MANAGEMENT_CLIENT_SECRET"):
        validate_startup_settings(
            Settings(
                **base,
                AUTH0_MANAGEMENT_DOMAIN="t.us.auth0.com",
                AUTH0_MANAGEMENT_CLIENT_ID="id",
                AUTH0_PASSWORD_EMAIL_CLIENT_ID="spa",
            )
        )
    with pytest.raises(UnsafeConfigurationError, match="bare host name"):
        validate_startup_settings(
            Settings(
                **base,
                AUTH0_MANAGEMENT_DOMAIN="https://t.us.auth0.com/",
                AUTH0_MANAGEMENT_CLIENT_ID="id",
                AUTH0_MANAGEMENT_CLIENT_SECRET="secret",
                AUTH0_PASSWORD_EMAIL_CLIENT_ID="spa",
            )
        )
    full = Settings(
        **base,
        AUTH0_MANAGEMENT_DOMAIN="t.us.auth0.com",
        AUTH0_MANAGEMENT_CLIENT_ID="id",
        AUTH0_MANAGEMENT_CLIENT_SECRET="secret",
        AUTH0_PASSWORD_EMAIL_CLIENT_ID="spa",
    )
    validate_startup_settings(full)
    assert full.auth0_management_configured
    assert settings.auth0_management_configured is False
