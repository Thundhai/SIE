"""Identity resolution: verified claims -> SIE user.

(issuer, subject) is the only identity key. An unknown identity is
refused, never auto-provisioned or matched by email, unless
verified-email linking is explicitly enabled for that exact issuer, and
even then only under every safeguard in
`IdentityResolverService._link_by_verified_email`.
"""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.identity import Identity
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.audit_service import AuditAction
from app.services.identity_service import (
    DevTokenVerifier,
    ExternalIdentityClaims,
    IdentityLinkRejectedError,
    LinkRejection,
    identity_resolver_service,
)
from app.services.permissions import PLATFORM_ADMIN
from app.services.user_service import user_service

ISSUER = "https://dev.issuer"


def _claims(subject="sub-1", *, issuer=ISSUER, email="person@example.com", email_verified=None):
    return ExternalIdentityClaims(
        subject=subject,
        issuer=issuer,
        email=email,
        display_name="Person",
        provider="test",
        email_verified=email_verified,
    )


def _bind(db_session, user, *, subject, issuer=ISSUER):
    identity = Identity(user_id=user.id, subject=subject, issuer=issuer, provider="test")
    db_session.add(identity)
    db_session.commit()
    return identity


def _user(db_session, email):
    return user_service.create(db_session, obj_in=UserCreate(email=email, name="Existing"))


def _rejections(db_session):
    return (
        db_session.execute(select(AuditLog).where(AuditLog.action == AuditAction.IDENTITY_LINK_REJECTED))
        .scalars()
        .all()
    )


@pytest.fixture
def email_linking(monkeypatch):
    """Turn verified-email linking on for ISSUER only."""
    monkeypatch.setattr(settings, "OIDC_TRUST_VERIFIED_EMAIL_FOR_LINKING", True)
    monkeypatch.setattr(settings, "OIDC_EMAIL_LINKING_TRUSTED_ISSUERS", ISSUER)


def test_dev_token_verifier_parses_claims():
    claims = DevTokenVerifier().verify("user-123|https://dev.issuer|person@example.com|Person Name")

    assert claims.subject == "user-123"
    assert claims.issuer == "https://dev.issuer"
    assert claims.email == "person@example.com"
    assert claims.display_name == "Person Name"
    assert claims.provider == "dev"
    assert claims.email_verified is None


def test_settings_default_to_no_email_linking():
    assert settings.OIDC_TRUST_VERIFIED_EMAIL_FOR_LINKING is False
    assert settings.oidc_email_linking_trusted_issuers == frozenset()


# --- (issuer, subject) is authoritative -----------------------------------------------


def test_existing_identity_resolves_to_its_user(db_session):
    user = _user(db_session, "bound@example.com")
    _bind(db_session, user, subject="sub-bound")

    resolved = identity_resolver_service.resolve_user(
        db_session, claims=_claims("sub-bound", email="other@example.com")
    )

    assert resolved.id == user.id


def test_resolving_same_identity_twice_returns_the_same_user_and_one_row(db_session):
    user = _user(db_session, "repeat@example.com")
    _bind(db_session, user, subject="sub-3")

    first = identity_resolver_service.resolve_user(db_session, claims=_claims("sub-3"))
    second = identity_resolver_service.resolve_user(db_session, claims=_claims("sub-3"))

    assert first.id == second.id == user.id
    rows = db_session.query(Identity).filter(Identity.issuer == ISSUER, Identity.subject == "sub-3").all()
    assert len(rows) == 1


def test_same_subject_under_another_issuer_is_a_different_identity(db_session):
    user = _user(db_session, "a@example.com")
    _bind(db_session, user, subject="shared", issuer="https://issuer-a")

    with pytest.raises(IdentityLinkRejectedError):
        identity_resolver_service.resolve_user(db_session, claims=_claims("shared", issuer="https://issuer-b"))


# --- Unknown identities are refused by default -----------------------------------------


def test_unknown_identity_is_rejected_and_nothing_is_created(db_session):
    users_before = db_session.query(User).count()

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(db_session, claims=_claims("brand-new", email="new@example.com"))

    assert exc.value.reason == LinkRejection.NO_GRANT
    assert db_session.query(User).count() == users_before
    assert db_session.query(Identity).filter(Identity.subject == "brand-new").count() == 0


def test_verified_email_is_not_linked_while_the_policy_is_disabled(db_session):
    existing = _user(db_session, "victim@example.com")

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("attacker", email="victim@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.NO_GRANT
    assert db_session.query(Identity).filter(Identity.user_id == existing.id).count() == 0


def test_flag_alone_trusts_no_issuer(db_session, monkeypatch):
    monkeypatch.setattr(settings, "OIDC_TRUST_VERIFIED_EMAIL_FOR_LINKING", True)
    _user(db_session, "victim@example.com")

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("x", email="victim@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.ISSUER_NOT_TRUSTED


def test_orphaned_identity_is_not_reattached_by_email(db_session, email_linking):
    _user(db_session, "orphan.owner@example.com")
    db_session.add(Identity(user_id=None, subject="orphan", issuer=ISSUER, provider="test"))
    db_session.commit()

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("orphan", email="orphan.owner@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.ORPHANED_IDENTITY


# --- Verified-email linking, when explicitly enabled -----------------------------------


@pytest.mark.parametrize(
    ("claims_kwargs", "reason"),
    [
        ({"email_verified": None}, LinkRejection.EMAIL_VERIFIED_MISSING),
        ({"email_verified": False}, LinkRejection.EMAIL_NOT_VERIFIED),
        ({"email": None, "email_verified": True}, LinkRejection.EMAIL_MISSING),
        ({"issuer": "https://untrusted.issuer", "email_verified": True}, LinkRejection.ISSUER_NOT_TRUSTED),
    ],
    ids=["email_verified missing", "email_verified false", "no email", "untrusted issuer"],
)
def test_email_linking_refuses_unless_every_condition_holds(db_session, email_linking, claims_kwargs, reason):
    existing = _user(db_session, "person@example.com")
    kwargs = {"email": "person@example.com", **claims_kwargs}

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(db_session, claims=_claims("new-sub", **kwargs))

    assert exc.value.reason == reason
    assert db_session.query(Identity).filter(Identity.user_id == existing.id).count() == 0


def test_email_verified_string_true_does_not_count_as_verified():
    """The verifier keeps only a JSON boolean; anything else becomes None."""
    from tests.oidc_test_helpers import make_test_token, make_test_verifier

    claims = make_test_verifier().verify(make_test_token(extra_claims={"email": "a@b.co", "email_verified": "true"}))
    assert claims.email_verified is None
    claims = make_test_verifier().verify(make_test_token(extra_claims={"email": "a@b.co", "email_verified": True}))
    assert claims.email_verified is True


def test_platform_administrator_is_never_linked_by_email(db_session, email_linking):
    admin = _user(db_session, "admin@example.com")
    user_service.set_platform_role(db_session, user=admin, platform_role=PLATFORM_ADMIN)

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("new-sub", email="admin@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.TARGET_PLATFORM_ADMIN
    assert db_session.query(Identity).filter(Identity.user_id == admin.id).count() == 0


def test_account_already_bound_for_the_issuer_is_not_given_a_second_subject(db_session, email_linking):
    owner = _user(db_session, "owner@example.com")
    _bind(db_session, owner, subject="owner-sub")

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("other-sub", email="owner@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.TARGET_ALREADY_BOUND


def test_inactive_user_is_not_linked_by_email(db_session, email_linking):
    user = _user(db_session, "gone@example.com")
    user.status = "inactive"
    db_session.commit()

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("new-sub", email="gone@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.TARGET_INACTIVE


def test_verified_email_from_trusted_issuer_links_and_is_audited(db_session, email_linking):
    existing = _user(db_session, "Person@Example.com")

    user = identity_resolver_service.resolve_user(
        db_session, claims=_claims("new-sub", email="person@example.com", email_verified=True)
    )

    assert user.id == existing.id
    identity = db_session.query(Identity).filter(Identity.issuer == ISSUER, Identity.subject == "new-sub").one()
    assert identity.user_id == existing.id
    linked = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.IDENTITY_LINKED).one()
    assert linked.event_metadata["method"] == "verified_email"


def test_rejections_are_audited_without_token_email_or_subject(db_session):
    with pytest.raises(IdentityLinkRejectedError):
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("secret-subject-value", email="private@example.com")
        )

    (row,) = _rejections(db_session)
    assert row.event_metadata["reason"] == LinkRejection.NO_GRANT
    assert row.event_metadata["issuer"] == ISSUER
    flat = repr(row.event_metadata)
    assert "secret-subject-value" not in flat
    assert "private@example.com" not in flat
    assert len(row.event_metadata["subject_fingerprint"]) == 16


# --- Concurrency (Copilot review on #69) ------------------------------------------------


def _first_lookup_misses(monkeypatch, *, misses: int = 1):
    """Make the first `misses` identity lookups return None, as if a
    concurrent request bound the identity right after them."""
    real = identity_resolver_service._get_identity
    calls = {"n": 0}

    def lookup(db, *, issuer, subject):
        calls["n"] += 1
        return None if calls["n"] <= misses else real(db, issuer=issuer, subject=subject)

    monkeypatch.setattr(identity_resolver_service, "_get_identity", lookup)


def test_identity_bound_while_waiting_for_the_lock_signs_in_instead_of_403(db_session, email_linking, monkeypatch):
    user = _user(db_session, "person@example.com")
    _bind(db_session, user, subject="racing-sub")
    _first_lookup_misses(monkeypatch, misses=1)

    resolved = identity_resolver_service.resolve_user(
        db_session, claims=_claims("racing-sub", email="person@example.com", email_verified=True)
    )

    assert resolved.id == user.id
    assert db_session.query(Identity).filter(Identity.subject == "racing-sub").count() == 1
    assert _rejections(db_session) == []


def test_unique_conflict_while_linking_resolves_the_now_bound_identity(db_session, email_linking, monkeypatch):
    """A grant redemption bound this (issuer, subject) to another user while
    the email link was in flight: the insert conflicts, and the caller
    signs in as the identity's actual user rather than getting a 500."""
    email_owner = _user(db_session, "person@example.com")
    grant_target = _user(db_session, "someone.else@example.com")
    _bind(db_session, grant_target, subject="contested-sub")
    _first_lookup_misses(monkeypatch, misses=2)

    resolved = identity_resolver_service.resolve_user(
        db_session, claims=_claims("contested-sub", email="person@example.com", email_verified=True)
    )

    assert resolved.id == grant_target.id
    assert db_session.query(Identity).filter(Identity.user_id == email_owner.id).count() == 0


def test_unique_conflict_with_nothing_bound_afterwards_is_an_audited_refusal(db_session, email_linking, monkeypatch):
    _user(db_session, "person@example.com")
    monkeypatch.setattr(identity_resolver_service, "_get_identity", lambda db, *, issuer, subject: None)

    def conflict(db, *, claims, user):
        from sqlalchemy.exc import IntegrityError

        raise IntegrityError("INSERT", {}, Exception("uq_identities_issuer_subject"))

    monkeypatch.setattr(identity_resolver_service, "_bind_verified_email", conflict)

    with pytest.raises(IdentityLinkRejectedError) as exc:
        identity_resolver_service.resolve_user(
            db_session, claims=_claims("new-sub", email="person@example.com", email_verified=True)
        )

    assert exc.value.reason == LinkRejection.CONCURRENT_CONFLICT
    (row,) = _rejections(db_session)
    assert row.event_metadata["reason"] == "concurrent_conflict"
