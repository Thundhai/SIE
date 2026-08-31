# SIE Backend — Safety Intelligence Engine (Foundation v0.1)

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

This is the **foundation phase**: a clean backend with core tenancy
models, a REST API, and infrastructure. The AI/LLM layer, RAG, vector
search, predictive models, and Safelytic integration are all out of scope
here and are stubbed out only as empty, documented package placeholders
(`app/intelligence`, `app/knowledge`, `app/ingestion`, `app/analytics`,
`app/predictions`, `app/governance`) so later phases have a predictable
home without a restructure.

## Architecture

```
backend/
  app/
    api/            HTTP layer: FastAPI routers + request-scoped dependencies
      v1/            Versioned routes (health, organizations, sites, data-sources)
    core/           Configuration (Pydantic Settings) and DB engine/session setup
    models/         SQLAlchemy 2.x ORM models (Organization, Site, User, DataSource)
    schemas/        Pydantic v2 request/response schemas
    services/       Tenant-scoped repository/service layer (see below)
    intelligence/   Reserved for a future AI/LLM layer
    knowledge/      Reserved for future knowledge/RAG work
    ingestion/      Reserved for future data ingestion pipelines
    analytics/      Reserved for future analytics
    predictions/    Reserved for future predictive models
    governance/     Reserved for future governance/compliance features
    main.py         FastAPI app instance and router wiring
  migrations/       Alembic migration environment and versions
  tests/            pytest suite (API + service-layer tests, incl. tenant isolation)
  requirements.txt
  Dockerfile
  docker-compose.yml
  alembic.ini
  .env.example
```

**Request flow:** router (`app/api/v1/*`) → dependency resolves and
validates the organization from the URL (`app/api/deps.py`) → service
(`app/services/*`) executes an organization-scoped query → SQLAlchemy model
→ Pydantic response schema.

## Tenant isolation principle

SIE is multi-tenant: every organization-owned table
(`sites`, `users`, `data_sources`, and any table added later) carries a
required, indexed, foreign-keyed `organization_id` column. Isolation is
enforced at two levels, deliberately redundant:

1. **Schema level** (`app/models/base.py::OrganizationScopedMixin`) — every
   organization-owned model includes a non-nullable `organization_id`
   foreign key to `organizations.id`, indexed for query performance and
   set to `ON DELETE CASCADE` so orphaned rows can't outlive their tenant.

2. **Query level** (`app/services/base.py::TenantScopedRepository`) — the
   *only* way the codebase reads or writes an organization-owned table is
   through this base class, and every one of its methods (`create`, `get`,
   `list`) takes `organization_id` as a required keyword argument and
   filters by it. There is no "get by id only" method that could
   accidentally span organizations — the method signatures don't allow it.
   A record's id being known or guessed is not enough to reach it from the
   wrong organization; `get()` returns `None` rather than the row.

3. **API level** (`app/api/deps.py::get_organization_or_404`) — every route
   nested under `/organizations/{organization_id}/...` resolves and
   validates the organization from the URL path first (404 if it doesn't
   exist), and that trusted, path-derived id is what's passed into the
   service layer. `organization_id` is never accepted from a request body,
   so a caller cannot create a resource under a different tenant by
   spoofing a field.

This is covered directly by `tests/test_tenant_isolation.py`, both through
the HTTP API and by calling the service layer directly.

## Prerequisites

* Python 3.12+
* Docker and Docker Compose (for running PostgreSQL, and optionally the
  API itself)

## Running with Docker Compose (recommended)

This starts PostgreSQL and the API together, running migrations
automatically on container start:

```bash
cd backend
cp .env.example .env   # adjust if needed
docker compose up --build
```

The API is then available at `http://localhost:8000`, with interactive
docs at `http://localhost:8000/docs`.

## Running locally (without Docker for the API)

### 1. Start PostgreSQL

Either via Docker Compose (starts just the database):

```bash
cd backend
docker compose up -d db
```

or point `POSTGRES_*` / `DATABASE_URL` in your `.env` at any PostgreSQL
16+ instance you already have running.

### 2. Install dependencies

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # adjust POSTGRES_HOST etc. as needed
```

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Start the API

```bash
uvicorn app.main:app --reload
```

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest
```

Tests run against an in-memory SQLite database, not PostgreSQL — every
model column uses SQLAlchemy's portable types (`Uuid`, `DateTime(timezone=True)`,
`String`) rather than PostgreSQL-specific dialect types, so the schema
behaves identically and the suite runs with no external services. This
keeps the test suite fast and dependency-free while PostgreSQL remains the
target production database, exercised through Alembic and Docker Compose.

## Database migrations

Migrations are managed with Alembic (`migrations/`). The database URL is
never hardcoded in `alembic.ini`; `migrations/env.py` builds it from
`app.core.config.settings`, i.e. from the same environment variables the
application itself uses.

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after changing models in app/models/
alembic revision --autogenerate -m "describe the change"

# Roll back one migration
alembic downgrade -1
```

## API endpoints (v0.1)

| Method | Path                                                    | Description                          |
|--------|----------------------------------------------------------|---------------------------------------|
| GET    | `/health`                                                | Liveness check                       |
| POST   | `/api/v1/organizations`                                  | Create an organization               |
| GET    | `/api/v1/organizations/{organization_id}`                | Get an organization                  |
| POST   | `/api/v1/organizations/{organization_id}/sites`          | Create a site under an organization  |
| GET    | `/api/v1/organizations/{organization_id}/sites`          | List sites for an organization       |
| POST   | `/api/v1/organizations/{organization_id}/data-sources`   | Create a data source                 |
| GET    | `/api/v1/organizations/{organization_id}/data-sources`   | List data sources for an organization|

## Data model (v0.1)

* **Organization** — the tenant root. `id`, `name`, `industry`, `country`,
  `status`, `created_at`, `updated_at`.
* **Site** — a location owned by an organization. Adds `organization_id`,
  `location`.
* **User** — a person belonging to an organization. Adds `organization_id`,
  `email` (unique per organization), `role`.
* **DataSource** — a system SIE ingests from (ingestion itself is not
  implemented yet). Adds `organization_id`, `source_type`, `last_sync_at`.

All primary keys are UUIDs generated application-side. All timestamps are
timezone-aware and stored in UTC.

## Configuration

All configuration is environment-based (`app/core/config.py`, backed by
Pydantic Settings and a local `.env` file — see `.env.example`). No
secrets are committed; `.env` is git-ignored.

## Deliberate scope boundaries (v0.1)

To keep this foundation phase clean and reviewable, the following are
intentionally **not** included yet: authentication/authorization, the
AI/LLM layer, RAG, vector search, predictive models, Safelytic
integration, Redis, and any microservice/Kubernetes topology.

## Known gaps / next phase

* **No authentication or authorization yet.** Every endpoint is open, and
  `organization_id` is trusted directly from the URL path. Before any real
  deployment, requests must be authenticated and the caller's access to
  the requested `organization_id` must be verified (e.g. via a JWT/session
  carrying the caller's own organization and role) — otherwise the tenant
  isolation this foundation implements at the query level is trivially
  bypassed by an unauthenticated caller supplying any UUID.
* **No update/delete endpoints** for any resource yet — only create and
  read, matching what was scoped for this phase.
* **No pagination metadata** (total count, next-page cursor) on list
  endpoints, only `skip`/`limit`.
* **No structured logging, tracing, or rate limiting.**
* **No CI pipeline** wired up in this repository yet to run `pytest`
  automatically on push.
