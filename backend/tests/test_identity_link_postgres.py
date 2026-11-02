"""Identity links and invitations on real PostgreSQL: the row locks and
unique indexes that keep codes single-use and accounts unique under
concurrency, and the table's CHECK constraints. Skipped without a
reachable PostgreSQL (tests/postgres_support.py)."""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import utcnow
from app.models.identity import Identity
from app.models.identity_link_grant import IdentityLinkGrant
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services.identity_link_service import GrantRedemptionError, identity_link_service
from app.services.identity_service import ExternalIdentityClaims
from app.services.invitation_service import InvitationError, invitation_service
from app.services.permissions import OrganizationRole, Permission
from app.services.verified_email import VerifiedEmail
from tests.intelligence_test_helpers import make_org, make_org_member
from tests.postgres_support import requires_postgres

ISSUER = "https://pg-issuer.example.com"
ALL = frozenset(Permission)


@pytest.fixture
def trusted_issuer(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_EMAIL_LINKING_TRUSTED_ISSUERS", ISSUER)


def _claims(subject: str) -> ExternalIdentityClaims:
    return ExternalIdentityClaims(subject=subject, issuer=ISSUER, email=None, display_name=None, provider="test")


def _verified(email: str) -> VerifiedEmail:
    return VerifiedEmail(email=email, email_verified=True, source="access_token")


def _invite(session, org, admin, email: str, role=OrganizationRole.VIEWER) -> str:
    return invitation_service.create(
        session, organization_id=org.id, email=email, role=role, actor_user_id=admin.id, actor_permissions=ALL
    ).code


def _race(pg_session, calls):
    """Run each callable on its own session and thread, released together.
    Each returns "ok" or the refusal reason."""
    factory = sessionmaker(bind=pg_session.get_bind())
    barrier = threading.Barrier(len(calls))
    outcomes: list[str] = []

    def run(call) -> None:
        session = factory()
        try:
            barrier.wait()
            call(session)
            outcomes.append("ok")
        except (GrantRedemptionError, InvitationError) as exc:
            outcomes.append(exc.reason)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(c,)) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    pg_session.expire_all()
    return sorted(outcomes)


def _slow(monkeypatch, module, name: str, seconds: float = 0.4) -> None:
    """Pause right after a check returns, so a concurrent request reaches
    the same check before this one writes."""
    original = getattr(module, name)

    def slowed(*args, **kwargs):
        result = original(*args, **kwargs)
        time.sleep(seconds)
        return result

    monkeypatch.setattr(module, name, slowed)


# --- Invitations ---------------------------------------------------------------------------


@requires_postgres
def test_concurrent_acceptances_of_one_invitation_admit_exactly_one(pg_session, trusted_issuer):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    code = _invite(pg_session, org, admin, "race@example.com")

    def accept(subject):
        return lambda s: invitation_service.accept(
            s, claims=_claims(subject), verified=_verified("race@example.com"), code=code
        )

    outcomes = _race(pg_session, [accept("racer-a"), accept("racer-b")])

    assert outcomes == ["invitation_already_used", "ok"]
    assert pg_session.query(Identity).filter(Identity.issuer == ISSUER).count() == 1
    assert pg_session.query(User).filter(User.email == "race@example.com").count() == 1


@requires_postgres
def test_two_organizations_inviting_one_new_person_at_once_create_one_account(pg_session, trusted_issuer, monkeypatch):
    """Two invitations (different organizations, same email) accepted at
    the same moment by two different sign-ins: the unique email stops the
    second account."""
    import app.services.invitation_service as module

    org_a, org_b = make_org(pg_session, "A"), make_org(pg_session, "B")
    admin_a, admin_b = make_org_member(pg_session, org_a.id), make_org_member(pg_session, org_b.id)
    code_a = _invite(pg_session, org_a, admin_a, "Person@Example.com")
    code_b = _invite(pg_session, org_b, admin_b, "person@example.com")
    _slow(monkeypatch, module, "_email_taken")

    outcomes = _race(
        pg_session,
        [
            lambda s: invitation_service.accept(
                s, claims=_claims("idp-a"), verified=_verified("person@example.com"), code=code_a
            ),
            lambda s: invitation_service.accept(
                s, claims=_claims("idp-b"), verified=_verified("person@example.com"), code=code_b
            ),
        ],
    )

    assert outcomes[1] == "ok"
    assert outcomes[0] in ("concurrent_conflict", "existing_account_sign_in_required")
    assert pg_session.query(User).filter(User.email == "person@example.com").count() == 1


@requires_postgres
def test_concurrent_invitations_for_one_email_leave_one_open(pg_session):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)

    outcomes = _race(
        pg_session,
        [lambda s, e=e: _invite(s, org, admin, e) for e in ("Dup@Example.com", "dup@example.com")],
    )

    assert outcomes == ["ok", "open_invitation_exists"]
    assert pg_session.query(IdentityLinkGrant).filter(IdentityLinkGrant.organization_id == org.id).count() == 1


@requires_postgres
def test_existing_mixed_case_account_blocks_a_new_identity(pg_session, trusted_issuer):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    pg_session.add(User(email="Existing.Person@Example.com", name="Existing"))
    pg_session.commit()
    code = _invite(pg_session, org, admin, "existing.person@example.com")

    with pytest.raises(InvitationError) as exc:
        invitation_service.accept(
            pg_session, claims=_claims("collider"), verified=_verified("existing.person@example.com"), code=code
        )

    assert exc.value.reason == "existing_account_sign_in_required"
    assert pg_session.query(Identity).filter(Identity.subject == "collider").count() == 0


@requires_postgres
def test_accepted_invitation_creates_an_active_membership(pg_session, trusted_issuer):
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    code = _invite(pg_session, org, admin, "joiner@example.com", role=OrganizationRole.HSE_ANALYST)

    accepted = invitation_service.accept(
        pg_session, claims=_claims("joiner"), verified=_verified("joiner@example.com"), code=code
    )

    membership = (
        pg_session.query(OrganizationMembership).filter_by(user_id=accepted.user.id, organization_id=org.id).one()
    )
    assert (membership.role, membership.status.value) == ("HSE_ANALYST", "ACTIVE")


# --- Account links -----------------------------------------------------------------------


@requires_postgres
def test_concurrent_account_links_never_give_one_user_two_identities_per_issuer(pg_session, monkeypatch):
    import app.services.identity_link_service as module

    org = make_org(pg_session)
    target = make_org_member(pg_session, org.id)
    codes = [
        identity_link_service.create_account_link(pg_session, target_user_id=target.id, actor_user_id=None).code
        for _ in range(2)
    ]
    _slow(monkeypatch, module, "user_has_identity_for_issuer")

    outcomes = _race(
        pg_session,
        [
            lambda s, c=c, sub=sub: identity_link_service.redeem(s, claims=_claims(sub), code=c)
            for c, sub in ((codes[0], "subject-a"), (codes[1], "subject-b"))
        ],
    )

    assert outcomes == ["ok", "target_already_bound_for_issuer"]
    assert pg_session.query(Identity).filter(Identity.user_id == target.id, Identity.issuer == ISSUER).count() == 1


@requires_postgres
def test_concurrent_redemptions_of_one_account_link_bind_exactly_one_identity(pg_session):
    org = make_org(pg_session)
    target = make_org_member(pg_session, org.id)
    code = identity_link_service.create_account_link(pg_session, target_user_id=target.id, actor_user_id=None).code

    outcomes = _race(
        pg_session,
        [lambda s, sub=sub: identity_link_service.redeem(s, claims=_claims(sub), code=code) for sub in ("x", "y")],
    )

    assert outcomes == ["grant_invalid_or_expired", "ok"]
    assert pg_session.query(Identity).filter(Identity.user_id == target.id).count() == 1


# --- Constraints ---------------------------------------------------------------------------


@requires_postgres
@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "INVITATION"},  # missing organization, role, email
        {"kind": "ACCOUNT_LINK"},  # missing target user
        {"kind": "SOMETHING_ELSE"},
        {"kind": "ACCOUNT_LINK", "status": "BOGUS"},
    ],
    ids=["invitation without org/role/email", "account link without target", "unknown kind", "unknown status"],
)
def test_check_constraints_refuse_malformed_grants(pg_session, fields):
    if fields.get("kind") == "ACCOUNT_LINK" and "status" in fields:
        org = make_org(pg_session)
        fields = {**fields, "target_user_id": make_org_member(pg_session, org.id).id}
    pg_session.add(IdentityLinkGrant(token_sha256="0" * 64, expires_at=utcnow() + timedelta(hours=1), **fields))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


@requires_postgres
@pytest.mark.parametrize("interleaved", ["resend", "accepted"])
def test_refusal_side_effects_never_overwrite_a_concurrent_change(pg_session, trusted_issuer, monkeypatch, interleaved):
    """A refused acceptance rolls back (releasing the row lock) before it
    records its side effect (here: the mismatch that would auto-revoke).
    If a resend or an acceptance lands in that gap, the side effect must
    not apply to the changed invitation."""
    from sqlalchemy import event

    from app.models.identity_link_grant import IdentityLinkGrant as Grant

    monkeypatch.setattr(settings, "INVITATION_MAX_FAILED_ATTEMPTS", 1)
    org = make_org(pg_session)
    admin = make_org_member(pg_session, org.id)
    code = _invite(pg_session, org, admin, "target@example.com")
    grant_id = pg_session.query(Grant).filter(Grant.organization_id == org.id).one().id
    factory = sessionmaker(bind=pg_session.get_bind())
    session = factory()
    fired = {"done": False}

    def concurrent_change(sess):
        if fired["done"]:
            return
        fired["done"] = True
        other = factory()
        try:
            if interleaved == "resend":
                invitation_service.resend(other, organization_id=org.id, invitation_id=grant_id, actor_user_id=admin.id)
            else:
                g = other.get(Grant, grant_id)
                g.status, g.redeemed_at = "ACCEPTED", utcnow()
                other.commit()
        finally:
            other.close()

    event.listen(session, "after_rollback", concurrent_change)
    try:
        with pytest.raises(InvitationError) as exc:
            invitation_service.accept(
                session, claims=_claims("mismatch"), verified=_verified("someone.else@example.com"), code=code
            )
    finally:
        session.close()

    assert exc.value.reason == "email_mismatch"
    pg_session.expire_all()
    grant = pg_session.get(Grant, grant_id)
    if interleaved == "resend":
        assert (grant.status, grant.failed_attempts, grant.issue_count) == ("PENDING", 0, 2)
    else:
        assert grant.status == "ACCEPTED"


@requires_postgres
def test_a_maximum_length_email_and_long_name_claim_are_accepted(pg_session, trusted_issuer):
    """Real column limits: a 320-character invited email (User.name falls
    back to it, 255 max) and a 400-character `name` claim (Identity.
    display_name, 255 max) must not overflow into a database error."""
    org = make_org(pg_session, "Long Names Org")
    admin = make_org_member(pg_session, org.id, role=OrganizationRole.ORG_ADMIN)
    email = ("a" * 64) + "@" + ("b" * 251) + ".com"
    assert len(email) == 320
    code = _invite(pg_session, org, admin, email)
    claims = ExternalIdentityClaims(
        subject="long-name-sub", issuer=ISSUER, email=None, display_name="N" * 400, provider="test"
    )

    accepted = invitation_service.accept(pg_session, claims=claims, verified=_verified(email), code=code)

    pg_session.refresh(accepted.user)
    assert accepted.user.email == email
    assert len(accepted.user.name) == 255
    identity = pg_session.query(Identity).filter(Identity.subject == "long-name-sub").one()
    assert len(identity.display_name) == 255


@requires_postgres
def test_an_over_long_name_claim_never_breaks_later_sign_ins_or_account_links(pg_session, trusted_issuer):
    """Every write of a token's profile claims fits the real columns: the
    next sign-in's profile sync and an account-link redemption included,
    not just acceptance."""
    from app.services.identity_service import identity_resolver_service

    org = make_org(pg_session, "Sync Org")
    admin = make_org_member(pg_session, org.id, role=OrganizationRole.ORG_ADMIN)
    code = _invite(pg_session, org, admin, "long.name@example.com")
    long_claims = ExternalIdentityClaims(
        subject="sync-sub", issuer=ISSUER, email="x" * 400, display_name="N" * 400, provider="test"
    )
    accepted = invitation_service.accept(
        pg_session, claims=long_claims, verified=_verified("long.name@example.com"), code=code
    )

    # The next authenticated request syncs the profile from the same claims.
    user = identity_resolver_service.resolve_user(pg_session, claims=long_claims)

    assert user.id == accepted.user.id
    identity = pg_session.query(Identity).filter(Identity.subject == "sync-sub").one()
    pg_session.refresh(identity)
    assert len(identity.display_name) == 255
    assert identity.email is None  # longer than any valid address: dropped, not cut

    # An account-link redemption writes the same fields.
    target = make_org_member(pg_session, org.id)
    link = identity_link_service.create_account_link(
        pg_session, target_user_id=target.id, actor_user_id=admin.id, allow_platform_admin=False
    )
    link_claims = ExternalIdentityClaims(
        subject="link-sub", issuer=ISSUER, email=None, display_name="L" * 400, provider="test"
    )
    linked_user, _ = identity_link_service.redeem(pg_session, claims=link_claims, code=link.code)
    assert linked_user.id == target.id
    linked = pg_session.query(Identity).filter(Identity.subject == "link-sub").one()
    assert len(linked.display_name) == 255


@requires_postgres
def test_a_refusal_for_a_nonexistent_organization_is_audited_without_breaking(pg_session):
    """A platform administrator can name any organization UUID. Auditing the
    refusal must not reference an organization that doesn't exist: the
    audit_logs foreign key would turn the expected 404 into a 500."""
    import uuid as _uuid

    from app.api.v1.invitations import _admin_refused
    from app.models.audit_log import AuditLog

    missing_org = _uuid.uuid4()
    error = _admin_refused(
        pg_session,
        InvitationError("invitation_not_found", 404, "Invitation not found."),
        operation="resend",
        organization_id=missing_org,
        actor_user_id=None,
        invitation_id=_uuid.uuid4(),
    )

    assert error.status_code == 404
    row = pg_session.query(AuditLog).filter(AuditLog.action == "INVITATION_REJECTED").order_by(AuditLog.timestamp.desc()).first()
    assert row is not None and row.organization_id is None
    assert row.event_metadata == {"reason": "invitation_not_found", "operation": "resend"}
