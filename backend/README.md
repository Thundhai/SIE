# SIE Backend — Safety Intelligence Engine

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

Three milestones are implemented so far:

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
      deps.py         Organization path-resolution dependency (pre-identity)
      deps_auth.py     Identity/authorization dependencies (see Identity architecture)
      v1/            Versioned routes (health, organizations, sites,
                      data-sources, knowledge, memberships)
    core/           Configuration (Pydantic Settings) and DB engine/session setup
    models/         SQLAlchemy 2.x ORM models (Organization, Site, User,
                     DataSource, KnowledgeSource, KnowledgeDocument,
                     KnowledgeDocumentVersion, KnowledgeChunk,
                     OrganizationMembership, Identity, AuditLog)
    schemas/        Pydantic v2 request/response schemas
    services/       Tenant-scoped repository/service layer, plus
                     permissions/authorization/tenant-context/identity/audit
                     services (see Identity architecture)
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

Three migrations exist so far: `0001` (Foundation v0.1 — organizations,
sites, users, data_sources), `0002` (Knowledge Foundation v0.1 —
knowledge_sources, knowledge_documents, knowledge_document_versions,
knowledge_chunks), and `0003` (Identity & Access Foundation v0.1 —
organization_memberships, identities, audit_logs, plus a compatibility
change to the `users` table — see
["Compatibility concerns"](#identity-architecture) below). Earlier
migrations are never modified; new schema changes are always a new
migration on top.

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

The three membership endpoints are the one place in this codebase that
requires authentication and a permission check today — see
[Identity architecture](#identity-architecture) for what that means in
practice (development-mode only, no real identity provider connected
yet) and why the routes above them still don't.

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
* **DataSource** — a system SIE ingests from (ingestion itself is not
  implemented yet). Adds `organization_id`, `source_type`, `last_sync_at`.
* **KnowledgeSource, KnowledgeDocument, KnowledgeDocumentVersion,
  KnowledgeChunk** — the knowledge foundation; see
  [Knowledge architecture](#knowledge-architecture) below for the full
  field list and design.
* **OrganizationMembership, Identity, AuditLog** — the identity & access
  foundation; see [Identity architecture](#identity-architecture) below.

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
(API keys, OAuth client credentials), the AI/LLM layer, RAG, vector
search, predictive models, Safelytic integration, Redis, and any
microservice/Kubernetes topology. See
[Identity architecture](#identity-architecture) for what *is* built
towards authentication/authorization, and the "Deliberately does not
implement" list the Identity & Access Foundation milestone itself set
(no password auth, no stored passwords, no API keys, no OAuth client
credentials, no SSO config UI, no MFA, no password reset, no email
invitations) — all of that is still true of this codebase.

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
