"""Identity-link redemption on real PostgreSQL: the row lock that makes a
code single-use under concurrency, case-insensitive email collision, and
the table's CHECK constraints. Skipped without a reachable PostgreSQL
(tests/postgres_support.py)."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.base import utcnow
from app.models.identity import Identity
from app.models.identity_link_grant import IdentityLinkGrant
from app.models.user import User
from app.services.identity_link_service import GrantRedemptionError, identity_link_service
from app.services.identity_service import ExternalIdentityClaims
from app.services.permissions import OrganizationRole
from tests.intelligence_test_helpers import make_org, make_org_member
from tests.postgres_support import requires_postgres

ISSUER = "https://pg-issuer.example.com"


def _claims(subject: str) -> ExternalIdentityClaims:
    return ExternalIdentityClaims(subject=subject, issuer=ISSUER, email=None, display_name=None, provider="test")


@requires_postgres
def test_concurrent_redemptions_of_one_code_bind_exactly_one_identity(pg_session):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    code = identity_link_service.create_invitation(
        pg_session,
        organization_id=org.id,
        email="race@example.com",
        role=OrganizationRole.VIEWER,
        actor_user_id=admin.id,
    ).code
    factory = sessionmaker(bind=pg_session.get_bind())
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def redeem(subject: str) -> None:
        session = factory()
        try:
            barrier.wait()
            identity_link_service.redeem(session, claims=_claims(subject), code=code)
            outcomes.append("ok")
        except GrantRedemptionError as exc:
            outcomes.append(exc.reason)
        finally:
            session.close()

    threads = [threading.Thread(target=redeem, args=(f"racer-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["grant_invalid_or_expired", "ok"]
    pg_session.expire_all()
    assert pg_session.query(Identity).filter(Identity.issuer == ISSUER).count() == 1
    assert pg_session.query(User).filter(User.email == "race@example.com").count() == 1


@requires_postgres
def test_invited_email_collision_is_case_insensitive(pg_session):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    pg_session.add(User(email="Existing.Person@Example.com", name="Existing"))
    pg_session.commit()
    code = identity_link_service.create_invitation(
        pg_session,
        organization_id=org.id,
        email="existing.person@example.com",
        role=OrganizationRole.VIEWER,
        actor_user_id=admin.id,
    ).code

    with pytest.raises(GrantRedemptionError) as exc:
        identity_link_service.redeem(pg_session, claims=_claims("collider"), code=code)

    assert exc.value.reason == "invited_email_in_use"
    assert pg_session.query(Identity).filter(Identity.subject == "collider").count() == 0


@requires_postgres
@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "INVITATION"},  # missing organization, role, email
        {"kind": "ACCOUNT_LINK"},  # missing target user
        {"kind": "SOMETHING_ELSE"},
    ],
    ids=["invitation without org/role/email", "account link without target", "unknown kind"],
)
def test_check_constraints_refuse_malformed_grants(pg_session, fields):
    pg_session.add(IdentityLinkGrant(token_sha256="0" * 64, expires_at=utcnow() + timedelta(hours=1), **fields))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
