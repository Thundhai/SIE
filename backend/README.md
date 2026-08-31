# SIE Backend — Safety Intelligence Engine

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

Two milestones are implemented so far:

* **Foundation v0.1** — core tenancy models (Organization, Site, User,
  DataSource), a REST API, and infrastructure (FastAPI, PostgreSQL,
  SQLAlchemy, Alembic, Docker Compose).
* **Knowledge Foundation v0.1** — the data model and service layer for
  storing and governing safety knowledge (KnowledgeSource,
  KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeChunk). See
  [Knowledge architecture](#knowledge-architecture) below.

The AI/LLM layer, RAG, embeddings, vector search, predictive models, and
Safelytic integration are all out of scope so far and are stubbed out only
as empty, documented package placeholders (`app/intelligence`,
`app/ingestion`, `app/analytics`, `app/predictions`, `app/governance`) so
later phases have a predictable home without a restructure. **No AI
training, embeddings, RAG, or predictive analytics exist in this codebase
yet** — the knowledge foundation below stores and structures content for
that future work; it does not perform it.

## Architecture

```
backend/
  app/
    api/            HTTP layer: FastAPI routers + request-scoped dependencies
      v1/            Versioned routes (health, organizations, sites,
                      data-sources, knowledge)
    core/           Configuration (Pydantic Settings) and DB engine/session setup
    models/         SQLAlchemy 2.x ORM models (Organization, Site, User,
                     DataSource, KnowledgeSource, KnowledgeDocument,
                     KnowledgeDocumentVersion, KnowledgeChunk)
    schemas/        Pydantic v2 request/response schemas
    services/       Tenant-scoped repository/service layer (see below)
    intelligence/   Reserved for a future AI/LLM layer
    ingestion/      Reserved for future data ingestion pipelines (crawling,
                     document processing workers, chunk extraction)
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

Note: the empty `app/knowledge/` placeholder package from Foundation v0.1
has been removed — the knowledge domain now lives in `app/models`,
`app/schemas`, `app/services`, and `app/api/v1/knowledge.py` alongside
every other resource, matching how Site/DataSource are organized, rather
than in its own package. The remaining placeholders (`app/intelligence`,
`app/ingestion`, `app/analytics`, `app/predictions`, `app/governance`)
are untouched.

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

The knowledge domain (below) reuses this exact same architecture rather
than inventing a second mechanism — see
[Knowledge architecture](#knowledge-architecture).

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

Two migrations exist so far: `0001` (Foundation v0.1 — organizations,
sites, users, data_sources) and `0002` (Knowledge Foundation v0.1 —
knowledge_sources, knowledge_documents, knowledge_document_versions,
knowledge_chunks). `0001` is not modified by `0002`; new schema changes
are always a new migration on top.

## API endpoints

| Method | Path                                                    | Description                          |
|--------|----------------------------------------------------------|---------------------------------------|
| GET    | `/health`                                                | Liveness check                       |
| POST   | `/api/v1/organizations`                                  | Create an organization               |
| GET    | `/api/v1/organizations/{organization_id}`                | Get an organization                  |
| POST   | `/api/v1/organizations/{organization_id}/sites`          | Create a site under an organization  |
| GET    | `/api/v1/organizations/{organization_id}/sites`          | List sites for an organization       |
| POST   | `/api/v1/organizations/{organization_id}/data-sources`   | Create a data source                 |
| GET    | `/api/v1/organizations/{organization_id}/data-sources`   | List data sources for an organization|
| POST   | `/api/v1/knowledge/sources`                              | Create a knowledge source (GLOBAL or ORGANIZATION) |
| GET    | `/api/v1/knowledge/sources`                              | List knowledge sources (GLOBAL, or one organization's — see below) |
| GET    | `/api/v1/knowledge/sources/{source_id}`                  | Get a knowledge source               |
| POST   | `/api/v1/knowledge/documents`                            | Create a document under a source     |
| GET    | `/api/v1/knowledge/documents/{document_id}`              | Get a knowledge document             |
| POST   | `/api/v1/knowledge/documents/{document_id}/versions`     | Create a document version            |
| GET    | `/api/v1/knowledge/documents/{document_id}/versions`     | List a document's versions           |

## Data model

* **Organization** — the tenant root. `id`, `name`, `industry`, `country`,
  `status`, `created_at`, `updated_at`.
* **Site** — a location owned by an organization. Adds `organization_id`,
  `location`.
* **User** — a person belonging to an organization. Adds `organization_id`,
  `email` (unique per organization), `role`.
* **DataSource** — a system SIE ingests from (ingestion itself is not
  implemented yet). Adds `organization_id`, `source_type`, `last_sync_at`.
* **KnowledgeSource, KnowledgeDocument, KnowledgeDocumentVersion,
  KnowledgeChunk** — the knowledge foundation; see
  [Knowledge architecture](#knowledge-architecture) below for the full
  field list and design.

All primary keys are UUIDs generated application-side. All timestamps are
timezone-aware and stored in UTC.

## Knowledge architecture

The knowledge foundation stores and governs safety knowledge as a linear
chain of increasingly granular records:

```
Global Knowledge  ─┐
                    ├──▶ Knowledge Source ──▶ Knowledge Document ──▶ Document Version ──▶ Knowledge Chunk
Organization       ─┘
Knowledge
```

* **KnowledgeSource** — the root provenance record: who published this
  knowledge, what kind of thing it is (`source_type`), and its governance
  state (`verification_status`: PENDING → UNDER_REVIEW → VERIFIED /
  REJECTED / EXPIRED / SUPERSEDED). This is where GLOBAL vs. ORGANIZATION
  scope is decided (see below) — every document under a source inherits
  that scope.
* **KnowledgeDocument** — one document belonging to a source (e.g. one
  regulation section, one internal procedure). Carries its own
  `organization_id`, denormalized from its source, so document queries can
  be tenant-filtered directly.
* **KnowledgeDocumentVersion** — one immutable, ingested snapshot of a
  document's content. Versions are append-only: re-ingesting the same
  content is idempotent (`content_hash`, see below), and a superseded
  version is marked via `superseded_at` rather than edited or deleted. No
  binary file is stored in PostgreSQL — `storage_reference` is a
  placeholder pointer at wherever the real file will eventually live in
  object storage, and `extracted_text` holds plain extracted text for
  downstream processing.
* **KnowledgeChunk** — a citable slice of one version's content
  (`chunk_index`, `content`, `character_count`, optional `page_number` /
  `section_title` / free-form `metadata`). This is the smallest unit of
  provenance, intended to support a future evidence-citation feature. No
  embedding or vector column exists on this table yet.

### Global Knowledge vs. Organization Knowledge

A `KnowledgeSource` is either:

* **GLOBAL** — published knowledge not owned by any tenant (a regulation,
  an industry standard, a public safety bulletin). `organization_id` is
  `NULL`.
* **ORGANIZATION** — a tenant's own knowledge (an internal procedure, an
  incident report). `organization_id` is required.

This is enforced at the database level by a `CHECK` constraint on
`knowledge_sources` (`ck_knowledge_sources_scope_org_consistency`), not
just application logic — a row that is GLOBAL with an `organization_id`
set, or ORGANIZATION with `organization_id` NULL, cannot exist. Every
`KnowledgeDocument` under a source inherits that same scope: its
`organization_id` is always derived server-side from its source, never
accepted at face value from a client
(`KnowledgeDocumentService.create` — see
`app/services/knowledge_document_service.py`), so a document can never end
up attached to a different organization than its source, or organization-
scoped under a GLOBAL source.

`KnowledgeDocumentVersion` and `KnowledgeChunk` do not carry their own
`organization_id` — their tenancy is transitive, resolved by walking the
foreign-key chain back to their document (and its source). An endpoint
that needs to authorize access to a version or chunk resolves and
tenant-checks the parent document first (see `app/api/v1/knowledge.py`),
exactly the same "resolve-then-authorize" shape as
`get_organization_or_404` in the foundation.

### Tenant isolation (reused, not reinvented)

The knowledge domain is built on the *same* tenant-scoping architecture as
the rest of SIE — `app/services/base.py` — extended with one addition,
`NullableTenantScopedRepository`, for the two knowledge tables whose
`organization_id` can legitimately be `NULL` (GLOBAL). It applies the
identical non-negotiable-signature principle as `TenantScopedRepository`:
every `get`/`list` call takes `organization_id` explicitly, and the two
scopes are never mixed in one query result — `organization_id=None`
returns only global rows, a UUID returns only that organization's rows,
and there is no third mode that returns both. This is what makes
"a caller cannot accidentally list all organization-private knowledge"
structural rather than a matter of remembering to add a filter.

Because knowledge routes aren't nested under
`/organizations/{organization_id}/...` (a source can be GLOBAL, so there's
no single tenant path segment that always applies), organization context
is passed explicitly as an `organization_id` query parameter instead:
omitted to reach GLOBAL knowledge, required and checked against the actual
owner to reach ORGANIZATION-scoped knowledge. A source or document that
belongs to a different organization than the one asserted (or none at
all) returns 404, the same as an unknown id — existence is never leaked
across tenants.

### Duplicate content and versioning

`KnowledgeDocumentVersionService.create` is idempotent on
`(document_id, content_hash)`: re-ingesting byte-identical content for a
document returns the existing version rather than creating a diverging
duplicate row. A unique constraint on that pair
(`uq_knowledge_document_versions_document_content`) is the safety net for
concurrent writers. When a genuinely new version is created, it becomes
the document's `current_version_id`, and the version it replaces has its
`superseded_at` set — a simple, linear versioning policy (newest ingested
version wins) that is easy to change later without touching the schema.

### Provenance / lineage

Every knowledge record is traceable back to its source through the
foreign-key chain itself — `KnowledgeChunk.document_version_id` →
`KnowledgeDocumentVersion.document_id` → `KnowledgeDocument.source_id` →
`KnowledgeSource` — rather than a separate event-log table. A
`KnowledgeDocumentVersion`'s `ingestion_status` and `created_at` serve as
its ingestion event for now. `app/services/knowledge_provenance_service.py`
provides `get_chunk_provenance()`, a read-side helper that walks this
chain and returns the full lineage for one chunk; no new data model is
introduced for it, matching the milestone's instruction not to
overengineer a separate event system before one is needed.

### What this milestone deliberately does not do

**No AI training, embeddings, RAG, semantic/vector search, or predictive
analytics exist in this codebase.** This phase only stores and structures
knowledge content — plain text chunks with structural metadata — so that
future work has a stable foundation to build on:

* `KnowledgeChunk` has the fields (content, ordering, page/section) an
  embeddings/vector-search layer will need to index, but no embedding or
  vector column.
* `verification_status` on `KnowledgeSource` gives a source-verification
  workflow states to move through, but no workflow engine exists yet.
* Chunk `metadata` and the full provenance chain are what an evidence-
  citation feature will read from, but no citation feature exists yet.
* `app/ingestion` remains an empty placeholder package — chunk creation
  has a service (`KnowledgeChunkService.create_many`) but no HTTP endpoint
  or worker calls it yet; that lands with a real ingestion pipeline.
* `external_reference`/`external_document_id` give an external-ingestion
  source system something to key off of, but no crawler or external
  connector exists yet.
* `knowledge_freshness` (staleness monitoring against `review_date`) is
  not implemented — `review_date` is stored but nothing acts on it yet.

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
* **No chunk HTTP endpoints or ingestion worker yet.** `KnowledgeChunkService`
  exists and is tested at the service layer, but nothing in `app/ingestion`
  calls it yet — there is no document-processing step that produces chunks
  from a version's `extracted_text`.
* **No `KnowledgeSourceUpdate`/verification-workflow transition endpoint.**
  `verification_status` can only be set at creation (defaults to PENDING);
  moving a source through UNDER_REVIEW → VERIFIED etc. isn't exposed yet.
* **The GLOBAL/ORGANIZATION scope-consistency `CHECK` constraint is
  single-table.** It guarantees `knowledge_sources.organization_id` is
  NULL iff `scope_type` is GLOBAL. The corresponding invariant on
  `knowledge_documents` (its `organization_id` must match its source's) is
  enforced only in `KnowledgeDocumentService.create` — PostgreSQL `CHECK`
  constraints cannot reference another table, so this one is
  application-enforced, not database-enforced. A direct SQL write that
  bypasses the service layer could violate it; this is the one place in
  the knowledge foundation with that gap.
