#!/usr/bin/env python
"""G3-3 multi-organization validation test fixture — ONE-OFF, NOT run on
startup, NOT part of the production runtime path.

Creates (idempotently) two ACTIVE memberships for an *already-existing*
Auth0-authenticated SIE user, plus one organization the user deliberately
has NO membership in, so G3-3's organization-switching behavior can be
exercised against a real OIDC session:

    SIE G3-3 Test Organization A        -- user's role: ORG_ADMIN
    SIE G3-3 Test Organization B        -- user's role: HSE_ANALYST
    SIE G3-3 Unauthorized Test Organization  -- no membership created

SAFETY
------
Fails closed unless SIE_CONFIRM_TEST_FIXTURE=true is set in the
environment -- deliberately a *different* flag from DEV_MODE, so this
can never be triggered by (or confused with) development/staging
configuration, and never implies DEV_MODE should be enabled.

Does NOT create a User. The target user must already exist (the Auth0
login that created it already ran) -- this script only looks one up via
its Identity row (issuer + subject, the same mapping
app/services/identity_service.py uses), and fails closed if it can't
find exactly one unambiguous match. It never grants PLATFORM_ADMIN,
never changes ROLE_PERMISSIONS, never touches DEV_MODE, and never calls
anything other than the existing organization_service/membership_service
write paths -- no raw INSERTs.

IDEMPOTENCY
-----------
Each organization is looked up by its exact name before creating one.
Each membership is looked up via membership_service.get() before
creating one; if it already exists, this script verifies the role/status
match what's expected and reports a mismatch rather than silently
overwriting it.

USAGE
-----
Run via the Render shell for the SIE backend service (this script needs
the same DATABASE_URL/environment the running app has -- it is not meant
to be run against a local/dev database):

    SIE_CONFIRM_TEST_FIXTURE=true \\
    python scripts/g3_3_test_fixture.py --subject '<auth0-subject>'

Omit --subject only if you are certain exactly one Identity row exists
for ISSUER below (e.g. exactly one real Auth0 login has ever happened on
this deployment) -- the script will refuse to guess if that's not true.

CLEANUP
-------
See this module's own `print_cleanup_instructions()` -- printed at the
end of every run, not merely on request, since this is a one-off test
fixture that should not be forgotten.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ISSUER = "https://dev-7vshxp0iirawjgso.us.auth0.com/"

ORG_A_NAME = "SIE G3-3 Test Organization A"
ORG_B_NAME = "SIE G3-3 Test Organization B"
ORG_UNAUTHORIZED_NAME = "SIE G3-3 Unauthorized Test Organization"

ORG_A_ROLE = "ORG_ADMIN"
ORG_B_ROLE = "HSE_ANALYST"


def main() -> None:
    if os.environ.get("SIE_CONFIRM_TEST_FIXTURE") != "true":
        sys.exit(
            "Refusing to provision the G3-3 test fixture: SIE_CONFIRM_TEST_FIXTURE "
            "is not set to 'true'. This is a deliberate, separate confirmation from "
            "DEV_MODE -- set it only for this one-off run, on the deployment you "
            "intend to test against, then unset it again."
        )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject",
        default=None,
        help="The Auth0 'sub' claim of the already-authenticated test user. If "
        "omitted, exactly one Identity row for ISSUER must exist, or this "
        "script refuses to guess.",
    )
    args = parser.parse_args()

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.enums import MembershipStatus
    from app.models.identity import Identity
    from app.models.organization import Organization
    from app.schemas.organization import OrganizationCreate
    from app.schemas.organization_membership import OrganizationMembershipCreate
    from app.services.membership_service import membership_service
    from app.services.organization_service import organization_service
    from app.services.permissions import OrganizationRole

    db = SessionLocal()
    try:
        # --- Resolve the target user via Identity (issuer + subject), never by
        # creating one. ---
        if args.subject:
            identity = db.execute(
                select(Identity).where(
                    Identity.issuer == ISSUER, Identity.subject == args.subject
                )
            ).scalar_one_or_none()
            if identity is None:
                sys.exit(f"No Identity found for issuer={ISSUER!r} subject={args.subject!r}.")
        else:
            matches = list(
                db.execute(select(Identity).where(Identity.issuer == ISSUER)).scalars().all()
            )
            if len(matches) != 1:
                sys.exit(
                    f"Refusing to guess: found {len(matches)} Identity row(s) for "
                    f"issuer={ISSUER!r}. Pass --subject explicitly."
                )
            identity = matches[0]

        user = identity.user
        if user is None:
            sys.exit(f"Identity {identity.id} has no linked User. Nothing to provision against.")

        print(f"Resolved SIE user: {user.id} (status={user.status})")

        # --- Idempotently ensure the three organizations exist. ---
        def get_or_create_organization(name: str) -> Organization:
            existing = db.execute(
                select(Organization).where(Organization.name == name)
            ).scalar_one_or_none()
            if existing is not None:
                print(f"Organization already exists: {existing.id} ({name!r}). Reusing.")
                return existing
            created = organization_service.create(
                db, obj_in=OrganizationCreate(name=name, status="active")
            )
            print(f"Created organization: {created.id} ({name!r}).")
            return created

        org_a = get_or_create_organization(ORG_A_NAME)
        org_b = get_or_create_organization(ORG_B_NAME)
        org_unauthorized = get_or_create_organization(ORG_UNAUTHORIZED_NAME)

        # --- Idempotently ensure the two intended memberships exist, exactly as
        # specified -- never silently overwriting a differing existing row. ---
        def get_or_create_membership(organization: Organization, role: str) -> None:
            existing = membership_service.get(db, organization_id=organization.id, user_id=user.id)
            if existing is not None:
                if existing.role == role and existing.status == MembershipStatus.ACTIVE:
                    print(
                        f"Membership already correct: user={user.id} org={organization.id} "
                        f"role={role} status=ACTIVE. Nothing to do."
                    )
                else:
                    print(
                        f"WARNING: existing membership for user={user.id} org={organization.id} "
                        f"has role={existing.role!r} status={existing.status.value!r}, "
                        f"expected role={role!r} status=ACTIVE. NOT modified -- resolve manually."
                    )
                return
            membership_service.create(
                db,
                organization_id=organization.id,
                obj_in=OrganizationMembershipCreate(
                    user_id=user.id,
                    role=OrganizationRole(role),
                    status=MembershipStatus.ACTIVE,
                ),
            )
            print(f"Created membership: user={user.id} org={organization.id} role={role} status=ACTIVE.")

        get_or_create_membership(org_a, ORG_A_ROLE)
        get_or_create_membership(org_b, ORG_B_ROLE)

        # --- Deliberately NOT creating a membership in org_unauthorized. ---
        unauthorized_existing = membership_service.get(
            db, organization_id=org_unauthorized.id, user_id=user.id
        )
        if unauthorized_existing is not None:
            print(
                f"WARNING: user {user.id} unexpectedly already has a membership in the "
                f"unauthorized test organization ({org_unauthorized.id}). This breaks the "
                "negative-authorization test -- resolve manually before testing."
            )
        else:
            print(f"Confirmed: no membership exists for user={user.id} in unauthorized org "
                  f"{org_unauthorized.id} (expected).")

        print()
        print("Fixture summary")
        print("---------------")
        print(f"SIE user:                {user.id}")
        print(f"Organization A ({ORG_A_ROLE}):  {org_a.id}")
        print(f"Organization B ({ORG_B_ROLE}): {org_b.id}")
        print(f"Unauthorized organization:     {org_unauthorized.id}")

    finally:
        db.close()

    print_cleanup_instructions()


def print_cleanup_instructions() -> None:
    print()
    print("Cleanup (run only when this fixture is no longer needed)")
    print("----------------------------------------------------------")
    print("Safe order (respects FK constraints -- memberships reference both")
    print("organizations and the user; organizations cascade-delete their own")
    print("memberships, sites, data sources, etc., so deleting the three test")
    print("organizations by id is sufficient and does NOT touch the User row):")
    print()
    print("  DELETE FROM organizations WHERE name IN (")
    print(f"    '{ORG_A_NAME}',")
    print(f"    '{ORG_B_NAME}',")
    print(f"    '{ORG_UNAUTHORIZED_NAME}'")
    print("  );")
    print()
    print("This relies on Organization.memberships having cascade='all, delete-orphan'")
    print("(app/models/organization.py) -- deleting the organization deletes its")
    print("membership rows with it. The User and its Identity are never touched by")
    print("this cleanup, intentionally.")


if __name__ == "__main__":
    main()
