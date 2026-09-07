#!/usr/bin/env python
"""Development-only local seed script — SIE Milestone UI-DEV-01: Local
Development Identity & Seeded Intelligence Environment v0.1.

WHAT THIS DOES
---------------
Creates one small, deterministic local-development organization/user/site
and ingests a realistic event history through the REAL production
ingestion pipeline, then creates one baseline risk assessment (with a
backend-generated candidate finding and one manually-rated finding)
through the REAL production risk-assessment API — so that
`GET /api/v1/intelligence/enterprise` and `GET /api/v1/risk-assessments`
return genuinely meaningful, backend-computed data the very first time a
developer points the frontend at a freshly migrated local database. No
frontend fixture, no fabricated score, no invented conclusion anywhere:
every number the UI ends up showing was computed by the same backend
code a production deployment would run.

REUSE, NOT A SECOND SEED MODEL
--------------------------------
The event history comes from `tests/fixtures/enterprise_scenarios.py::
scenario_b_emerging_risk()` — the exact same deterministic (seeded,
`random.Random`-only), already-calibration-tested "emerging risk"
dataset the backend's own test suite exercises (see
tests/evaluation/calibration_harness.py). It is ingested through
`app.intelligence.enterprise_ingestion.enterprise_ingestion_service`,
the same real service `POST /api/v1/data-ingestion/events` uses — this
script is a thin orchestration wrapper around existing, already-tested
production/test code, not a new, competing data-generation mechanism.
The risk assessment is created through the real, running FastAPI `app`
object (in-process `TestClient`, no separate server needed) hitting the
exact same `/api/v1/risk-assessments` routes a real HTTP client would.

SAFETY — FAILS CLOSED
------------------------
Refuses to run at all unless `settings.DEV_MODE` is true. `DEV_MODE` is
a *backend* environment variable (`app/core/config.py`) with no frontend
control surface whatsoever — nothing in Vite/React configuration can
turn it on, and a production deployment that never sets `DEV_MODE=true`
cannot be made to run this script's write path even if somehow invoked
(see `tests/test_seed_dev_environment.py`). This script performs no
authentication or authorization work of its own: every write goes
through the ordinary service layer and the ordinary
`RequestContext`/permission-checked API routes, so tenant isolation and
permission enforcement are exercised exactly as they would be for any
other caller.

IDEMPOTENCY
------------
Deliberately NOT idempotent-by-merge: if the fixed development
organization id already exists, the script refuses to run again rather
than guessing how to reconcile with whatever state is already there.
Re-seeding means dropping and recreating the local database first — see
docs/DEVELOPMENT_SETUP.md for the exact reset commands.

USAGE
------
From `backend/`, against a freshly `alembic upgrade head`-ed local
PostgreSQL database, with `DEV_MODE=true` set in the environment:

    DEV_MODE=true DATABASE_URL=postgresql+psycopg://sie:sie@localhost:5432/sie \\
        python scripts/seed_dev_environment.py

On success it prints the exact `VITE_DEV_USER_ID`/`VITE_DEV_ORGANIZATION_ID`
lines to put in the frontend's `.env.local` — though since both are
FIXED, well-known development constants (see `DEV_ORGANIZATION_ID`/
`DEV_USER_ID` below), `.env.development.example` in the frontend already
has the right values checked in; nothing needs to be copied by hand.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make both `app` and `tests` importable regardless of the caller's CWD —
# this script deliberately lives in scripts/, not tests/, since it is
# development tooling, not a test, but it reuses tests/fixtures/ code (see
# module docstring's "reuse, not a second seed model").
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402

# --- Fixed, deterministic development identifiers ---------------------------------------
# Obviously-synthetic UUIDs (never randomly generated) so the exact same
# organization/user/site ids are produced on every fresh database, letting
# frontend/.env.development.example hardcode matching values -- no
# copy-pasting a freshly generated UUID after every reseed. Collision with
# a real uuid4-generated row is astronomically unlikely (2^-122) and this
# script refuses to overwrite an existing row at these ids in any case.
DEV_ORGANIZATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000d01")
DEV_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000d02")
DEV_SITE_ID = uuid.UUID("00000000-0000-4000-8000-000000000d03")

DEV_ORGANIZATION_NAME = "SIE Local Development Organization"
DEV_USER_NAME = "Development User"
DEV_USER_EMAIL = "dev-user@example.invalid"
DEV_SITE_NAME = "Demo Site (Local Development)"


def _require_dev_mode() -> None:
    if not settings.DEV_MODE:
        sys.exit(
            "Refusing to seed: DEV_MODE is not enabled for this backend process.\n"
            "This script deliberately fails closed -- it never runs against a deployment "
            "that has not explicitly opted into DEV_MODE=true. Set DEV_MODE=true in the "
            "environment this script itself runs in (it does not need to match a separately "
            "running uvicorn process, since this script talks to the database and the FastAPI "
            "app directly, in-process) and try again."
        )


def main() -> None:
    _require_dev_mode()

    # Imported after the DEV_MODE guard so a misconfigured environment
    # never even constructs the app/engine.
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        _seed(db)
    finally:
        db.close()


def _seed(db) -> None:
    from app.models.organization import Organization
    from app.models.organization_membership import OrganizationMembership
    from app.models.site import Site
    from app.models.user import User
    from app.schemas.organization_membership import OrganizationMembershipCreate
    from app.services.membership_service import membership_service
    from app.services.permissions import OrganizationRole

    existing = db.get(Organization, DEV_ORGANIZATION_ID)
    if existing is not None:
        sys.exit(
            f"Refusing to reseed: organization {DEV_ORGANIZATION_ID} ({existing.name!r}) already "
            "exists. Drop and recreate the local database (see docs/DEVELOPMENT_SETUP.md's reset "
            "commands), run `alembic upgrade head`, then re-run this script."
        )

    print(f"Creating development organization {DEV_ORGANIZATION_ID} ...")
    org = Organization(id=DEV_ORGANIZATION_ID, name=DEV_ORGANIZATION_NAME, status="active")
    db.add(org)

    print(f"Creating development site {DEV_SITE_ID} ...")
    site = Site(id=DEV_SITE_ID, organization_id=DEV_ORGANIZATION_ID, name=DEV_SITE_NAME, status="active")
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
        obj_in=OrganizationMembershipCreate(user_id=DEV_USER_ID, role=OrganizationRole.ORG_ADMIN),
    )
    print("Created ORG_ADMIN membership (all permissions, including risk_assessment:approve).")

    _ingest_events(db)
    _create_risk_assessment(db)

    print()
    print("Done. Frontend .env.local values (already the default in .env.development.example):")
    print(f"  VITE_DEV_ORGANIZATION_ID={DEV_ORGANIZATION_ID}")
    print(f"  VITE_DEV_USER_ID={DEV_USER_ID}")
    print(f"  VITE_DEV_ORGANIZATION_NAME={DEV_ORGANIZATION_NAME}")


def _ingest_events(db) -> None:
    """Ingests `scenario_b_emerging_risk()` — see module docstring's
    "reuse, not a second seed model" — through the real
    `EnterpriseIngestionService`, then (a) backdates `ingestion_time` to
    track each event's own `event_time` (mirroring
    `tests/evaluation/calibration_harness.py::
    _backdate_ingestion_time_near_event_time()` exactly, for the same
    reason: a one-shot historical bulk load must not collapse every
    point-in-time bucket into "just now"), and (b) attaches every
    ingested row to the one development Site, for a more realistic demo
    (the scenario builders themselves don't assign a site — see their
    own module docstring)."""
    import random

    from app.intelligence.enterprise_ingestion import enterprise_ingestion_service
    from app.models.safety_event import SafetyEvent
    from tests.fixtures.enterprise_scenarios import incident, inspection, near_miss, observation, scenario_b_emerging_risk, training

    base_time = datetime.now(timezone.utc)
    dataset = scenario_b_emerging_risk(base_time)

    # `scenario_b_emerging_risk()` ships exactly 3 quiet baseline periods
    # (90/60/30 days ago), one short of
    # `settings.INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS` (4 by default) --
    # real, honest behavior (anomaly status reports INSUFFICIENT_DATA
    # rather than guessing), but it means a fresh local seed would never
    # show the ANOMALOUS status this milestone wants demonstrable through
    # the UI. Rather than editing the shared scenario fixture (used by the
    # backend's own calibration test suite, out of scope here) or inventing
    # a new dataset, this adds one more quiet baseline period in the exact
    # same shape as the scenario's own baseline periods, using the exact
    # same builder functions imported from enterprise_scenarios.py -- a
    # reuse-additive extension, not a second, competing generator. A
    # distinct rng seed keeps its synthetic source_record_ids from
    # colliding with the scenario's own.
    rng = random.Random(90031002)
    # Deliberately 180 (not 120) days ago: `_available_baseline_periods()`
    # counts *complete* window_days-length periods between the earliest
    # event and the START of the current 30-day window (not `as_of`
    # itself), so a period merely 120 days back still lands one period
    # short of the minimum. 180 clears it with a safety margin.
    base_days = 6 * 30
    extra_baseline_events = [
        incident(rng, base_time, days_ago=base_days + 5, subtype="FIRST_AID_CASE"),
        near_miss(rng, base_time, days_ago=base_days + 3, subtype="DROPPED_OBJECT"),
        observation(rng, base_time, days_ago=base_days + 7, subtype="UNSAFE_ACT"),
        inspection(rng, base_time, days_ago=base_days + 10, subtype="SITE_INSPECTION"),
        *(training(rng, base_time, days_ago=base_days + i, canonical_status="COMPLETED") for i in range(8)),
    ]
    all_events = [*dataset.events, *extra_baseline_events]

    print(f"Ingesting {len(all_events)} events ({dataset.name!r} scenario + 1 extra quiet baseline period) ...")
    result = enterprise_ingestion_service.ingest_batch(
        db, organization_id=DEV_ORGANIZATION_ID, source_id=None, payloads=all_events
    )
    batch = result.batch
    print(
        f"Ingestion result: {batch.accepted_records} accepted, {batch.partial_records} partial, "
        f"{batch.quarantined_records} quarantined, {batch.rejected_records} rejected, "
        f"{batch.duplicate_records} duplicate (of {batch.total_records} total)."
    )

    delay = timedelta(hours=6)
    rows = db.execute(select(SafetyEvent).where(SafetyEvent.organization_id == DEV_ORGANIZATION_ID)).scalars().all()
    for event in rows:
        event.ingestion_time = event.event_time + delay
        if event.site_id is None:
            event.site_id = DEV_SITE_ID
    db.commit()
    print(f"Backdated ingestion_time and attached site for {len(rows)} events.")


def _create_risk_assessment(db) -> None:
    """Creates one APPROVED baseline risk assessment with a
    backend-generated candidate finding (`generate_candidates=True`,
    the endpoint's own default -- candidates are derived from the
    intelligence just ingested above, never fabricated here) plus one
    manually-authored, explicitly rated finding, through the real
    `/api/v1/risk-assessments` HTTP routes via an in-process
    `TestClient` — exactly the request shape a real browser session
    would send, including the dev-mode identity header."""
    from fastapi.testclient import TestClient

    from app.api.deps_auth import DEV_USER_HEADER
    from app.main import app
    from app.models.ontology_concept import OntologyConcept

    headers = {DEV_USER_HEADER: str(DEV_USER_ID)}
    params = f"?organization_id={DEV_ORGANIZATION_ID}"

    concept = db.execute(
        select(OntologyConcept).where(
            OntologyConcept.concept_key == "VEHICLE_INCIDENT", OntologyConcept.organization_id.is_(None)
        )
    ).scalar_one_or_none()
    if concept is None:
        print(
            "WARNING: GLOBAL ontology concept VEHICLE_INCIDENT not found (expected to be seeded by "
            "migrations/versions/0017_..._governed_risk_area_taxonomy.py) -- skipping risk assessment "
            "creation. Run `alembic upgrade head` against this database and re-run this script."
        )
        return

    now = datetime.now(timezone.utc)
    with TestClient(app) as client:
        print("Creating baseline risk assessment (generate_candidates=True) ...")
        create_response = client.post(
            f"/api/v1/risk-assessments{params}",
            json={
                "scope": "ORGANIZATION",
                "title": "Local Development Baseline Assessment",
                "assessment_type": "BASELINE",
                "assessment_date": now.isoformat(),
                "as_of": now.isoformat(),
                "generate_candidates": True,
            },
            headers=headers,
        )
        if create_response.status_code != 201:
            print(f"WARNING: risk assessment creation failed ({create_response.status_code}): {create_response.text}")
            return
        assessment = create_response.json()
        assessment_id = assessment["id"]
        print(f"Created assessment {assessment_id} with {len(assessment['findings'])} backend-generated candidate finding(s).")

        finding_response = client.post(
            f"/api/v1/risk-assessments/{assessment_id}/findings{params}",
            json={
                "risk_area_concept_id": str(concept.id),
                "title": "Rising near-miss frequency in vehicle operations",
                "description": "Deterministic pattern/anomaly detection flagged a sharp increase in "
                "near misses and unsafe observations for vehicle operations in the current window.",
                "likelihood": 3,
                "consequence": 3,
            },
            headers=headers,
        )
        if finding_response.status_code != 201:
            print(f"WARNING: manual finding creation failed ({finding_response.status_code}): {finding_response.text}")
        else:
            print(f"Created rated finding {finding_response.json()['id']}.")

        submit_response = client.post(f"/api/v1/risk-assessments/{assessment_id}/submit{params}", headers=headers)
        if submit_response.status_code != 200:
            print(f"WARNING: submit failed ({submit_response.status_code}): {submit_response.text}")
            return
        approve_response = client.post(f"/api/v1/risk-assessments/{assessment_id}/approve{params}", headers=headers)
        if approve_response.status_code != 200:
            print(f"WARNING: approve failed ({approve_response.status_code}): {approve_response.text}")
            return
        print(f"Assessment {assessment_id} submitted and approved.")


if __name__ == "__main__":
    main()
