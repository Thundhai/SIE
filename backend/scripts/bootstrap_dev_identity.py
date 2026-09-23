#!/usr/bin/env python
"""Create the minimal SIE development identity for a DEV_MODE deployment.

This script intentionally does NOT seed events, intelligence data, or risk
assessments. It only creates the fixed development organization, site, user,
and ORG_ADMIN membership required for the frontend development identity.

SAFETY
------
Fails closed unless DEV_MODE=true. It is intended for an explicitly
development/staging deployment such as the Render SIE environment used to
connect the Vercel frontend.

IDEMPOTENCY
-----------
If the fixed development organization already exists, the script exits
without modifying anything.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


DEV_ORGANIZATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000d01")
DEV_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000d02")
DEV_SITE_ID = uuid.UUID("00000000-0000-4000-8000-000000000d03")

DEV_ORGANIZATION_NAME = "SIE Local Development Organization"
DEV_USER_NAME = "Development User"
DEV_USER_EMAIL = "dev-user@example.invalid"
DEV_SITE_NAME = "Demo Site (Local Development)"


def main() -> None:
    if not settings.DEV_MODE:
        sys.exit(
            "Refusing to bootstrap: DEV_MODE is not enabled. "
            "Set DEV_MODE=true on this development/staging deployment first."
        )

    from app.core.database import SessionLocal
    from app.models.organization import Organization
    from app.models.organization_membership import OrganizationMembership
    from app.models.site import Site
    from app.models.user import User
    from app.schemas.organization_membership import OrganizationMembershipCreate
    from app.services.membership_service import membership_service
    from app.services.permissions import OrganizationRole

    db = SessionLocal()
    try:
        existing = db.get(Organization, DEV_ORGANIZATION_ID)
        if existing is not None:
            print(
                f"Development organization already exists: "
                f"{DEV_ORGANIZATION_ID} ({existing.name!r}). Nothing changed."
            )
            return

        print(f"Creating development organization {DEV_ORGANIZATION_ID} ...")
        org = Organization(
            id=DEV_ORGANIZATION_ID,
            name=DEV_ORGANIZATION_NAME,
            status="active",
        )
        db.add(org)

        print(f"Creating development site {DEV_SITE_ID} ...")
        site = Site(
            id=DEV_SITE_ID,
            organization_id=DEV_ORGANIZATION_ID,
            name=DEV_SITE_NAME,
            status="active",
        )
        db.add(site)

        print(f"Creating development user {DEV_USER_ID} ...")
        user = User(
            id=DEV_USER_ID,
            name=DEV_USER_NAME,
            email=DEV_USER_EMAIL,
            organization_id=DEV_ORGANIZATION_ID,
        )
        db.add(user)

        db.commit()

        membership_service.create(
            db,
            organization_id=DEV_ORGANIZATION_ID,
            obj_in=OrganizationMembershipCreate(
                user_id=DEV_USER_ID,
                role=OrganizationRole.ORG_ADMIN,
            ),
        )

        # Verify the membership exists before reporting success.
        membership = db.execute(
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == DEV_ORGANIZATION_ID,
                OrganizationMembership.user_id == DEV_USER_ID,
            )
        ).scalar_one_or_none()

        if membership is None:
            raise RuntimeError("Development membership was not created.")

        print("Created ORG_ADMIN development membership.")
        print()
        print("Bootstrap complete.")
        print(f"VITE_DEV_ORGANIZATION_ID={DEV_ORGANIZATION_ID}")
        print(f"VITE_DEV_USER_ID={DEV_USER_ID}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
