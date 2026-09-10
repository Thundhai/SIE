# SIE Local Development Setup

**SIE Milestone UI-DEV-01: Local Development Identity & Seeded
Intelligence Environment v0.1.** Answers one question: *what do I do
after cloning SIE to see the Intelligence workspace populated with real
data?*

Everything below uses already-existing SIE mechanisms — the
development-only `DEV_MODE` header (`backend/app/api/deps_auth.py`),
the frontend's `DevAuthProvider`/`devIdentity.ts`
(`docs/FRONTEND_ARCHITECTURE.md` §3), and the backend's own
calibration-tested scenario fixtures
(`backend/tests/fixtures/enterprise_scenarios.py`) — orchestrated by
one new script, `backend/scripts/seed_dev_environment.py`. No new
authentication mechanism, no frontend fixture standing in for real
intelligence, no fabricated risk score anywhere in this path: every
number the UI ends up showing was computed by the same backend code a
production deployment would run, against real (if synthetic) seeded
events.

## 1. Start PostgreSQL + pgvector

```bash
sudo pg_ctlcluster 16 main start   # or however Postgres 16 is managed locally
sudo -u postgres psql -c "CREATE USER sie WITH PASSWORD 'sie';"     # first time only
sudo -u postgres psql -c "CREATE DATABASE sie OWNER sie;"           # first time only
```

## 2. Apply migrations

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://sie:sie@localhost:5432/sie"
python -m alembic upgrade head
```

Migration `0017` seeds the GLOBAL risk-area ontology concepts
(`VEHICLE_INCIDENT` and friends) the seed script's risk assessment
needs — nothing further to seed for that part.

## 3. Seed the development organization, events, and a risk assessment

```bash
# Still in backend/, DATABASE_URL still exported from step 2.
DEV_MODE=true python scripts/seed_dev_environment.py
```

This creates one fixed-id development organization/user/site, ingests
a real, deterministic "emerging risk" event scenario through the real
`EnterpriseIngestionService`, and creates one baseline risk assessment
(a backend-generated candidate finding plus one manually-rated finding)
through the real `/api/v1/risk-assessments` API, then submits and
approves it. See the script's own module docstring for exactly what it
does and why each piece is reused rather than invented. It prints a
confirmation and refuses to run again against the same database (see
§6, "Resetting").

## 4. Start the backend

```bash
# Still in backend/.
DEV_MODE=true DATABASE_URL="postgresql+psycopg://sie:sie@localhost:5432/sie" \
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`DEV_MODE=true` is what makes the `X-SIE-Dev-User-Id` development
identity header work at all (`backend/app/api/deps_auth.py`) — a
production deployment never sets this, and nothing on the frontend can
turn it on (see §7).

## 5. Start the frontend

```bash
# From the repo root.
cp .env.development.example .env.local   # first time only
npm install                              # first time only
npm run dev
```

`.env.development.example`'s `VITE_DEV_ORGANIZATION_ID`/
`VITE_DEV_USER_ID` are fixed constants that match the ids
`seed_dev_environment.py` always creates — nothing to copy by hand.
Open the app; `DevAuthProvider` resolves that identity against the real
backend (`GET /organizations/{id}`, `GET /organizations/{id}/members/
{user_id}`, `GET /auth/me`) and the header shows a small "Development
identity" pill so it's always obvious this is not a real session.

## 6. Verifying Intelligence is using the real backend

- Open **Intelligence** in the sidebar (the teal-accented nav item).
  Risk score, classification, indicators, the Anomalies tab, the
  Patterns tab, and the Associations tab should all show real,
  non-empty values — an `ANOMALOUS` badge on `near_miss_count`/
  `observation_count`/`unsafe_observation_count`, at least one
  `Recurring pattern` badge on the Patterns tab.
- Open your browser's network tab: every one of those numbers comes
  from a single `GET /api/v1/intelligence/enterprise?organization_id=...`
  response — there is no frontend recalculation anywhere in
  `src/features/intelligence/`.
- Open **Risk Assessments**: one `Approved` "Local Development Baseline
  Assessment" should be listed; opening it shows its findings, again
  from `GET /api/v1/risk-assessments` directly, never a fixture (there
  is no fixture repository for either Intelligence or Risk Assessments
  — see `docs/FRONTEND_ARCHITECTURE.md` §10's "no fixture path for
  these two domains").

## 7. Resetting

The seed script is deliberately **not** idempotent-by-merge — re-running
it against a database that already has the fixed development
organization id refuses, rather than guessing how to reconcile existing
state. To start over:

```bash
sudo -u postgres psql -c "DROP DATABASE IF EXISTS sie;"
sudo -u postgres psql -c "CREATE DATABASE sie OWNER sie;"
cd backend && python -m alembic upgrade head
DEV_MODE=true DATABASE_URL="postgresql+psycopg://sie:sie@localhost:5432/sie" \
    python scripts/seed_dev_environment.py
```

## 8. Production safety — what this setup can and cannot do

- **`DEV_MODE` is backend-only.** It is read once, from the backend
  process's own environment (`backend/app/core/config.py`), and
  defaults to `false`. Nothing in `.env.local`, Vite configuration, or
  any frontend build can set it — there is no code path from frontend
  configuration to the backend's `DEV_MODE` flag at all.
- **A production deployment never runs the seed script or sets
  `DEV_MODE=true`.** Both are operator actions on a machine the
  operator controls; `tests/test_seed_dev_environment.py` and the
  pre-existing `tests/test_dev_mode_gate.py` verify the request-time
  and seed-time mechanisms both fail closed when `DEV_MODE` is not
  explicitly enabled.
- **The frontend never has a second production-auth mechanism.**
  `ProdAuthProvider` (a real OIDC/OAuth2 seam, `docs/PRODUCTION_AUTH.md`)
  is entirely separate code from `DevAuthProvider`; which one mounts is
  decided by build-time frontend configuration, and `DevAuthProvider`
  itself does nothing at all — shows an honest "not authenticated"
  state — unless both `VITE_DEV_USER_ID` and `VITE_DEV_ORGANIZATION_ID`
  are explicitly set.
- **Tenant isolation is unchanged.** The seed script's every write goes
  through the ordinary service layer and the ordinary
  permission-checked API routes (creating the risk assessment goes
  through a real, in-process `TestClient` hitting the real HTTP routes)
  — it introduces no new code path that could weaken cross-tenant
  isolation, and the backend's full existing tenant-isolation test
  suite (dozens of tests across `tests/test_events_tenant_isolation.py`,
  `tests/test_actions_api.py`, `tests/test_risk_assessment_api.py`, and
  others) is unmodified by this milestone.
