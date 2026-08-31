# SIE Backend — Safety Intelligence Engine

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

Four milestones are implemented so far:

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

The AI/LLM layer, RAG, embeddings, vector search, predictive models,
OCR execution, transcription, and Safelytic integration are all out of
scope so far and are stubbed out only as empty, documented package
placeholders (`app/intelligence`, `app/analytics`, `app/predictions`,
`app/governance`) or interface-only modules (`app/ingestion/ocr.py`) so
later phases have a predictable home without a restructure. **No AI
training, embeddings, RAG, or predictive analytics exist in this codebase
yet** — the knowledge foundation and ingestion engine below store and
structure content for that future work; neither performs it.

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

Ingestion tests use real small fixture files
(`tests/fixtures/ingestion/`, PDF/DOCX/XLSX/CSV/PPTX/RTF/TXT — see that
directory's own README.md for what each one is and how it was generated)
rather than strings standing in for file content, and a per-test
temporary directory (`tmp_path`, via an autouse fixture in
`tests/conftest.py`) rather than the real `var/ingested_files` storage
path.

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
| POST   | `/api/v1/organizations/{organization_id}/members`        | Add a member (`users:manage`)        |
| GET    | `/api/v1/organizations/{organization_id}/members`        | List members (`users:read`)          |
| GET    | `/api/v1/organizations/{organization_id}/members/{user_id}` | Get one member (`users:read`)     |
| POST   | `/api/v1/knowledge/ingestion`                             | Upload and ingest a file (`knowledge:manage`) |

The membership endpoints and the ingestion endpoint are the routes in
this codebase that require authentication and a permission check today —
see [Identity architecture](#identity-architecture) for what that means
in practice (development-mode only, no real identity provider connected
yet) and why the other routes above them still don't, and
[Universal ingestion architecture](#universal-ingestion-architecture) for
the ingestion endpoint's own authorization rules (global vs.
organization knowledge).

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

    file bytes -> detect -> validate -> hash -> extract -> normalize -> chunk

is `app/ingestion/pipeline.py` — pure, DB-independent, directly testable
(`tests/test_ingestion_pipeline.py`) — called by
`app/services/ingestion_service.py`, which supplies the remaining stages
(source/document association, persistence, provenance) that need the
database and the caller's authorized tenant context. New processors don't
require rewriting the pipeline: a new format is one adapter module plus
one line in `app/ingestion/adapters/registry.py`'s `_DEFAULT_ADAPTERS`
tuple.

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
├── metadata             format-specific extras (columns/values, speaker notes, tables, ...)
└── source_reference     human-readable locator, e.g. "Sheet: Incident Register, Row 124"
```

This is not an attempt to make every format mean the same thing — a
spreadsheet row and a PDF page are different things — it's a common
*envelope* that preserves whichever location fields are meaningful for
the format that produced it. A `ChunkingStrategy`
(`app/ingestion/chunking.py`) turns a list of these into `KnowledgeChunk`
rows: only a simple, deterministic paragraph/size-based
`SimpleChunkingStrategy` is implemented (no semantic/embedding-aware
chunking — out of scope, see below), but every location field is carried
straight through into each chunk's `metadata`, split or not, so a chunk
still says "page 47" or "Sheet: Incident Register, Row 124" no matter how
it was cut.

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

## Configuration

All configuration is environment-based (`app/core/config.py`, backed by
Pydantic Settings and a local `.env` file — see `.env.example`). No
secrets are committed; `.env` is git-ignored. `DEV_MODE` (default
`false`) is the one identity-related setting — see
[Identity architecture](#identity-architecture) above.

## Deliberate scope boundaries (v0.1)

To keep each foundation phase clean and reviewable, the following are
intentionally **not** included yet: real OIDC/OAuth2 token verification, a
commercial identity provider dependency, machine-client authentication
(API keys, OAuth client credentials), the AI/LLM layer, RAG, embeddings,
pgvector/semantic search, predictive models, machine learning, Safelytic
integration, Redis, Celery, Kafka, Kubernetes, production (S3/Azure/GCS)
object storage, commercial OCR, transcription, unrestricted web crawling,
and automatic external-source trust. See
[Identity architecture](#identity-architecture) for what *is* built
towards authentication/authorization, and the "Deliberately does not
implement" list the Identity & Access Foundation milestone itself set
(no password auth, no stored passwords, no API keys, no OAuth client
credentials, no SSO config UI, no MFA, no password reset, no email
invitations) — all of that is still true of this codebase. Similarly, see
[Universal ingestion architecture](#universal-ingestion-architecture) for
what the ingestion engine does and does not implement (real OCR
execution, semantic chunking, and a JSON/XML schema-mapping layer are
architected for but not built).

## Known gaps / next phase

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
* **No chunk HTTP endpoints.** `KnowledgeChunkService.create_many` is now
  called by `app/services/ingestion_service.py` on every successful
  ingestion (see [Universal ingestion architecture](#universal-ingestion-architecture)),
  but there is still no route to create, list, or inspect chunks
  directly — only indirectly, via the ingestion response's `chunk_count`
  and the existing knowledge read endpoints.
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
* **No semantic chunking.** `SimpleChunkingStrategy` is deterministic
  paragraph/size-based splitting; a future `ChunkingStrategy`
  implementation can replace it without changing the interface or any
  call site.
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
