# SIE Backend — Safety Intelligence Engine

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

Six milestones are implemented so far:

* **Foundation v0.1** — core tenancy models (Organization, Site, User,
  DataSource), a REST API, and infrastructure (FastAPI, PostgreSQL,
  SQLAlchemy, Alembic, Docker Compose).
* **Knowledge Foundation v0.1** — the data model and service layer for
  storing and governing safety knowledge (KnowledgeSource,
  KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeChunk). See
  [Knowledge architecture](#knowledge-architecture) below.
* **Identity & Access Foundation v0.1** — organization membership, roles,
  permissions, authorization, and tenant context: the model SIE will
  authenticate real users and machine clients against once a real
  identity provider is connected. See
  [Identity architecture](#identity-architecture) below.
* **Universal Knowledge & Data Ingestion Engine v0.1** — turns an
  uploaded file (PDF, DOCX, TXT, RTF, CSV, XLSX, PPTX, with an
  architectural boundary for JSON/XML/images) into
  KnowledgeDocument/KnowledgeDocumentVersion/KnowledgeChunk rows, format
  by format rather than as one plain-text pipeline. See
  [Universal ingestion architecture](#universal-ingestion-architecture)
  below.
* **Knowledge Quality & Semantic Chunking Foundation v0.1** — turns
  normalized, extracted content into well-structured, quality-assessed,
  fully-attributed `KnowledgeChunk` rows: section-hierarchy detection,
  structure-aware chunking (headings stay with their content, tables and
  spreadsheet rows are never flattened into misleading prose), a
  deterministic extraction-quality assessment kept strictly separate from
  source authority and verification status, and a full
  chunk-to-source provenance chain. See [Knowledge Quality & Semantic
  Chunking Pipeline](#knowledge-quality--semantic-chunking-pipeline)
  below.
* **Semantic Knowledge Engine v0.1** — semantic embeddings and
  metadata-filtered vector retrieval over `KnowledgeChunk`, on
  PostgreSQL + pgvector: a deterministic embedding provider abstraction,
  embedding model/version tracking (multiple models coexist per chunk,
  never overwritten), tenant-isolated and metadata-filtered similarity
  search with a minimum-similarity floor and a first-class
  `NO_RELEVANT_EVIDENCE` outcome, full provenance on every result, and a
  synthetic evaluation corpus with real, honestly-reported Recall@K
  numbers. Proves retrieval works *before* any LLM/RAG layer exists. See
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture)
  below.

The AI/LLM layer, RAG, predictive models, OCR execution, transcription,
and Safelytic integration are all out of scope so far and are stubbed
out only as empty, documented package placeholders (`app/intelligence`,
`app/analytics`, `app/predictions`, `app/governance`) or interface-only
modules (`app/ingestion/ocr.py`) so later phases have a predictable home
without a restructure. **No AI training, RAG, prompt engineering, answer
generation, or predictive analytics exist in this codebase yet** — as of
the Semantic Knowledge Engine milestone, embeddings and vector similarity
search *do* exist (see above) — everything below that layer stores,
structures, and now retrieves content for a future reasoning layer;
nothing yet reasons over it or generates an answer.

## Architecture

```
backend/
  app/
    api/            HTTP layer: FastAPI routers + request-scoped dependencies
      deps.py         Organization path-resolution dependency (pre-identity)
      deps_auth.py     Identity/authorization dependencies (see Identity architecture)
      v1/            Versioned routes (health, organizations, sites,
                      data-sources, knowledge, memberships, ingestion)
    core/           Configuration (Pydantic Settings) and DB engine/session setup
    models/         SQLAlchemy 2.x ORM models (Organization, Site, User,
                     DataSource, KnowledgeSource, KnowledgeDocument,
                     KnowledgeDocumentVersion, KnowledgeChunk,
                     OrganizationMembership, Identity, AuditLog,
                     IngestedFile, IngestionJob)
    schemas/        Pydantic v2 request/response schemas
    services/       Tenant-scoped repository/service layer, plus
                     permissions/authorization/tenant-context/identity/audit
                     services (see Identity architecture) and
                     ingestion_service.py (see Universal ingestion architecture)
    ingestion/      The ingestion engine itself — detection, format
                     adapters, storage, chunking, OCR interface (see
                     Universal ingestion architecture below); no longer
                     an empty placeholder as of this milestone
    intelligence/   Reserved for a future AI/LLM layer
    analytics/      Reserved for future analytics
    predictions/    Reserved for future predictive models
    governance/     Reserved for future governance/compliance features
    main.py         FastAPI app instance and router wiring
  migrations/       Alembic migration environment and versions
  tests/            pytest suite (API + service-layer tests, incl. tenant isolation)
    fixtures/ingestion/  Small, synthetic PDF/DOCX/XLSX/CSV/PPTX/RTF/TXT
                          files used by the ingestion tests — see that
                          directory's own README.md
  requirements.txt
  Dockerfile
  docker-compose.yml
  alembic.ini
  .env.example
```

Note: the empty `app/knowledge/` placeholder package from Foundation v0.1
has been removed — the knowledge domain lives in `app/models`,
`app/schemas`, `app/services`, and `app/api/v1/knowledge.py` alongside
every other resource, matching how Site/DataSource are organized, rather
than in its own package. `app/ingestion/` was a similar empty placeholder
through the first three milestones; this one is where it became real
code. The remaining placeholders (`app/intelligence`, `app/analytics`,
`app/predictions`, `app/governance`) are still untouched.

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

Everything above predates real identity: `organization_id` is trusted
directly from the URL, with no check that the caller is actually allowed
into that organization. The Identity & Access Foundation
([below](#identity-architecture)) adds that check — `TenantContext`,
authorized via `OrganizationMembership` — as a layer *in front of* this
same repository architecture, not a replacement for it. See
["Existing organization-scoped APIs"](#existing-organization-scoped-apis)
for exactly which routes do and don't use it yet.

## Prerequisites

* Python 3.12+
* Docker and Docker Compose (for running PostgreSQL, and optionally the
  API itself) — `docker-compose.yml` uses `pgvector/pgvector:pg16`
  (upstream PostgreSQL 16 with the pgvector extension pre-installed) so
  semantic embeddings work out of the box; see [Semantic Knowledge
  Architecture](#semantic-knowledge-architecture) and the **known
  migration-0005 issue** in [Known gaps](#known-gaps--next-phase) before
  relying on `docker compose up` end to end

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

Ingestion tests use real small fixture files
(`tests/fixtures/ingestion/`, PDF/DOCX/XLSX/CSV/PPTX/RTF/TXT — see that
directory's own README.md for what each one is and how it was generated)
rather than strings standing in for file content, and a per-test
temporary directory (`tmp_path`, via an autouse fixture in
`tests/conftest.py`) rather than the real `var/ingested_files` storage
path.

**Semantic embeddings and retrieval are the one exception to "no
external services."** `KnowledgeChunkEmbedding` rows themselves round-trip
through pgvector's SQLAlchemy `Vector` type on SQLite fine, but the
*search* operators (`<=>` cosine distance, `.cosine_distance()`) are
real PostgreSQL/pgvector SQL with no SQLite equivalent — see [Semantic
Knowledge Architecture](#semantic-knowledge-architecture) and
`tests/postgres_support.py`. Those tests are marked
`@pytest.mark.postgres`, live in `tests/test_retrieval_service.py`,
`tests/test_retrieval_api.py`'s one end-to-end test, and
`tests/evaluation/`, and are **skipped automatically** (not failed) when
no reachable PostgreSQL + pgvector server is configured — a plain
`pytest` run with no such server passes cleanly on everything else. To
run them: point `PG_TEST_DATABASE_URL` at a real PostgreSQL + pgvector
database (defaults to `postgresql+psycopg://sie:sie@localhost:5432/sie_test` —
a separate database from the application's own `sie` one), e.g.:

```bash
PG_TEST_DATABASE_URL=postgresql+psycopg://sie:sie@localhost:5432/sie_test pytest
```

No AI provider, API key, or network access is required for *any* test in
this suite, embeddings/retrieval included — `HashingEmbeddingProvider`
(the only embedding provider exercised anywhere in this codebase's tests)
is fully deterministic and offline. See [Semantic Knowledge
Architecture](#semantic-knowledge-architecture) for why.

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

Four migrations exist so far: `0001` (Foundation v0.1 — organizations,
sites, users, data_sources), `0002` (Knowledge Foundation v0.1 —
knowledge_sources, knowledge_documents, knowledge_document_versions,
knowledge_chunks), `0003` (Identity & Access Foundation v0.1 —
organization_memberships, identities, audit_logs, plus a compatibility
change to the `users` table — see
["Compatibility concerns"](#identity-architecture) below), and `0004`
(Universal Knowledge & Data Ingestion Engine v0.1 — ingested_files,
ingestion_jobs; purely additive, no changes to any existing table).
Earlier migrations are never modified; new schema changes are always a
new migration on top.

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
| GET    | `/api/v1/knowledge/documents/{document_id}/versions/{version_id}/chunks` | List one version's chunks (read-only — see below) |
| POST   | `/api/v1/organizations/{organization_id}/members`        | Add a member (`users:manage`)        |
| GET    | `/api/v1/organizations/{organization_id}/members`        | List members (`users:read`)          |
| GET    | `/api/v1/organizations/{organization_id}/members/{user_id}` | Get one member (`users:read`)     |
| POST   | `/api/v1/knowledge/ingestion`                             | Upload and ingest a file (`knowledge:manage`) |
| POST   | `/api/v1/knowledge/retrieval/search`                      | Semantic evidence search (authenticated; `knowledge:read` if `filters.organization_id` is given) |

The membership endpoints, the ingestion endpoint, and the retrieval
search endpoint are the routes in this codebase that require
authentication today (the retrieval endpoint additionally requires a
permission check whenever an `organization_id` filter is supplied) — see
[Identity architecture](#identity-architecture) for what that means in
practice (development-mode only, no real identity provider connected
yet) and why the other routes above them still don't, and
[Universal ingestion architecture](#universal-ingestion-architecture) /
[Semantic Knowledge Architecture](#semantic-knowledge-architecture) for
the ingestion and retrieval endpoints' own authorization rules (global vs.
organization knowledge). There is deliberately no endpoint to *create* or
modify chunks — see [Knowledge Quality & Semantic Chunking
Pipeline](#knowledge-quality--semantic-chunking-pipeline) for why chunk
generation is controlled by ingestion processing only, and for the
tenant-scoping the one read endpoint reuses from its sibling knowledge
read routes.

## Data model

* **Organization** — the tenant root. `id`, `name`, `industry`, `country`,
  `status`, `created_at`, `updated_at`.
* **Site** — a location owned by an organization. Adds `organization_id`,
  `location`.
* **User** — a platform-level identity (not organization-scoped — see
  [Identity architecture](#identity-architecture)). `email` (globally
  unique), `name`, `status`, an optional `organization_id` (a convenience
  default organization, not an access grant), and an optional
  `platform_role`.
* **DataSource** — a reference to an external system SIE may one day sync
  with directly (an EHS platform, an ERP, an IoT feed — see the Identity
  architecture's "machine clients" note). Adds `organization_id`,
  `source_type`, `last_sync_at`. Distinct from — and not used by — the
  file-upload ingestion engine below, which reads standalone files, not
  external systems.
* **KnowledgeSource, KnowledgeDocument, KnowledgeDocumentVersion,
  KnowledgeChunk** — the knowledge foundation; see
  [Knowledge architecture](#knowledge-architecture) below for the full
  field list and design.
* **OrganizationMembership, Identity, AuditLog** — the identity & access
  foundation; see [Identity architecture](#identity-architecture) below.
* **IngestedFile, IngestionJob** — the ingestion engine's own file
  metadata and per-attempt job history; see
  [Universal ingestion architecture](#universal-ingestion-architecture)
  below.
* **KnowledgeChunkEmbedding** — one embedding vector per
  (chunk, provider, model_name, model_version), pgvector-backed; see
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture)
  below.

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

`KnowledgeDocumentVersion` does not carry its own `organization_id` — its
tenancy is transitive, resolved by walking the foreign-key chain back to
its document (and its source). `KnowledgeChunk` (and, one milestone
later, `KnowledgeChunkEmbedding`) *do* carry a denormalized
`organization_id`, copied from their document at write time — the
Knowledge Quality & Semantic Chunking milestone added this specifically
so chunk (and later embedding) queries can be tenant-filtered directly,
without a join back through the version and document on every retrieval
query — see [Semantic Knowledge
Architecture](#semantic-knowledge-architecture)'s tenant isolation
section for why that matters for retrieval specifically. An endpoint that
needs to authorize access to a version resolves and tenant-checks the
parent document first (see `app/api/v1/knowledge.py`), exactly the same
"resolve-then-authorize" shape as `get_organization_or_404` in the
foundation.

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

## Identity architecture

```
OIDC/OAuth2-compatible identity provider
    │  (real token verification — not implemented yet)
    ▼
Identity Resolver        app/services/identity_service.py
    │  (links an external identity to a SIE User, creating one if needed)
    ▼
SIE User                 app/models/user.py
    │
    ▼
Organization Membership  app/models/organization_membership.py
    │  (role, per organization; ACTIVE/SUSPENDED/INVITED/REVOKED)
    ▼
Role                     app/services/permissions.py::OrganizationRole
    │
    ▼
Permissions              app/services/permissions.py::Permission, ROLE_PERMISSIONS
    │
    ▼
Tenant Context            app/services/tenant_context.py
    │  (user_id, organization_id, role, permissions — authorized, not asserted)
    ▼
Services / Repositories   app/services/*, app/services/base.py
```

**SIE does not implement password authentication, and never stores a
password or credential of any kind.** There is no `password` column
anywhere in this schema, and there won't be one — see the milestone
constraint this was built under: no custom password system, no API keys,
no OAuth client credentials, no commercial identity provider dependency.
Production authentication is meant to be an external OIDC/OAuth2 identity
provider (Auth0, Entra ID, Okta, Keycloak, or anything else that speaks
the standard) verifying a token and handing SIE a set of claims — this
codebase defines the *boundary* that verification plugs into
(`app.services.identity_service.TokenVerifier`, a `Protocol`) without
depending on any specific provider's SDK. No real implementation of that
protocol exists yet; connecting one is future work.

### Authentication vs. authorization vs. tenant isolation

Three distinct concerns, each with its own module, deliberately not
conflated:

* **Authentication** — "who is making this request." Answered by
  verifying a token's signature against an identity provider and
  extracting its claims (not implemented — see `TokenVerifier` above),
  then resolving those claims to a `User` via `IdentityResolverService`.
  In this milestone, the *only* thing that stands in for this is the
  development-only mechanism described below.
* **Authorization** — "is this (now-known) user allowed to do this
  specific thing." Answered by `AuthorizationService.can()`
  (`app/services/authorization_service.py`): given a user, a `Permission`,
  and an organization, it checks membership existence, membership status,
  and the membership's role's permission set (or the explicit
  `PLATFORM_ADMIN` exception).
* **Tenant isolation** — "does this database query stay inside the
  tenant boundary it's supposed to." Unchanged from the Foundation
  milestones: `TenantScopedRepository` /
  `NullableTenantScopedRepository` (`app/services/base.py`), which every
  organization-owned table's service is still built on. Authorization
  decides *whether* a request should proceed with a given
  `organization_id`; tenant isolation is what makes that
  `organization_id`, once accepted, incapable of leaking another
  tenant's rows. Authorization without tenant isolation would still leak
  data through a buggy query; tenant isolation without authorization
  (Foundation v0.1's actual state, and still most of this codebase's
  actual state — see below) means anyone can supply any
  `organization_id` and be trusted.

`TenantContext` is what carries an authorization decision into the
tenant-isolation layer: it is the only thing
`app/api/deps_auth.py::get_tenant_context` produces, it can only be
constructed by `authorize_tenant_context()` (direct construction raises
`TypeError` — see `app/services/tenant_context.py`), and that function is
the one place all three concerns meet: it resolves the user
(authentication's output), checks membership status and computes
permissions (authorization), and returns the object services/repositories
consume (tenant isolation's input).

### Users, membership, roles, and permissions

* **User** (`app/models/user.py`) is a platform-level identity, not an
  organization-scoped record — see the note in the Data model section
  above and the design-note docstring in that file for exactly how and
  why this differs from Foundation v0.1's original User model.
* **OrganizationMembership** (`app/models/organization_membership.py`)
  is the authoritative user↔organization relationship: one row per
  (user, organization) pair — never duplicated, even across statuses; a
  status change updates the existing row rather than inserting a new one
  (`uq_organization_memberships_user_organization`). `role` is a plain
  string, not a native database enum, validated at the service layer
  against `OrganizationRole` — new roles are meant to be addable without a
  migration.
* **Roles** (`app/services/permissions.py::OrganizationRole`): `ORG_ADMIN`,
  `HSE_MANAGER`, `HSE_ANALYST`, `HSE_USER`, `VIEWER`. `PLATFORM_ADMIN` is
  *not* one of these — it's a property of a `User`
  (`User.platform_role`), because platform-wide administration isn't
  scoped to one organization.
* **Permissions** (`app/services/permissions.py::Permission`): a small,
  fixed vocabulary (`organization:read`/`:manage`, `site:read`/`:manage`,
  `knowledge:read`/`:manage`/`:verify`, `safety_data:read`/`:write`,
  `intelligence:read`, `prediction:read`, `intervention:read`/`:manage`,
  `governance:read`/`:manage`, `users:read`/`:manage`) with an initial
  `ROLE_PERMISSIONS` mapping — e.g. `VIEWER` has every `:read` permission
  and no `:manage`/`:write`/`:verify` permission at all; member management
  (`users:manage`) is reserved for `ORG_ADMIN` (and `PLATFORM_ADMIN`).

### Development-only identity mechanism

There is no real authentication in this milestone. To exercise the
Authorization → TenantContext pipeline against real HTTP requests (the
membership endpoints), `app/api/deps_auth.py` provides
`get_dev_authenticated_user_id`, which:

* **only operates when `settings.DEV_MODE` is true** — off by default
  (`DEV_MODE=false`), so a deployment that never configures real
  authentication fails closed: every route that depends on it returns
  **501 Not Implemented**, not "fall back to trusting the caller."
* reads one request header, `X-SIE-Dev-User-Id`, naming an *existing*
  `User` by id. No token, no signature, no expiry — it is not
  authentication, it is a name.
* **never accepts a permission, a role, or an organization directly.**
  The header can only ever grant exactly what the named user's real,
  already-stored `OrganizationMembership` rows say they have — checked by
  the same `authorize_tenant_context()` a real integration would call.
  There is no way to use this header to grant a permission the named user
  doesn't otherwise have, or to reach an organization they aren't an
  active member of.
* is a FastAPI dependency reading a header, **not an HTTP login endpoint**
  — no route mints, issues, or returns anything resembling a credential.
  This follows the milestone's own stated preference for "dependency
  injection/mocked identity... rather than exposing a development HTTP
  endpoint."

**This must be replaced by real OIDC/OAuth2 token verification
(implementing `TokenVerifier`) before any production deployment**, and
`DEV_MODE` must never be `true` in a production environment. See
`tests/test_dev_mode_gate.py` for the tests covering this gate's failure
modes.

### Existing organization-scoped APIs

The membership endpoints (`POST`/`GET .../members`) are this milestone's
reference implementation of the full pipeline: every route requires a
resolved identity and an explicit `Permission` check via
`app/api/deps_auth.py::require_permission`, and the `organization_id` URL
segment is only ever used to ask `authorize_tenant_context` whether the
caller is actually an active member — never to filter data directly.

The organizations/sites/data-sources/knowledge routes built in the two
earlier milestones (`app/api/v1/organizations.py`, `sites.py`,
`data_sources.py`, `knowledge.py`) are **deliberately left as they were**:
they still trust `organization_id` from the URL (or, for knowledge, an
`organization_id` query parameter) directly, with no identity or
permission check. This was a scope decision, not an oversight — retrofitting
every existing route to require authentication in the same change that
introduces the *only* authentication mechanism available (the dev-only
header) would mean every existing test starts sending a fake identity
header to keep passing, which defeats the purpose of having a real
authentication boundary at all. Instead:

* The full pipeline (`AuthorizationService`, `TenantContext`,
  `authorize_tenant_context`) is built, and is exercised for real by the
  membership endpoints and by the [Knowledge architecture](#knowledge-architecture)
  section's global-vs-organization distinction (tested directly at the
  service layer in `tests/test_global_vs_organization_knowledge_access.py`).
* Cutting the remaining routes over is a follow-up, not a partial,
  silent change here — see ["What must be implemented before
  production"](#known-gaps--next-phase).

### Provenance and safety of the platform-admin exception

`AuthorizationService.can()` and `authorize_tenant_context()` both grant
full access when `User.platform_role == PLATFORM_ADMIN`, without
requiring an `OrganizationMembership` row to exist. This is the one
documented exception to "membership required," and it is intentionally
narrow: it checks one specific, named field for one specific, named
value — not a generic "is this user special" flag, a `is_superuser`
boolean, or a bypass of the function entirely. See
`app/services/authorization_service.py`'s module docstring for the exact
reasoning, and `tests/test_authorization.py::test_platform_admin_status_is_not_a_generic_bypass`
for a test that a near-miss value (wrong case) grants nothing.

### Machine clients (architecture, not implementation)

SIE is meant to serve both human users (an HSE Manager signing in through
a browser) and machine clients (Safelytic, an external EHS/ERP system, an
IoT platform, calling the API directly) — see the milestone's own framing
of this. **Machine-client authentication (OAuth2 client credentials, API
keys) is not implemented in this milestone**, but nothing in the identity
model assumes a caller is a human: `Identity.provider` is a free-form
string (not restricted to consumer IdP names), `ExternalIdentityClaims`
has no human-specific field (no "first name", just `subject`/`issuer`/
`email`/`display_name`), and `TenantContext` is keyed on `user_id` and
`organization_id`/`role`/`permissions` — none of which presume a person
is attached. A machine client's eventual `User` row (or a distinct
principal type, if machine clients turn out to need one) would flow
through the same `OrganizationMembership` → `Role` → `Permission` →
`TenantContext` pipeline as a human user; this milestone doesn't build
that caller type, but doesn't need to change this pipeline to add it
later either.

### Compatibility concerns (the `users` table change)

Migration `0003` changes the `users` table's shape rather than only
adding new tables — see that migration's docstring for the full
before/after and why each change was made; summary:

* `organization_id` becomes nullable (was required) and its FK changes
  from `ON DELETE CASCADE` to `ON DELETE SET NULL` — it's now a
  convenience default, not an ownership relationship.
* `role` (one global role string) is dropped, replaced by
  `organization_memberships.role` (per-organization) and the new
  `users.platform_role` (the one genuinely global role).
* `email` becomes unique platform-wide (was unique per `organization_id`).

This is judged low-risk because Foundation v0.1 never shipped a
User-facing endpoint — there is no real user data anywhere that could
depend on the old shape. A codebase with real production user data at
this point would need a multi-step migration (add new columns, backfill
from the old ones, drop the old columns in a later migration) instead of
the single-step change `0003` makes.

### Audit foundation

`AuditLog` (`app/models/audit_log.py`) is a minimal, synchronous,
append-only table — not an event-streaming system — written to by
`app/services/audit_service.py::AuditService.log()`. Wired up today (see
`AuditAction` for the exact constants) to: `KNOWLEDGE_SOURCE_CREATED`,
`KNOWLEDGE_VERIFIED`, `DOCUMENT_CREATED`, `DOCUMENT_VERSION_CREATED`
(skipped on the idempotent-duplicate path — see
[Knowledge architecture](#knowledge-architecture)), `MEMBER_ADDED`,
`MEMBER_ROLE_CHANGED`, `MEMBER_STATUS_CHANGED`. Every action-generating
service method accepts an optional `actor_user_id` for attribution
(`None` where no authenticated actor is available yet, e.g. every
knowledge route today — see "Existing organization-scoped APIs" above).
`organization_id`/`user_id` on `AuditLog` are `ON DELETE SET NULL`, not
`CASCADE` like most of this schema — an audit row is a historical record
and should outlive the organization or user it refers to. Per the
security requirements this milestone was built under, no audit call
anywhere in this codebase logs a password, token, or secret — there
aren't any in this schema to log.

## Universal ingestion architecture

    INPUT
        -> File/type detection
        -> Validation
        -> Hashing
        -> Source/document association
        -> Format adapter
        -> Content extraction
        -> Structure detection
        -> Normalization
        -> Quality checks
        -> Persistence
        -> Provenance

This is how a file uploaded to `POST /api/v1/knowledge/ingestion` becomes
`KnowledgeDocument` / `KnowledgeDocumentVersion` / `KnowledgeChunk` rows.
The core architectural principle: **different input formats are
interpreted differently, not flattened into plain text.** A PDF's pages,
a spreadsheet's rows and columns, and a presentation's slides and speaker
notes are different kinds of structure, and this engine keeps them that
way all the way down to the chunk, rather than reducing every format to
an undifferentiated block of text.

### Supported formats

| Format        | Support in this milestone | Extraction approach                          | Structured data | Future |
|---------------|---------------------------|-----------------------------------------------|------------------|--------|
| PDF           | Yes (`PDFAdapter`)        | Text layer per page (`pypdf`); OCR not run     | No               | Table extraction, OCR for scanned pages |
| DOCX          | Yes (`DOCXAdapter`)       | Document-order paragraphs/headings/tables (`python-docx`) | No   | — |
| TXT           | Yes (`TXTAdapter`)        | Direct decode                                  | No               | — |
| RTF           | Yes (`RTFAdapter`)        | `striprtf` (pure Python, no shell-out)         | No               | — |
| CSV           | Yes (`CSVAdapter`)        | Delimiter/header sniffing, one record per row  | Yes              | — |
| XLSX          | Yes (`XLSXAdapter`)       | One record per row per worksheet (`openpyxl`)  | Yes              | — |
| PPTX          | Yes (`PPTXAdapter`)       | Title/text/notes/tables per slide (`python-pptx`) | Partial (tables) | — |
| DOC           | No adapter (detected only) | —                                             | —                | Adapter |
| ODT           | No adapter (detected only) | —                                             | —                | Adapter |
| XLS           | No adapter (detected only) | —                                             | —                | Adapter |
| ODS           | No adapter (detected only) | —                                             | —                | Adapter |
| PPT           | No adapter (detected only) | —                                             | —                | Adapter |
| ODP           | No adapter (detected only) | —                                             | —                | Adapter |
| JSON          | Architecture + basic parsing (`JSONAdapter`) | Validate + split a top-level record array; no schema mapping | Yes | Schema identification, canonical mapping |
| XML           | Architecture + basic parsing (`XMLAdapter`), via `defusedxml` for XXE/entity-expansion safety | Validate + one record per root child; no schema mapping | Yes | Schema identification, canonical mapping |
| HTML          | Not implemented            | —                                             | —                | Controlled web-page ingestion (not unrestricted crawling) |
| JPG/JPEG      | Detected, metadata only (`ImageAdapter`) | Dimensions/format via Pillow; no OCR | No               | OCR (`app/ingestion/ocr.py`) |
| PNG           | Detected, metadata only (`ImageAdapter`) | Same as JPG                          | No               | OCR |
| TIFF          | Detected, metadata only (`ImageAdapter`) | Same as JPG                          | No               | OCR |
| EML / MSG     | Not implemented            | —                                             | —                | Adapter |
| MP3/WAV/MP4/… | Not implemented            | —                                             | —                | Transcription |

"Detected only" means `app/ingestion/detection.py` recognizes the
extension/media type (so a future ingestion response could say "DOC
recognized but not yet supported" rather than "unknown file"), but no
`DocumentAdapter` is registered for it, so `POST /ingestion` still
rejects it with 415 today.

### Pipeline architecture

    file bytes -> detect -> validate -> hash -> extract -> normalize -> structure detection

is `app/ingestion/pipeline.py` — pure, DB-independent, directly testable
(`tests/test_ingestion_pipeline.py`) — called by
`app/services/ingestion_service.py`, which supplies the remaining stages
(source/document association, persistence, provenance) that need the
database and the caller's authorized tenant context. New processors don't
require rewriting the pipeline: a new format is one adapter module plus
one line in `app/ingestion/adapters/registry.py`'s `_DEFAULT_ADAPTERS`
tuple.

Chunking — turning that normalized, structure-detected content into
`KnowledgeChunk` rows — happens one layer further up, in
`app/services/chunking_service.py`, after a `KnowledgeDocumentVersion`
already exists. See [Knowledge Quality & Semantic Chunking
Pipeline](#knowledge-quality--semantic-chunking-pipeline) below for why
that stage needs to live there rather than in this DB-independent module,
and for everything downstream of normalization.

### Format adapter interface

Every adapter (`app/ingestion/adapters/*.py`) implements the same small
interface (`DocumentAdapter` in `adapters/base.py`):

    detect(media_type, extension) -> bool
    validate(file_bytes, filename) -> list[str]        # warnings, or raises for a hard failure
    extract(file_bytes) -> ExtractionResult             # format-specific parsing
    normalize(extraction) -> list[NormalizedContent]     # translation into the common shape

`validate`/`extract` are separate steps specifically so a format
library's own parsing failures (a corrupt PDF, a malformed workbook) are
caught and reported as a failed ingestion job rather than crashing the
request — see "Failure handling" below.

### Normalized content model

```
NormalizedContent
├── content_type        (text | table | image | structured_record)
├── text
├── title                nullable
├── page_number          nullable — PDF
├── sheet_name           nullable — XLSX
├── row_number           nullable — CSV, XLSX, JSON record arrays, XML elements
├── slide_number         nullable — PPTX
├── section_title        nullable — DOCX, PDF (best-effort)
├── section_path         nullable — the section heading breadcrumb (see the Knowledge
│                        Quality pipeline below); populated by structure detection,
│                        not by the adapters themselves
├── metadata             format-specific extras (columns/values, speaker notes, tables, ...)
└── source_reference     human-readable locator, e.g. "Sheet: Incident Register, Row 124"
```

This is not an attempt to make every format mean the same thing — a
spreadsheet row and a PDF page are different things — it's a common
*envelope* that preserves whichever location fields are meaningful for
the format that produced it. What turns a list of these into
`KnowledgeChunk` rows is the [Knowledge Quality & Semantic Chunking
Pipeline](#knowledge-quality--semantic-chunking-pipeline) below — every
location field on this envelope is carried through (directly, or into a
chunk's `metadata`) all the way to the chunk, so a chunk still says "page
47" or "Sheet: Incident Register, Row 124" no matter how it was cut.

### Storage architecture

```
StorageProvider
├── save(content_hash, extension, data) -> storage_reference
├── retrieve(storage_reference) -> bytes
├── delete(storage_reference) -> None
└── exists(storage_reference) -> bool
```

No uploaded file's bytes are ever stored in PostgreSQL — `IngestedFile`
and `KnowledgeDocumentVersion` both only carry a `storage_reference`
string. `LocalFilesystemStorageProvider`
(`app/ingestion/storage.py`) is the only implementation in this
milestone, explicitly for local development; a production S3/Azure
Blob/GCS-backed implementation is future work that satisfies the same
interface, swapped in at `get_storage_provider()` (the single call site
every other module uses) without touching any ingestion logic. Storage
keys are derived entirely from the content hash and a validated
extension (`<hash[:2]>/<hash[2:4]>/<hash><ext>`) — never from the
caller-supplied filename — which is what makes path traversal
structurally impossible rather than merely filtered: there is no code
path where an uploaded filename becomes part of a filesystem path.
`retrieve`/`delete`/`exists` additionally reject any reference that
doesn't match that exact shape, as defense in depth. `storage_reference`
is never returned by the API as a raw path — only as this opaque key.

### Provenance

    File -> Ingestion Job -> Document -> Document Version -> Normalized Content -> Chunk

(See [Knowledge Quality & Semantic Chunking
Pipeline](#knowledge-quality--semantic-chunking-pipeline) below for what
sits between "Normalized Content" and "Chunk" — structure detection,
Knowledge Units, and the chunking strategy itself — and for how each
chunk carries this full chain back down to a concrete page/section/
slide/row, not just a document-level reference.)

`IngestedFile` and `IngestionJob` mirror the KnowledgeDocument/
KnowledgeDocumentVersion current-state/history split already used
elsewhere in this schema: a file's own status reflects its most recent
job, while every job (one per ingestion attempt) is an immutable record —
uploading the same content twice creates two files and two jobs, both
individually traceable, even though (per the Knowledge Foundation's
existing idempotency, reused unchanged here) they resolve to the same
`KnowledgeDocumentVersion`. `IngestionJob` has no `document_version_id`
column of its own (see that model's docstring) — `app/services/knowledge_provenance_service.py::get_ingestion_provenance`
recovers it by joining the job's file's `content_hash` against
`KnowledgeDocumentVersion.content_hash` within the job's own
`document_id`, extending the same "no new event table" principle
`get_chunk_provenance` (Knowledge Foundation) already used.

### Failure handling ("fail safely")

A file whose *type* isn't supported is rejected with 415 before anything
is written to the database. A file whose type *is* supported but whose
content is malformed (a corrupt PDF, an unparseable workbook) still
creates a queryable `IngestedFile` and `IngestionJob` — the job's status
is `FAILED`, `error_message` names what went wrong, and the API still
returns 201 (the request was valid; the *content* couldn't be processed).
Neither case ever "succeeds" silently: a PDF whose pages contain no
extractable text is recorded as `ExtractionStatus.PARTIAL` with a warning
naming exactly how many pages ("PDF text extraction completed with 3
pages containing no extractable text"), not returned as if it worked
cleanly. `extraction_method` (`TEXT_EXTRACTION` / `STRUCTURED_PARSE` /
`OCR` / `NONE`) and `extraction_status` (`PENDING` / `SUCCEEDED` /
`PARTIAL` / `FAILED`) together are what a future evidence-quality feature
reads to know how much to trust a given chunk.

### Future OCR

```
Input -> OCR detection -> OCR provider -> Extracted text -> Normalized content
```

`OCRProvider` (`app/ingestion/ocr.py`) is an interface with **no
implementation** — no commercial OCR is wired up in this milestone, per
spec. `ImageAdapter` (JPG/PNG/TIFF) validates real images and extracts
genuine metadata (dimensions, format) via Pillow, but never produces
text — recorded as `extraction_method = NONE` today; a PDF whose pages
have no text layer is
likewise not OCR'd, staying `TEXT_EXTRACTION` (the method that genuinely
was attempted) with a warning instead. `is_ocr_available()` always
returns False until a real provider is registered — nothing pretends
otherwise.

### Future background processing

The ingestion service call (`IngestionService.ingest()`) is fully
synchronous — no Redis/Celery/Kafka, per spec. Nothing about the
architecture assumes that, though: `IngestionJob`'s state machine
(`RECEIVED` → `VALIDATING` → `PROCESSING` → `COMPLETED`/`FAILED`/
`CANCELLED`) already models an asynchronous job's lifecycle, so moving to
a background worker later means the worker driving that same state
machine over time instead of one function doing it inline — not a schema
or API contract change.

### Tenant isolation and authorization

`POST /api/v1/knowledge/ingestion` reuses the Identity & Access
Foundation's authorization exactly as built, with no new mechanism (see
[Identity architecture](#identity-architecture)):

* `organization_id` provided (organization knowledge) — the caller must
  have an ACTIVE membership in that organization whose role grants
  `knowledge:manage` (`authorization_service.can()`, unchanged).
* `organization_id` omitted (global knowledge) — `can()` with no
  organization only ever succeeds for a `PLATFORM_ADMIN`. Omitting the
  field is explicitly *not* a lower-privilege path to global knowledge —
  see the milestone's own instruction that this must not be possible.

`organization_id` is never trusted as proof of ownership on its own —
whether a request is even attempted against it depends on this
authorization check succeeding first (in `app/api/v1/ingestion.py`,
before `ingestion_service.ingest()` is even called), and once inside the
service, an existing `document_id` is still re-resolved tenant-scoped
(`knowledge_document_service.get(..., organization_id=...)`, returning
`None` — surfaced as 404 — for a document in a different organization)
and a new document's source/organization consistency still goes through
the Knowledge Foundation's own unchanged check. This route does not have
a `{organization_id}` URL segment the way the membership endpoints do (a
file can target GLOBAL knowledge, which has no organization at all), so
it calls `authorization_service.can()` directly rather than the
path-based `require_permission` dependency used elsewhere — see
`app/api/v1/ingestion.py`'s module docstring.

## Knowledge Quality & Semantic Chunking Pipeline

    Ingested File -> Ingestion Job -> Knowledge Document -> Document Version
        -> Normalized Content -> Structure Detection -> Knowledge Units
        -> Semantic Chunking -> Knowledge Chunks -> Provenance

This is the stage between [Universal ingestion
architecture](#universal-ingestion-architecture)'s normalized content and
a citable `KnowledgeChunk` row. **It is explicitly not the embeddings /
vector search / RAG layer** — no embedding is computed, no vector column
exists, nothing here is aware that a future retrieval step will exist.
The objective is narrower and structural: turn extracted content into
well-structured, well-attributed, quality-assessed units suitable for
that future layer to build on, without building it.

### Why chunking needs the database, and why it isn't in `pipeline.py`

`app/ingestion/pipeline.py` is deliberately pure and DB-independent (see
above) — but a chunk needs a real `document_id`/`source_id`/
`organization_id` and an idempotency check against an already-created
`KnowledgeDocumentVersion`, neither of which exist yet at that layer.
`app/services/chunking_service.py` is the one place `KnowledgeUnit`s are
built and `StructureAwareChunkingStrategy` is invoked, called only from
`app/services/ingestion_service.py` after the version row exists. It
knows nothing about LLMs, embeddings, or vector databases — those
concerns don't appear anywhere in this call chain.

### Why `KnowledgeUnit` is in-memory, not a table

`app/ingestion/knowledge_unit.py::KnowledgeUnit` is the milestone's
"conceptual intermediate representation" between normalized content and a
chunk — but it is a plain dataclass, never persisted. It has no
independent lifecycle (nothing ever queries "the knowledge units for this
version" as a stable resource the way it queries chunks or documents); a
persisted version would duplicate most of `KnowledgeChunk`'s own columns
for no benefit; and it's a natural continuation of a pattern already used
one stage earlier (`NormalizedContent` itself is an in-memory Pydantic
model, not a table). If a future debugging/QA view ever needs to inspect
pre-chunking structure, `KnowledgeDocumentVersion.extracted_text` and the
original stored file already retain enough to reconstruct it.

### Why different content types need different chunking strategies

A PDF/DOCX/TXT/RTF page is prose: paragraphs that can be packed together
up to a target size, split at sentence boundaries only when one paragraph
alone is too large, with a small amount of trailing-text overlap across a
split so neither half loses context. A PPTX slide is conceptually
discrete — "Slide 17" must always mean exactly slide 17's own chunk(s),
never a blend of slide 16 and 17's text, even though both are short plain
text — so slides are never merged across their boundary
(`KnowledgeUnit.is_atomic`). A spreadsheet row (XLSX/CSV) is a structured
record, not prose: `StructureAwareChunkingStrategy` never concatenates an
entire sheet into one blob of text and chunks that blob — each row keeps
its own `sheet_name`/`row_number`/`source_reference`, and if a single row
is too large it splits on field boundaries (never mid-value) while every
fragment still carries the same row identity
(`row_part`/`row_part_count` in `chunk_metadata`). A table (e.g. a DOCX
table) is preserved as a row-structured block — `"Equipment | Inspection
Interval"`, not flattened into a sentence — and if its own extraction was
incomplete, that is recorded as a quality warning rather than silently
presented as complete. An image with no OCR result is still a real,
citable chunk (empty content, `INSUFFICIENT` quality, `no_ocr_text_available`)
— never a fabricated description of content nobody actually read. Only
`StructureAwareChunkingStrategy` is implemented this milestone; future
strategies named but intentionally not built: `SemanticChunkingStrategy`,
`TableAwareChunkingStrategy`, `LegalDocumentChunkingStrategy`,
`SafetyProcedureChunkingStrategy` — all would implement the same
`ChunkingStrategy` interface (`app/ingestion/chunking.py`), so
`chunking_service.py` never needs to change to add one.

### Why spreadsheet rows never get prose-style overlap

Overlap (repeating a small tail of one chunk's text at the start of the
next) helps prose recover context lost at a mid-paragraph cut. Applying
that to structured records would literally duplicate row data — two
chunks would each claim to (partially) contain the same incident record,
which is never correct. `StructureAwareChunkingStrategy` applies overlap
only within a run of prose text units; structured-record and table
splitting use exact field/row boundaries and zero overlap, always
(`tests/test_chunking_structure.py::test_structured_records_are_never_duplicated_for_overlap`).

### Section hierarchy detection

`app/ingestion/structure.py::detect_structure` walks a document's
normalized content maintaining a heading stack, and builds a
`section_path` breadcrumb from it — the milestone's own example: a
`"Fall Protection"` chunk under `"Working at Height"` gets
`section_title="Fall Protection"`,
`section_path=["Working at Height", "Fall Protection"]`. This only works
where an adapter actually signals heading level (currently DOCX, via
Word's built-in Heading styles); formats with only a weaker signal (a
PDF's first line of a page, currently used as a low-confidence guess) get
a single-element path and `structure_confidence: "low"`; formats with no
heading signal at all (CSV, XLSX, images) get `structure_confidence:
"none"`. **No format's structure is guessed beyond what its adapter can
actually support** — a low-confidence guess is recorded as low-confidence
metadata, never presented as a confident hierarchy.

### Configurable chunk sizing

`MIN_CHUNK_CHARACTERS` (200), `TARGET_CHUNK_CHARACTERS` (1000),
`MAX_CHUNK_CHARACTERS` (1800), `OVERLAP_CHARACTERS` (150) —
`app/core/config.py`, read through `ChunkingSettings.from_app_settings()`
(`app/ingestion/chunking.py`). **These are documented initial defaults,
not scientifically validated optimal values** — character-based, not
token-based, since no tokenizer dependency is introduced by this
milestone (a future embedding layer would introduce one matched to its
own model). Priority order when packing content into a chunk: headings
staying attached to the content they introduce > section boundaries >
paragraph boundaries > list cohesion > tables/structured records as
atomic blocks > only then a character-limit split — never blindly every
N characters, and never mid-sentence unless a single unit alone exceeds
the limit.

### Deterministic, reproducible generation

Same normalized content + same `ChunkingSettings` → the same chunk
sequence, every time (`tests/test_chunking_structure.py::test_chunking_is_deterministic_for_the_same_input_and_settings`).
Nothing in the strategy is random, time-dependent, or model-based.
`app/services/chunking_service.py::generate_chunks` is additionally
idempotent at the persistence layer: a `KnowledgeDocumentVersion` that
already has chunks is returned as-is rather than re-chunked (reusing the
Knowledge Foundation's existing `content_hash`-based version
deduplication — reprocessing the same file never creates a duplicate
version *or* duplicate chunks). This determinism is what makes future
evidence reproducible: a citation captured today against a given version
will still resolve to the same chunk text if that version is ever
re-chunked (e.g. after a bug fix), since a version that already has
chunks is never silently regenerated — a real change in chunking logic
would need its own explicit re-chunking path, not implemented here.

### Quality assessment — extraction/structure quality, not truth

`app/ingestion/quality.py` computes a deterministic `QualityStatus`
(`HIGH`/`MEDIUM`/`LOW`/`INSUFFICIENT`) from simple, explainable signals:
text length, whether structural metadata (page/section/sheet/slide) was
available, whether OCR was needed but never ran, whether extraction was
only partial, whether a table's extraction was flagged incomplete, and
whether content came back suspiciously empty. **This is an extraction/
structure quality indicator — it says nothing about whether the
underlying safety information is true, correct, or complete, and it is
never called a "truth score" anywhere in this codebase.** Two distinct
assessment functions exist on purpose: `assess_unit_quality` scores one
piece of content standalone (useful in its own right — e.g. spotting
which source pages extracted poorly); `assess_merged_quality` is what a
final chunk's quality is actually computed from, re-running the same
checks against the chunk's *real* final text once several units have
been packed together, rather than blindly unioning each ingredient's own
pre-merge assessment (which would otherwise mislabel a perfectly good
combined chunk as low-quality just because one short fragment that went
into it was).

### Source authority, verification status, and extraction quality are three separate things

The milestone's own worked example, and a hard rule throughout this
codebase: **a highly authoritative, `VERIFIED` regulation can still have
`LOW` extraction quality** if it was ingested from a scanned PDF with no
text layer; a low-authority internal note can have `HIGH` extraction
quality if it came from a clean DOCX. These are never combined into one
score:

* **Source authority** (`KnowledgeSource.authority_level`) — set by a
  human when the source is registered; how authoritative the *publisher*
  is, independent of how any particular file happened to parse.
* **Verification status** (`KnowledgeSource.verification_status`) — SIE's
  own governance workflow state. **Ingestion and chunking never touch
  this field.** A newly ingested source is never auto-marked `VERIFIED`
  just because it chunked successfully, and chunking a source that is
  already `VERIFIED` never changes that status either
  (`tests/test_chunking_quality_and_scope.py::test_ingestion_never_changes_source_verification_status`,
  `::test_ingestion_never_marks_a_source_verified`).
* **Extraction/structure quality** (`KnowledgeChunk.quality_status`, from
  `app/ingestion/quality.py` above) — this milestone's own concern, and
  the only one of the three chunking ever computes or writes.

### Chunk shape, tenant scope, and provenance

`KnowledgeChunk` (`app/models/knowledge_chunk.py`) carries: denormalized
`document_id`/`source_id`/`organization_id` (same precedent as
`KnowledgeDocument.organization_id` — copied at write time so a chunk can
be tenant-filtered and looked up directly, without joining back through
its version and document on every query — never an independent source of
truth); `content_type`, `page_number`/`sheet_name`/`row_number`/
`slide_number`, `section_title`/`section_path`, `source_reference`,
`extraction_method`, and `quality_status` as real, indexable columns
(promoted out of free-form JSON specifically so a future retrieval filter
can query on them directly); and `chunk_metadata` (JSON) for
`quality_reasons`, table/row split-part numbering, and a
**point-in-time snapshot** of fields still owned elsewhere
(`language` from the document, `jurisdiction`/`industry_sector`/
`authority_level`/`verification_status` from the source,
`publication_date`/`effective_date` from the version) — recorded once at
chunk-creation time rather than copied as live columns, because copying
them as real columns would mean every existing chunk going stale (or
needing a bulk-update fan-out this milestone has no background-worker
infrastructure to run) the moment a source's metadata changes later; the
owning table's live value is always still queryable directly.
`organization_id` follows the source's own GLOBAL/ORGANIZATION scope all
the way down — a GLOBAL source's chunks always have `organization_id =
NULL`, an ORGANIZATION source's chunks always carry that organization's
id, and cross-organization access to another organization's chunks is
structurally impossible via the one read endpoint (see below).

Concrete `source_reference` examples per format, exactly as the milestone
specifies: `"Page 1"` (PDF), a `section_path` breadcrumb (DOCX),
`"Slide 1"` (PPTX), `"Sheet: Incident Register, Row 2"` (XLSX),
`"Row 2"` (CSV) — see
`tests/test_chunk_provenance_multiformat.py` for the full per-format
assertions, and `app/services/knowledge_provenance_service.py::get_chunk_provenance`
for how a chunk's id resolves the complete
`Chunk -> Document Version -> Document -> Source` chain (extending
unchanged to `Ingested File -> Ingestion Job` via
`get_ingestion_provenance`, as already documented above). Versioning is
untouched by this milestone: old chunks stay with their old
`KnowledgeDocumentVersion`, a new version's chunks are new rows entirely,
and nothing ever overwrites a historical chunk.

### The one read endpoint, and why there's no write endpoint

`GET /api/v1/knowledge/documents/{document_id}/versions/{version_id}/chunks`
is the only chunk-related API route. There is no create/update/delete
route for chunks anywhere: **chunk generation is controlled by ingestion
processing only** (`chunking_service.generate_chunks`, called from
`ingestion_service`), never by a direct client request. The read endpoint
was added rather than kept service-only because it costs no new
authorization mechanism: it reuses exactly the same tenant check every
sibling knowledge read route in `app/api/v1/knowledge.py` already uses —
`get_knowledge_document_or_404` requires the caller to already know the
document's own `organization_id` (or omit it for a GLOBAL document) to
resolve the document at all, so a chunk can never be reached via the
wrong organization; `get_for_document` applies that same containment one
level further, so a `version_id` that exists but doesn't belong to the
resolved document 404s rather than leaking a different document's chunks
(`tests/test_knowledge_chunks_api.py`).

### Future compatibility, deliberately not built yet

Every chunk carries the fields a future retrieval layer will need to
filter by — organization/scope (`organization_id`), source
(`source_id`), document/version (`document_id`/`document_version_id`),
content type, page/section/sheet/slide/row, industry/jurisdiction
(in the metadata snapshot), verification status (same), and date
(`publication_date`/`effective_date`, same) — without any of that
retrieval layer existing. **No embedding is computed. No vector column
exists on `KnowledgeChunk` or anywhere else. No pgvector extension is
enabled. No semantic/similarity search, no RAG, and no LLM integration
exist in this codebase.** Attaching an embedding to a chunk later is
additive — a new nullable column/table referencing `KnowledgeChunk.id` —
not a redesign of anything built in this milestone.

*(As of the Semantic Knowledge Engine v0.1 milestone below, this is no
longer fully true: pgvector is enabled and semantic similarity search
does exist — see [Semantic Knowledge
Architecture](#semantic-knowledge-architecture). RAG and LLM integration
still do not.)*

## Semantic Knowledge Architecture

    KnowledgeChunk -> EmbeddingService -> EmbeddingProvider -> Vector
        -> KnowledgeChunkEmbedding (pgvector storage)
        -> RetrievalService -> Metadata filter -> Vector similarity
        -> Ranked RetrievalResult -> Provenance

This is the Semantic Knowledge Engine v0.1 milestone: it proves SIE can
retrieve semantically relevant knowledge chunks reliably, with tenant
isolation and full provenance, **before any LLM/RAG reasoning layer is
introduced.** No LLM, no RAG, no prompt engineering, no answer
generation, and no reranking model exist anywhere in this codebase — see
["What this deliberately does not do"](#future-architecture-not-built-here)
below. `RetrievalService` returns evidence; nothing downstream of it
exists yet to turn that evidence into a generated answer.

### Why embeddings live in their own package, not inside chunking

`app/embeddings/` and `app/retrieval/` are new top-level packages, not
additions to `app/ingestion/`. Chunking (the previous milestone) produces
`KnowledgeChunk` rows without knowing embeddings will ever exist;
embedding a chunk happens afterward, against an already-persisted chunk,
and is itself invisible to chunking. This mirrors the same layering
`app/ingestion/chunking.py` and `app/services/chunking_service.py`
already establish one level down: a pure transformation stage
(`EmbeddingProvider`, analogous to `ChunkingStrategy`) and a DB-facing
orchestration stage (`EmbeddingService`, analogous to `ChunkingService`)
that gives that transformation real identity, idempotency, and
persistence.

### Embedding provider abstraction

`app/embeddings/provider.py::EmbeddingProvider` is a `Protocol`
(`embed_text`/`embed_texts`, plus `provider_name`/`model_name`/
`model_version`/`dimensions`) — nothing above it depends on a concrete
implementation. **`HashingEmbeddingProvider`, a deterministic,
dependency-free feature-hashing embedding (the same "hashing trick"
technique behind scikit-learn's `HashingVectorizer`), is the only
provider actually exercised anywhere in this milestone** — in
development, in the test suite, and in the evaluation harness alike. It
is a real, working implementation, not a mock: lowercase, tokenize, drop
a small generic/procedural stopword list, hash each surviving token into
a signed bucket, weight by sublinear term frequency, sum, and
L2-normalize. Two texts sharing vocabulary land closer together under
cosine similarity than two that don't — genuine, explainable signal, just
not a trained semantic representation, and never presented as one.

This choice follows the milestone spec directly: *"If a model dependency
would make the test suite unreliable or require downloading large model
weights, create a deterministic test provider and a production-provider
abstraction."* `SentenceTransformerEmbeddingProvider` is that production
extension point — implemented, lazy-importing its optional dependency so
this module stays importable without it — but it was **not exercised
against a real downloaded model in this environment**, and is not the
default. No commercial AI provider is hardcoded into the domain layer
anywhere; `EMBEDDING_PROVIDER` (`app/core/config.py`) is a plain setting
resolved once, at the edge, by `get_embedding_provider()`.

### Embedding model/version tracking — why re-embedding never overwrites

`KnowledgeChunkEmbedding` (`app/models/embedding.py`) is one row per
`(knowledge_chunk_id, provider, model_name, model_version)` — not one row
per chunk:

    Chunk A
    ├── Embedding(provider=hashing, model=sie-hashing-embedder, version=v1)
    └── Embedding(provider=sentence_transformers, model=all-MiniLM-L6-v2, version=1)

Changing embedding models over time must never silently invalidate
existing vectors: re-embedding a chunk under a *different* model identity
creates a new row, never touches the old one, and
`RetrievalService` always searches within one pinned model identity —
vectors from different models are never compared in the same ranking
(mixing vector spaces from different models would be numerically
meaningless, not just architecturally sloppy). Re-embedding the *same*
chunk under the *same* model identity is idempotent instead: `content_hash`
(the same SHA-256 content-addressing already used for
`KnowledgeDocumentVersion`/`IngestedFile`) detects whether the existing
row already reflects the chunk's current content, and — since a chunk's
content is expected to be immutable — a hash mismatch is reported
(`SKIPPED_STALE_CONTENT_HASH`) rather than silently overwritten; only an
explicit `force=True` updates the existing row in place.

`app/core/config.py`'s `EMBEDDING_DIMENSIONS` is the single central
source of truth for the pgvector column's width — both
`app/models/embedding.py`'s `Vector(...)` column and
`migrations/versions/0006_semantic_embeddings.py` read this one value;
neither hardcodes a dimension of its own. Changing it requires a new
migration (a pgvector column's dimension is fixed at creation time) and
re-embedding every chunk under a new `EMBEDDING_MODEL_VERSION`.

### Embedding generation — what gets skipped, and why

`app/embeddings/embedding_service.py::EmbeddingService.embed_chunk`
never embeds a chunk with empty content (a zero vector would claim
meaning that was never there), and never embeds an `INSUFFICIENT`-quality
chunk unless explicitly configured
(`EMBED_INSUFFICIENT_QUALITY_CHUNKS=true`) or the caller passes
`force=True` — the same "do not pretend content was understood"
principle the previous milestone's quality assessment already
established, extended to embeddings. It never modifies the source
chunk's own text. A provider failure is caught and reported as a typed
outcome (`FAILED`, with a reason), never raised and never silently
swallowed. `generate_embeddings_for_version(version_id)` batches this
over every chunk in one version, is safe to re-run (already-embedded
chunks are skipped, not duplicated), and collects per-chunk failures into
one report rather than aborting the whole batch on the first bad chunk.

### Tenant isolation — enforced explicitly, never by vector similarity alone

This is non-negotiable, and enforced the same way tenant isolation is
enforced everywhere else in this codebase: an **explicit SQL predicate**,
not an assumption that semantically-unrelated content from another
organization simply won't rank highly enough to matter.
`KnowledgeChunkEmbedding.organization_id` is denormalized from the
embedded chunk at write time (the same "copy tenant identity onto the
child row" precedent as `KnowledgeChunk.organization_id` itself), and
`RetrievalService._tenant_clause()` is the one place that predicate is
built — always applied, never optional, always evaluated *before* the
vector `ORDER BY`/`LIMIT`, not as a post-filter over results that could
already have crossed a tenant boundary:

* `allowed_organization_id=None` -> `organization_id IS NULL` only
  (GLOBAL knowledge).
* `allowed_organization_id=<uuid>` -> `organization_id IS NULL OR
  organization_id = <uuid>` (GLOBAL **plus** that one authorized
  organization — never more than one organization's private knowledge in
  a single search).

`allowed_organization_id` is never request input taken at face value.
`app/api/v1/retrieval.py` resolves and authorizes it *before*
`RetrievalService.search()` is ever called — the same
"resolve-then-authorize-then-pass-a-trusted-value" shape
`ChunkingService`/`IngestionService` already use — so a client cannot
reach another organization's knowledge by simply naming its
`organization_id` in the request body. See [Tenant isolation
(reused, not reinvented)](#tenant-isolation-reused-not-reinvented) above
for why this principle already runs through every other layer of this
codebase; retrieval is one more enforcement point for it, not a new
mechanism.

### Global vs. authorized-organization knowledge

A search's authorized scope always follows the same table as Ingestion's
own authorization (`app/api/v1/ingestion.py`), with one deliberate,
documented difference for *reads*:

* `filters.organization_id` provided -> `authorization_service.can(...,
  permission=KNOWLEDGE_READ, organization_id=...)` — an ACTIVE membership
  granting `knowledge:read` in that organization is required, or 403.
* `filters.organization_id` omitted -> GLOBAL-only search. Every request
  must still be authenticated (unlike the sibling read routes in
  `app/api/v1/knowledge.py` today — a known gap, see below), but no
  organization-membership check applies. This deliberately departs from
  `authorization_service.can()`'s own stricter "no organization_id ->
  only a `PLATFORM_ADMIN` succeeds" rule, which that module's own
  docstring already states is tuned for *global-knowledge reads never
  being routed through it at all* — that rule exists for the
  meaningfully more privileged act of *writing* new GLOBAL knowledge, not
  for reading already-published GLOBAL knowledge that a legitimate
  platform user should be able to search.

### Similarity score vs. confidence

`RetrievalResult.similarity` is a cosine-similarity score (pgvector's
`<=>` cosine-distance operator, converted as `1 - distance` — see
"Similarity method" below) — a measure of vector closeness between the
query and a chunk, nothing more. **It is never called "confidence"
anywhere in this codebase** — a high similarity score says the query and
the chunk share a lot of vector space; it says nothing about whether the
chunk's content is true, current, or authoritative (those are
`verification_status` and `source_authority_level`, carried on every
result unchanged from the previous milestone's own three-way
separation). `RelevanceLevel` (`HIGH`/`MODERATE`/`LOW`) is a
human-readable bucket over that same score, for the same reason — a
label, not a probability or a truth judgment.

### Similarity method

Cosine similarity (`.cosine_distance()`, pgvector's `<=>` operator) —
the standard choice for normalized text embeddings, and what
`HashingEmbeddingProvider`'s own L2-normalized output is designed for. L2
(Euclidean) distance and inner product are both supported by pgvector but
not used here: inner product is only meaningful for unnormalized vectors
optimized for magnitude (not the case here), and L2 distance on
normalized vectors is a monotonic transform of cosine distance anyway —
cosine keeps the score in an intuitive, bounded `[-1, 1]` range
regardless of the embedding provider swapped in later. A future
`SentenceTransformerEmbeddingProvider` (or any other real model) should
keep using cosine unless that specific model's own documentation
recommends otherwise.

### Retrieval threshold — why `top_k` never means "always return k results"

`RETRIEVAL_MIN_SIMILARITY` (default `0.12`) is a floor a result must
clear to be returned *at all* — asking for `top_k=5` does not mean five
results are always returned; it means at most five, only among whatever
actually clears the bar. If nothing does, the response's `outcome` is
`NO_RELEVANT_EVIDENCE` — a first-class, explicit response shape
(`app/retrieval/results.py::RetrievalOutcome`), not an empty list a
caller has to interpret the meaning of on their own, and not a set of
weak, barely-related matches dressed up as if they were useful evidence.
`RETRIEVAL_MODERATE_SIMILARITY` (`0.20`) and `RETRIEVAL_HIGH_SIMILARITY`
(`0.30`) are the `RelevanceLevel` bucket boundaries above that floor.

**All three are documented *initial* defaults, calibrated empirically
against `HashingEmbeddingProvider`'s own score distribution** (see
`tests/test_embedding_provider.py` and the calibration data in this
milestone's final report) — unrelated text scores ~0.0 under this
provider, genuine topical matches typically score ~0.14-0.45. A
different embedding provider produces a differently-shaped score
distribution and would need its own recalibration of all three values —
the same "not scientifically validated optimal values" spirit already
established for the chunking size defaults.

### Provenance

Every `RetrievalResult` carries the full chain this codebase has
maintained since the Knowledge Foundation milestone — source authority,
verification status, extraction quality, document version, page/sheet/
row/slide, section, organization scope, and a human-readable
`source_reference`-derived `location` (e.g. `"Page 47, Section 6.2"`,
`"Slide 17"`, `"Sheet: Incident Register, Row 124"`) — nothing is
discarded on the way through embedding or retrieval. A citation built
from a `RetrievalResult` can point at exactly the passage it came from,
the same guarantee `KnowledgeChunk` itself already made one milestone
earlier.

### API

`POST /api/v1/knowledge/retrieval/search` is the **only** retrieval
route, and the only chunk-adjacent write path remains ingestion — there
is no endpoint to create, update, or delete an embedding or a chunk
directly. Raw embedding vectors are never included in the response (only
the named model identity: `provider`/`model_name`/`model_version`); no
storage path, secret, API key, or provider credential is ever exposed.
See `app/schemas/retrieval.py` for the exact request/response shape.

### Security and observability

Embedding generation only ever operates on a `KnowledgeChunk` the caller
already resolved and was authorized to process — `EmbeddingService`
performs no tenant authorization of its own, the same "caller
authorizes, service trusts what it's given" contract as
`ChunkingService`. Retrieval's tenant check happens before the service is
even called (see above). Neither layer ever logs a raw embedding vector,
a chunk's full content, a storage path, a secret, an API key, or a
provider credential. `app/embeddings/embedding_service.py` logs each
embedding failure (chunk id, model identity, error type/message — never
chunk content) and each batch's summary counts; `app/retrieval/retrieval_service.py`
logs each search request's organization scope, query *length*, result
count, outcome, embedding model identity, and duration — the query
*text* itself only if `LOG_RETRIEVAL_QUERY_TEXT` is explicitly turned on
for development, since a query may contain an organization's sensitive
operational detail.

### Evaluation methodology — "Prototype retrieval evaluation"

`tests/fixtures/evaluation/` is a small, synthetic, non-confidential
safety-knowledge corpus (28 chunks across six topics: working at height,
lifting operations, permit to work, PPE, confined spaces, emergency
response) and a 12-query set (two natural-language queries per topic).
`tests/evaluation/harness.py` loads that corpus through the *actual*
production `KnowledgeChunkService`/`EmbeddingService` code path (not a
separate mock pipeline), runs every query through the real
`RetrievalService`, and calculates Recall@1/3/5 — whether a chunk from
the query's expected topic appears within the top-K results.

**This is explicitly labeled a "Prototype retrieval evaluation" every
place it is surfaced (code, tests, this README, the final report) and is
never claimed as a production or enterprise accuracy figure.** Its
purpose is to catch regressions on this one small fixture, nothing more.
The one real, honestly-calculated result on this fixture, using
`HashingEmbeddingProvider`: **Recall@1 = 0.83, Recall@3 = 1.00,
Recall@5 = 1.00** (10 of 12 queries found their expected topic at rank 1;
all 12 found it within the top 3). This says nothing about how any real
embedding model would perform on real organizational content — it says
only that this milestone's retrieval pipeline, end to end, correctly
surfaces topically relevant evidence on this fixture.

### Production architecture consideration — synchronous today, a queue later

`EmbeddingService`/`RetrievalService` both run synchronously in the
request, exactly like `IngestionService` before them — no Redis, Celery,
Kafka, or background worker exists in this milestone, per spec. Nothing
about the architecture assumes that stays true: a future evolution is

    Ingestion -> Queue -> Embedding Worker -> Vector Store

with `EmbeddingService.generate_embeddings_for_version` becoming what a
worker calls repeatedly instead of what a request calls once — the same
kind of change `IngestionJob`'s own state machine was already built to
absorb without an API or schema break.

### Indexing decision — no ANN vector index yet

`migrations/versions/0006_semantic_embeddings.py` enables pgvector and
creates `knowledge_chunk_embeddings` with **no** IVFFlat/HNSW
approximate-nearest-neighbor index — pgvector's exact sequential scan via
`<=>` is both fast enough and exact at this milestone's dataset size (a
few dozen rows in the evaluation fixture; a real deployment's current
scale is not meaningfully larger yet), and an approximate index chosen
without a real dataset size to tune against (IVFFlat's `lists`, HNSW's
`m`/`ef_construction`) would only ever cost recall, never help. Adding
one, correctly tuned to an actual dataset size, is future work — see
"What should be built next" in the final report.

### Future architecture, not built here

    Semantic Retrieval (this milestone)
        -> Hybrid Retrieval (keyword search + vector search -> fusion)
        -> Reranking
        -> Evidence Selection
        -> RAG
        -> LLM Reasoning

`RetrievalService` is deliberately shaped so this evolution is additive:
it already returns a ranked `RetrievalResponse`; adding a keyword-search
branch and a fusion step ahead of the final ranking does not require
changing its public contract. **None of the above exists in this
codebase.** No BM25/keyword search, no Elasticsearch/OpenSearch or any
other additional search engine, no reranking model, no RAG, no prompt
engineering, no answer generation, and no LLM integration — this
milestone stops at ranked evidence with provenance, on purpose.

## Configuration

All configuration is environment-based (`app/core/config.py`, backed by
Pydantic Settings and a local `.env` file — see `.env.example`). No
secrets are committed; `.env` is git-ignored. `DEV_MODE` (default
`false`) is the one identity-related setting — see
[Identity architecture](#identity-architecture) above. `MIN_CHUNK_CHARACTERS`
(200) / `TARGET_CHUNK_CHARACTERS` (1000) / `MAX_CHUNK_CHARACTERS` (1800) /
`OVERLAP_CHARACTERS` (150) configure chunk sizing — documented initial
defaults, not scientifically validated ones; see [Knowledge Quality &
Semantic Chunking Pipeline](#knowledge-quality--semantic-chunking-pipeline)
above. `EMBEDDING_PROVIDER` (`hashing`) / `EMBEDDING_MODEL_NAME` /
`EMBEDDING_MODEL_VERSION` / `EMBEDDING_DIMENSIONS` (256, the one central
pgvector column-width value) / `EMBED_INSUFFICIENT_QUALITY_CHUNKS`
(`false`) and `RETRIEVAL_DEFAULT_TOP_K` (5) / `RETRIEVAL_MAX_TOP_K` (50) /
`RETRIEVAL_MIN_SIMILARITY` (0.12) / `RETRIEVAL_MODERATE_SIMILARITY`
(0.20) / `RETRIEVAL_HIGH_SIMILARITY` (0.30) configure embeddings and
retrieval — see [Semantic Knowledge
Architecture](#semantic-knowledge-architecture) above for what each
controls and how the retrieval thresholds were calibrated.
`LOG_RETRIEVAL_QUERY_TEXT` (`false`) gates whether a search's raw query
text is ever written to logs (query length and an embedding-model
identity are always logged; the query content itself is not, by
default — see that section's "Observability" note).

## Deliberate scope boundaries (v0.1)

To keep each foundation phase clean and reviewable, the following are
intentionally **not** included yet: real OIDC/OAuth2 token verification, a
commercial identity provider dependency, machine-client authentication
(API keys, OAuth client credentials), the AI/LLM layer, RAG, prompt
engineering, answer generation, a reranking model, predictive models,
machine learning, Safelytic integration, Redis, Celery, Kafka,
Kubernetes, production (S3/Azure/GCS) object storage, commercial OCR,
transcription, unrestricted web crawling, and automatic external-source
trust. See [Identity architecture](#identity-architecture) for what *is*
built towards authentication/authorization, and the "Deliberately does
not implement" list the Identity & Access Foundation milestone itself set
(no password auth, no stored passwords, no API keys, no OAuth client
credentials, no SSO config UI, no MFA, no password reset, no email
invitations) — all of that is still true of this codebase. Similarly, see
[Universal ingestion architecture](#universal-ingestion-architecture) for
what the ingestion engine does and does not implement (real OCR
execution, semantic chunking, and a JSON/XML schema-mapping layer are
architected for but not built). **As of the Semantic Knowledge Engine
v0.1 milestone, embeddings, pgvector, and semantic similarity search
*are* implemented** — see [Semantic Knowledge
Architecture](#semantic-knowledge-architecture) for the full design and
its own explicit statement that hybrid/keyword retrieval, reranking,
RAG, and LLM reasoning are still not implemented, and remain future work
layered on top of the ranked-evidence-with-provenance this milestone
delivers.

## Known gaps / next phase

* **`alembic upgrade head` fails on a fresh PostgreSQL database, at
  migration 0005, before ever reaching migration 0006.** Discovered in
  this milestone while integrating a real PostgreSQL + pgvector server
  for the first time in this project's history (previously, migration
  0005 had only been dialect-tested via SQLite and an offline `--sql`
  dry run against PostgreSQL — neither can catch this). Root cause,
  confirmed live: `0005`'s `batch_alter_table.add_column()` calls add two
  new PostgreSQL enum-typed columns to the already-existing
  `knowledge_chunks` table; on real PostgreSQL, Alembic's `add_column`
  (batched or not) does not auto-create the enum type the column
  references — only `op.create_table()` does that. Every earlier native
  enum column was introduced via `create_table`, which is why this had
  never surfaced before. The fix is a small, well-understood change
  *inside* migration 0005 itself (creating the two enum types with
  `sa.Enum(...).create(op.get_bind(), checkfirst=True)` before the
  `add_column` calls that reference them) — deliberately **not** applied
  by this milestone, per its explicit instruction not to modify
  migrations 0001-0005. Migration 0006 (pgvector) was still verified for
  real against a live local PostgreSQL 16 + pgvector 0.6.0 server, by
  pre-creating those two enum types out-of-band before running `alembic
  upgrade head` (not by editing 0005's file) — see
  `migrations/versions/0006_semantic_embeddings.py`'s own docstring and
  the Semantic Knowledge Engine milestone's final report for the exact
  commands. **This blocks any fresh `docker-compose up` deployment
  today** (see that file's `db`/`backend` service comments) and needs a
  decision from whoever owns this codebase before the next real
  deployment.
* **No real authentication.** The only mechanism that exists (see
  [Identity architecture](#identity-architecture)) is a development-only
  header naming an existing user, gated by `DEV_MODE` (default off, and
  must stay off in production). Before any real deployment: implement a
  `TokenVerifier` for a real OIDC/OAuth2 provider and wire it into
  `app/api/deps_auth.py` in place of the dev-mode mechanism.
* **Most existing routes still trust the URL directly.** Only the
  membership endpoints require authentication and a permission check
  today; organizations/sites/data-sources/knowledge do not — see
  ["Existing organization-scoped APIs"](#existing-organization-scoped-apis).
  Before any real deployment, every organization-scoped route must be
  cut over to `require_permission`/`TenantContext`, the same way the
  membership endpoints already are.
* **No machine-client authentication.** Safelytic and any other external
  application connecting to SIE will need OAuth2 client credentials or
  API keys — explicitly out of scope for this milestone (see
  ["Machine clients"](#machine-clients-architecture-not-implementation)) — plus a principal type/flow
  for a non-human caller through the same membership/role/permission
  pipeline.
* **No self-registration or email invitations.** Adding a member is
  strictly administrative today (`POST .../members` names an existing
  `User` id) — no signup flow, no invite-by-email, no way for a new
  person to create their own `User` row short of the identity resolver
  (which itself has no real IdP feeding it yet).
* **No update/delete endpoints** for any resource yet — only create and
  read, matching what was scoped for this phase.
* **No pagination metadata** (total count, next-page cursor) on list
  endpoints, only `skip`/`limit`.
* **No structured logging, tracing, or rate limiting.**
* **No CI pipeline** wired up in this repository yet to run `pytest`
  automatically on push.
* **Only one chunk HTTP endpoint, and it's read-only.**
  `app/services/chunking_service.py` is called by
  `app/services/ingestion_service.py` on every successful ingestion (see
  [Knowledge Quality & Semantic Chunking
  Pipeline](#knowledge-quality--semantic-chunking-pipeline)); the only
  route is `GET .../versions/{version_id}/chunks` — there is no
  create/update/delete route for chunks anywhere, by design.
* **No OCR execution, table extraction, or transcription.** All
  architected for (`app/ingestion/ocr.py`, `PDFAdapter`'s explicit
  `table_extraction: "not_attempted"`, the "Audio/Video" row in the
  format matrix) but none implemented — see
  [Universal ingestion architecture](#universal-ingestion-architecture).
* **No JSON/XML schema mapping.** `JSONAdapter`/`XMLAdapter` validate and
  do basic, schema-agnostic parsing only; identifying *what kind* of
  safety data a payload represents (an incident, an inspection, ...) and
  mapping it to canonical fields is future work, same as for CSV/XLSX
  rows.
* **No semantic (embedding-aware) chunking, and no embeddings/vector
  search/RAG at all.** `StructureAwareChunkingStrategy` is deterministic,
  structure-based splitting — see [Knowledge Quality & Semantic Chunking
  Pipeline](#knowledge-quality--semantic-chunking-pipeline). A future
  `SemanticChunkingStrategy` (or `TableAwareChunkingStrategy`,
  `LegalDocumentChunkingStrategy`, `SafetyProcedureChunkingStrategy`) can
  be added as another `ChunkingStrategy` implementation without changing
  the interface or any call site; none of that, nor any embedding
  computation, vector column, or retrieval layer, exists yet.
* **DOCX list-item detection covers Word's built-in styles only.**
  `app/ingestion/adapters/docx_adapter.py` detects "List Bullet"/"List
  Number" paragraph styles, not manually-formatted lists (a paragraph
  that merely starts with a hyphen or "1)" without that style applied).
* **No background ingestion workers.** `IngestionService.ingest()` runs
  synchronously in the request; `IngestionJob`'s state machine already
  models an async job's lifecycle for when that changes (see
  [Universal ingestion architecture](#universal-ingestion-architecture)).
* **`app/ingestion/adapters/registry.py` returns exactly one adapter per
  detected type**, first-match — there's no ranking or fallback if a
  file matches more than one adapter's `detect()` (not currently
  possible with the registered set, but worth noting as the format list
  grows).
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
* **`HashingEmbeddingProvider` is not a trained semantic model.** It is a
  genuine, deterministic, dependency-free feature-hashing embedding — see
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture) —
  chosen specifically so this milestone's tests and evaluation harness
  never need network access or a downloaded model. `SentenceTransformerEmbeddingProvider`
  is implemented as the real-model extension point but was not exercised
  against an actual downloaded model in this environment. Before any
  production use, a real embedding model should be evaluated and wired in
  through that same provider abstraction — no `RetrievalService` or
  `EmbeddingService` call site would need to change.
* **No ANN vector index (IVFFlat/HNSW).** Deliberate for this milestone's
  dataset size — see [Semantic Knowledge Architecture](#semantic-knowledge-architecture)'s
  "Indexing decision" — but will need to be added and tuned once a real
  deployment's chunk/embedding count grows past what an exact sequential
  scan comfortably serves.
* **Retrieval thresholds are calibrated to `HashingEmbeddingProvider`
  specifically.** `RETRIEVAL_MIN_SIMILARITY`/`RETRIEVAL_MODERATE_SIMILARITY`/
  `RETRIEVAL_HIGH_SIMILARITY` will need recalibrating against that
  model's own score distribution if a different embedding provider is
  ever configured — they are not universal constants.
* **No background embedding workers.** `EmbeddingService`/`RetrievalService`
  both run synchronously in the request, exactly like `IngestionService`
  — see [Semantic Knowledge Architecture](#semantic-knowledge-architecture)'s
  "Production architecture consideration" for the future
  Queue -> Embedding Worker evolution this is deliberately shaped to
  support without an API/schema break.
* **No hybrid (keyword + vector) retrieval, reranking, RAG, or LLM
  integration.** All explicitly out of scope for this milestone — see
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture)'s
  "Future architecture" diagram.
