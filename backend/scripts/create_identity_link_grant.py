#!/usr/bin/env python
"""Issue an ACCOUNT_LINK code for one existing SIE user. Operator-only,
never run on startup.

Use it to bind an existing account to its identity-provider sign-in:
migrating an account that has no (issuer, subject) identity yet,
recovering an orphaned identity, or linking a platform administrator,
which the API refuses to do. The person signs in with the identity
provider, then redeems the code (`POST /api/v1/auth/identity-links/redeem`).

SAFETY
------
* Fails closed unless SIE_CONFIRM_IDENTITY_LINK_GRANT=true is set.
* Names the user by id only, never by email.
* A platform-administrator target needs --allow-platform-admin as well.
* Prints the one-time code once, to this terminal. Only its hash is
  stored, and the issuance is audited (IDENTITY_LINK_GRANT_CREATED). Hand
  the code over through a trusted channel. It expires after
  IDENTITY_LINK_GRANT_TTL_HOURS.

USAGE (Render shell for the SIE backend)
-----
    SIE_CONFIRM_IDENTITY_LINK_GRANT=true \\
    python scripts/create_identity_link_grant.py --user-id <uuid> [--allow-platform-admin]
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue a one-time account-link code for an existing user.")
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--allow-platform-admin", action="store_true")
    args = parser.parse_args(argv)

    if os.environ.get("SIE_CONFIRM_IDENTITY_LINK_GRANT") != "true":
        print("Refusing to run: set SIE_CONFIRM_IDENTITY_LINK_GRANT=true to confirm.", file=sys.stderr)
        return 2

    from app.core.database import SessionLocal
    from app.services.identity_link_service import GrantCreationError, identity_link_service

    db = SessionLocal()
    try:
        created = identity_link_service.create_account_link(
            db,
            target_user_id=args.user_id,
            actor_user_id=None,
            allow_platform_admin=args.allow_platform_admin,
        )
        # Read while the session is open: the commit expired the grant.
        grant_id, expires_at = created.grant.id, created.grant.expires_at
    except GrantCreationError as exc:
        print(f"Refused: {exc.message}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"grant_id:   {grant_id}")
    print(f"expires_at: {expires_at.isoformat()}")
    print(f"code:       {created.code}")
    print("Shown once. Hand it over through a trusted channel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
