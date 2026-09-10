"""Identity resolution: External Identity -> Identity Resolver -> SIE User.

No OIDC token verification is implemented (by design — see
app/services/identity_service.py); these tests exercise the resolver
against already-"verified" claims, using `DevTokenVerifier` only to
produce that claims object, exactly as a real verifier would.
"""

from app.models.identity import Identity
from app.schemas.user import UserCreate
from app.services.identity_service import DevTokenVerifier, identity_resolver_service
from app.services.user_service import user_service


def test_dev_token_verifier_parses_claims():
    verifier = DevTokenVerifier()

    claims = verifier.verify("user-123|https://dev.issuer|person@example.com|Person Name")

    assert claims.subject == "user-123"
    assert claims.issuer == "https://dev.issuer"
    assert claims.email == "person@example.com"
    assert claims.display_name == "Person Name"
    assert claims.provider == "dev"


def test_resolve_or_create_creates_new_user(db_session):
    verifier = DevTokenVerifier()
    claims = verifier.verify("sub-1|https://dev.issuer|new.person@example.com|New Person")

    user = identity_resolver_service.resolve_or_create_user(db_session, claims=claims)

    assert user.email == "new.person@example.com"
    assert user.name == "New Person"
    stored = user_service.get_by_email(db_session, email="new.person@example.com")
    assert stored is not None
    assert stored.id == user.id


def test_resolve_or_create_links_existing_user_by_email(db_session):
    existing = user_service.create(
        db_session, obj_in=UserCreate(email="already.here@example.com", name="Already Here")
    )
    verifier = DevTokenVerifier()
    claims = verifier.verify("sub-2|https://dev.issuer|already.here@example.com|Different Name")

    user = identity_resolver_service.resolve_or_create_user(db_session, claims=claims)

    # Linked to the pre-existing User row, not a new one.
    assert user.id == existing.id


def test_resolving_same_identity_twice_returns_the_same_user(db_session):
    verifier = DevTokenVerifier()
    claims = verifier.verify("sub-3|https://dev.issuer|repeat@example.com|Repeat User")

    first = identity_resolver_service.resolve_or_create_user(db_session, claims=claims)
    second = identity_resolver_service.resolve_or_create_user(db_session, claims=claims)

    assert first.id == second.id
    # And exactly one Identity row was created, not two.
    identities = (
        db_session.query(Identity)
        .filter(Identity.issuer == "https://dev.issuer", Identity.subject == "sub-3")
        .all()
    )
    assert len(identities) == 1


def test_different_issuers_with_the_same_subject_are_different_identities(db_session):
    """The OIDC identity key is (issuer, subject), not subject alone."""
    verifier = DevTokenVerifier()
    claims_a = verifier.verify("shared-subject|https://issuer-a|a@example.com|A")
    claims_b = verifier.verify("shared-subject|https://issuer-b|b@example.com|B")

    user_a = identity_resolver_service.resolve_or_create_user(db_session, claims=claims_a)
    user_b = identity_resolver_service.resolve_or_create_user(db_session, claims=claims_b)

    assert user_a.id != user_b.id


def test_resolve_without_email_claim_still_provisions_a_user(db_session):
    verifier = DevTokenVerifier()
    claims = verifier.verify("sub-no-email|https://dev.issuer")

    user = identity_resolver_service.resolve_or_create_user(db_session, claims=claims)

    assert user is not None
    assert user.email  # some stable placeholder was assigned, not empty/None
