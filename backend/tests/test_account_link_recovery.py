"""Account-link recovery, end to end over HTTP, as the redemption page
drives it: a refused sign-in, the code redeemed with that same token,
then a normal sign-in.

Above all: redeeming never changes the account it links. A platform
administrator recovered this way is still a platform administrator, and
an ordinary user gains no role.
"""

from __future__ import annotations

import pytest

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_service import AuditAction
from app.services.identity_link_service import identity_link_service
from app.services.permissions import PLATFORM_ADMIN
from tests.intelligence_test_helpers import (
    make_org,
    make_org_member,
    make_platform_admin_user,
)
from tests.oidc_test_helpers import (
    bearer,
    make_test_token,
    production_auth,  # noqa: F401 -- fixture
)

_REDEEM = "/api/v1/auth/identity-links/redeem"
_ORGS = "/api/v1/auth/organizations"


def _as(subject: str) -> dict:
    return bearer(make_test_token(subject=subject))


def _snapshot(db_session, user_id) -> tuple:
    db_session.expire_all()
    user = db_session.get(User, user_id)
    return (user.platform_role, user.status, user.email, user.name)


@pytest.mark.usefixtures("production_auth")
def test_a_recovered_platform_admin_keeps_platform_role(client, db_session):
    admin = make_platform_admin_user(db_session)
    before = _snapshot(db_session, admin.id)
    assert before[0] == PLATFORM_ADMIN
    created = identity_link_service.create_account_link(
        db_session, target_user_id=admin.id, actor_user_id=None, allow_platform_admin=True
    )
    db_session.commit()

    # Before redemption the sign-in is refused, and the page is shown.
    assert client.get(_ORGS, headers=_as("recovered-admin-sub")).status_code == 403

    response = client.post(_REDEEM, json={"code": created.code}, headers=_as("recovered-admin-sub"))
    assert response.status_code == 200
    assert response.json()["user_id"] == str(admin.id)

    assert _snapshot(db_session, admin.id) == before
    signed_in = client.get(_ORGS, headers=_as("recovered-admin-sub"))
    assert signed_in.status_code == 200
    assert signed_in.json()["is_platform_admin"] is True


@pytest.mark.usefixtures("production_auth")
def test_a_recovered_user_gains_no_role_and_keeps_their_memberships(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    before = _snapshot(db_session, user.id)
    assert before[0] is None
    created = identity_link_service.create_account_link(db_session, target_user_id=user.id, actor_user_id=None)
    db_session.commit()

    assert client.post(_REDEEM, json={"code": created.code}, headers=_as("recovered-user-sub")).status_code == 200

    assert _snapshot(db_session, user.id) == before
    signed_in = client.get(_ORGS, headers=_as("recovered-user-sub")).json()
    assert signed_in["is_platform_admin"] is False
    assert [m["organization_id"] for m in signed_in["memberships"]] == [str(org.id)]


@pytest.mark.usefixtures("production_auth")
def test_the_code_never_reaches_the_audit_log(client, db_session):
    user = make_org_member(db_session, make_org(db_session).id)
    created = identity_link_service.create_account_link(db_session, target_user_id=user.id, actor_user_id=None)
    db_session.commit()

    client.post(_REDEEM, json={"code": created.code + "x"}, headers=_as("someone-sub"))  # refused
    client.post(_REDEEM, json={"code": created.code}, headers=_as("someone-sub"))  # redeemed
    client.post(_REDEEM, json={"code": created.code}, headers=_as("someone-else-sub"))  # used: refused

    rows = db_session.query(AuditLog).filter(
        AuditLog.action.in_(
            [AuditAction.IDENTITY_LINK_GRANT_CREATED, AuditAction.IDENTITY_LINKED, AuditAction.IDENTITY_LINK_REJECTED]
        )
    )
    rendered = " ".join(repr(row.event_metadata) for row in rows)
    assert rendered
    assert created.code not in rendered
    assert created.code[len("sie_link_") :] not in rendered
