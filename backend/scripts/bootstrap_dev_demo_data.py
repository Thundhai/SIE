#!/usr/bin/env python
"""Populate the existing SIE DEV_MODE identity with deterministic demo intelligence data.

This is deliberately separate from bootstrap_dev_identity.py:
- identity bootstrap creates organization/site/user/membership;
- this script creates demo safety events and one baseline risk assessment.

SAFETY
------
Fails closed unless DEV_MODE=true AND SIE_DEV_DEMO_DATA=true. It is intended
only for the explicitly enabled Render development/staging deployment.

IDEMPOTENCY
-----------
If the development organization has no events, the script reuses the existing
development seed pipeline to ingest its deterministic enterprise scenario.
If events already exist, event ingestion is skipped.

If no risk assessment exists for the development organization, the script
creates the existing deterministic baseline assessment through the real API
path used by the development seed. If an assessment already exists, it is
left untouched.

No frontend fixtures or hard-coded intelligence values are created here.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

DEV_ORGANIZATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000d01")


def main() -> None:
    if not settings.DEV_MODE:
        sys.exit(
            "Refusing to seed demo data: DEV_MODE is not enabled. "
            "Set DEV_MODE=true on the development/staging deployment first."
        )

    if not settings.SIE_DEV_DEMO_DATA:
        sys.exit(
            "Refusing to seed demo data: SIE_DEV_DEMO_DATA is not enabled. "
            "Set SIE_DEV_DEMO_DATA=true only on the intended development/staging deployment."
        )

    from app.core.database import SessionLocal
    from app.models.risk_assessment import RiskAssessment
    from app.models.safety_event import SafetyEvent

    db = SessionLocal()
    try:
        event_count = db.execute(
            select(func.count())
            .select_from(SafetyEvent)
            .where(SafetyEvent.organization_id == DEV_ORGANIZATION_ID)
        ).scalar_one()

        assessment_count = db.execute(
            select(func.count())
            .select_from(RiskAssessment)
            .where(RiskAssessment.organization_id == DEV_ORGANIZATION_ID)
        ).scalar_one()

        print(
            f"Development demo state: {event_count} event(s), "
            f"{assessment_count} risk assessment(s)."
        )

        if event_count == 0:
            print("No development events found. Reusing the existing deterministic seed pipeline...")
            from scripts.seed_dev_environment import _ingest_events

            _ingest_events(db)
        else:
            print("Development events already exist. Skipping event ingestion.")

        # Use a fresh session because _ingest_events commits its own transaction.
        db.expire_all()

        assessment_count = db.execute(
            select(func.count())
            .select_from(RiskAssessment)
            .where(RiskAssessment.organization_id == DEV_ORGANIZATION_ID)
        ).scalar_one()

        if assessment_count == 0:
            print("No development risk assessment found. Reusing the existing risk-assessment seed pipeline...")
            from scripts.seed_dev_environment import _create_risk_assessment

            _create_risk_assessment(db)
        else:
            print("Development risk assessment already exists. Skipping assessment creation.")

        print("Development demo data bootstrap complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
