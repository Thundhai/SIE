# SIE Backend — Safety Intelligence Engine

SIE is an independent, multi-tenant safety intelligence platform. This
service is not architecturally coupled to any single client application.
Safelytic (the frontend in this repository) will eventually be one
consumer of the SIE API — but it is a consumer, not a dependency. Any
authorized enterprise application connects the same way: through the
versioned REST API under `/api/v1`.

Ten milestones are implemented so far:

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
  numbers. Proved retrieval works *before* any LLM/RAG layer existed. See
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture)
  below.
* **Evidence-Grounded RAG v0.1** — a controlled reasoning layer over that
  retrieval evidence: an `LLMProvider` abstraction (a deterministic test
  provider, plus a documented, unexercised real-provider extension
  point), evidence selection, deterministic evidence-sufficiency rules,
  abstention when evidence is insufficient, source-conflict detection,
  citation generation and validation, full provenance through to the
  final response, tenant isolation reused unchanged, an external-LLM
  privacy boundary, prompt versioning, and a synthetic RAG evaluation
  harness. **The LLM is not the source of truth** — SIE's knowledge
  sources are the evidence. See
  [Evidence-Grounded RAG](#evidence-grounded-rag) below.
* **Intelligence & Predictive Analytics Foundation v0.1** — the
  trustworthy data-intelligence foundation a future predictive layer will
  need, not the predictive layer itself: a canonical, source-agnostic
  `SafetyEvent` model across eleven safety-data domains; a
  validate/normalize/idempotent-ingest pipeline (single and batch) with
  full source provenance and a deterministic data-quality state on every
  record; machine-client (API key) authentication for external system
  integration, independent of the dev-mode human header; strict
  point-in-time-correct feature engineering (no future information can
  leak into a historical calculation — enforced in one central place and
  regression-tested); exposure-normalized rates; deterministic leading/
  lagging indicators, trend classification, z-score anomaly detection,
  and rule-based risk signals — never a fabricated probability; a
  synthetic evaluation dataset and harness. **This milestone does not
  claim to predict accidents or injuries.** See
  [Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)
  below.
* **Predictive Risk Modeling Specification v0.1** — a rigorous, auditable
  predictive-modeling foundation: an explicit, versioned specification of
  what SIE predicts (Elevated Safety Event Risk, per site, over a 30-day
  horizon), a deterministic label generator that never leaks into
  features, a versioned/persisted feature-snapshot architecture, a
  hand-rolled (no numpy/scikit-learn) logistic regression baseline,
  chronological train/validation/test splitting and walk-forward
  backtesting, Recall/Precision/PR-AUC-first evaluation reported
  separately for sufficient- and limited-data entities, a minimal model
  registry with an enforced human-review lifecycle
  (`TRAINED -> VALIDATED -> APPROVED -> DEPLOYED`, nothing auto-promoted),
  coefficient-based "contributing feature" explanations that never claim
  causation, mandatory abstention (`NO_PREDICTION`) whenever data is
  insufficient/stale/cold-start or the model isn't deployed, and a full
  prediction-to-source-record provenance chain. **Only a
  prototype model, explicitly labeled and trained on synthetic data, is
  produced — this milestone does not claim production predictive
  performance.** See
  [Predictive Intelligence Architecture](#predictive-intelligence-architecture)
  below.
* **Predictive Model Validation & Governance v0.1** — the validation,
  governance, monitoring, and controlled-deployment foundation a
  predictive model needs *before* SIE can responsibly use it against real
  organizational data: explicit `SYNTHETIC`/`REAL` dataset versioning with
  a structured, multi-field real-data quality report (never a single
  collapsed score, never auto-modified — only quarantined/reported);
  configurable, explicitly-labeled "INITIAL GOVERNANCE DEFAULT" minimum
  data requirements gating training with `INSUFFICIENT_DATA`; a second
  comparison model (Gradient Boosting, via scikit-learn — a deliberate,
  documented exception to this project's hand-rolled-model default)
  evaluated identically to Logistic Regression with neither
  auto-selected; reliability-curve/Brier-score/ECE calibration validation
  that gates whether a score may ever be shown as a "probability";
  configurable decision thresholds; cross-time/site/data-quality model
  stability analysis; per-record false-negative/false-positive error
  analysis; an expanded rolling walk-forward harness and six mandatory
  temporal-leakage regression tests; a human-approval-gated model
  lifecycle (`TRAINED -> VALIDATED -> APPROVED -> DEPLOYED -> RETIRED`,
  the model can never approve itself) with controlled rollback; prediction
  monitoring, outcome tracking, and lightweight/explainable data, feature,
  and performance drift detection that only ever *flags* a model for
  human review, never retrains or redeploys anything automatically;
  machine- and human-readable model cards with explicit prohibited-use
  language; and a governance validation report producing an
  APPROVE/REJECT/REVIEW *recommendation* a human still has to act on. **A
  model is not "approved" by scoring well — a high-scoring but
  poorly-calibrated, unstable, or low-provenance model is not approved.**
  See
  [Predictive Model Validation & Governance Architecture](#predictive-model-validation--governance-architecture)
  below.

Deep-learning predictive models, autonomous/automated safety
interventions or decisions, worker-level risk scoring, automatic model
retraining, OCR execution, transcription, autonomous/tool-using agents,
and Safelytic integration are all out of scope so far. `app/analytics`,
`app/governance` remain empty, documented package placeholders (see
[Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)
for what `app/intelligence` itself now contains, and
[Predictive Intelligence Architecture](#predictive-intelligence-architecture) /
[Predictive Model Validation & Governance Architecture](#predictive-model-validation--governance-architecture)
for what `app/predictions` now contains) or interface-only modules
(`app/ingestion/ocr.py`) so later phases have a predictable home without a
restructure. **No AI training beyond the two models in `app/predictions`
(hand-rolled Logistic Regression; Gradient Boosting via scikit-learn, the
one deliberate, documented dependency exception), no autonomous agents,
tool-calling, web search/crawling, automated retraining, or workflow
automation exist in this codebase.**

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
  Architecture](#semantic-knowledge-architecture). The full migration
  chain (0001-0006) has been verified end to end against a genuinely
  fresh PostgreSQL 16.13 + pgvector 0.6.0 database with no manual
  intervention — see [Known gaps](#known-gaps--next-phase) for what was
  fixed and how it was proven.

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

Seven migrations exist so far: `0001` (Foundation v0.1 — organizations,
sites, users, data_sources), `0002` (Knowledge Foundation v0.1 —
knowledge_sources, knowledge_documents, knowledge_document_versions,
knowledge_chunks), `0003` (Identity & Access Foundation v0.1 —
organization_memberships, identities, audit_logs, plus a compatibility
change to the `users` table — see
["Compatibility concerns"](#identity-architecture) below), `0004`
(Universal Knowledge & Data Ingestion Engine v0.1 — ingested_files,
ingestion_jobs; purely additive, no changes to any existing table), `0005`
(Knowledge Quality & Semantic Chunking Foundation v0.1), `0006` (Semantic
Knowledge Engine v0.1 — pgvector + knowledge_chunk_embeddings), and
`0007` (Intelligence & Predictive Analytics Foundation v0.1 —
`safety_events` and `api_clients`; purely additive — see
[Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)
for why no other table was added), `0008` (Predictive Risk Modeling
Specification v0.1 — `feature_snapshots`, `model_registry_entries`,
`predictions`; purely additive — see
[Predictive Intelligence Architecture](#predictive-intelligence-architecture)
for what each table stores and why no `model_evaluations` table was
needed), and `0009` (Predictive Model Validation & Governance v0.1 —
`dataset_versions`, `model_approvals`, `model_review_flags`,
`prediction_outcomes`, plus an additive, nullable
`model_registry_entries.dataset_version_id` foreign key; no existing
column altered or dropped — see
[Predictive Model Validation & Governance Architecture](#predictive-model-validation--governance-architecture)
for what each table stores). Earlier migrations are never modified; new
schema changes are always a new migration on top.

## API endpoints

| Method | Path                                                    | Description                          |
|--------|----------------------------------------------------------|---------------------------------------|
| GET    | `/health`                                                | Liveness check                       |
| GET    | `/health/live`                                           | Process-liveness check — never fails on a dependency (Intelligence Platform Integration v0.1) |
| GET    | `/health/ready`                                          | Readiness check — 503 if PostgreSQL is unreachable (Intelligence Platform Integration v0.1) |
| POST   | `/api/v1/organizations`                                  | Create an organization               |
| GET    | `/api/v1/organizations/{organization_id}`                | Get an organization                  |
| POST   | `/api/v1/organizations/{organization_id}/sites`          | Create a site under an organization  |
| GET    | `/api/v1/organizations/{organization_id}/sites`          | List sites for an organization       |
| POST   | `/api/v1/organizations/{organization_id}/data-sources`   | Register an ingestion source — **human OR machine caller**; `safety_data:write` (Enterprise Data Ingestion v0.1) |
| GET    | `/api/v1/organizations/{organization_id}/data-sources`   | List an organization's ingestion sources — **human OR machine caller**; `safety_data:read` |
| GET    | `/api/v1/organizations/{organization_id}/data-sources/{source_id}` | Get one ingestion source — **human OR machine caller**; `safety_data:read` |
| PATCH  | `/api/v1/organizations/{organization_id}/data-sources/{source_id}/status` | Toggle a source active/inactive — **human OR machine caller**; `safety_data:write` |
| POST   | `/api/v1/knowledge/sources`                              | Create a knowledge source (GLOBAL or ORGANIZATION) — authenticated; `knowledge:manage`, platform-admin-only for GLOBAL |
| GET    | `/api/v1/knowledge/sources`                              | List knowledge sources (GLOBAL, or one organization's — see below) — authenticated; `knowledge:read` for an organization |
| GET    | `/api/v1/knowledge/sources/{source_id}`                  | Get a knowledge source — authenticated; `knowledge:read` for an organization-scoped source |
| POST   | `/api/v1/knowledge/documents`                            | Create a document under a source — authenticated; `knowledge:manage` |
| GET    | `/api/v1/knowledge/documents/{document_id}`              | Get a knowledge document — authenticated; `knowledge:read` for an organization-scoped document |
| POST   | `/api/v1/knowledge/documents/{document_id}/versions`     | Create a document version — authenticated; `knowledge:manage` |
| GET    | `/api/v1/knowledge/documents/{document_id}/versions`     | List a document's versions — authenticated; `knowledge:read` for an organization-scoped document |
| GET    | `/api/v1/knowledge/documents/{document_id}/versions/{version_id}/chunks` | List one version's chunks (read-only — see below) — authenticated; `knowledge:read` for an organization-scoped document |
| POST   | `/api/v1/organizations/{organization_id}/members`        | Add a member (`users:manage`)        |
| GET    | `/api/v1/organizations/{organization_id}/members`        | List members (`users:read`)          |
| GET    | `/api/v1/organizations/{organization_id}/members/{user_id}` | Get one member (`users:read`)     |
| POST   | `/api/v1/knowledge/ingestion`                             | Upload and ingest a file (`knowledge:manage`) |
| POST   | `/api/v1/knowledge/retrieval/search`                      | Semantic evidence search — **human OR machine caller** (`RequestContext`); `knowledge:read` if `filters.organization_id` is given |
| POST   | `/api/v1/knowledge/rag/query`                              | Evidence-grounded RAG query — **human OR machine caller**; `knowledge:read` if `filters.organization_id` is given |
| POST   | `/api/v1/intelligence/events`                              | Ingest one canonical safety event (**machine-client authenticated**, `safety_data:write` scope) |
| POST   | `/api/v1/intelligence/events/batch`                        | Batch-ingest safety events (same auth; partial success, per-record results) |
| GET    | `/api/v1/intelligence/analytics/summary`                   | Features + indicators + signals + source reliability for one organization/site — **human OR machine caller**; `intelligence:read` |
| GET    | `/api/v1/intelligence/analytics/trends`                    | Period-bucketed trend for one named metric — **human OR machine caller**; `intelligence:read` |
| GET    | `/api/v1/intelligence/analytics/signals`                   | Deterministic risk signals — **human OR machine caller**; `intelligence:read` |
| GET    | `/api/v1/intelligence/features`                            | Raw computed feature values — **human OR machine caller**; `intelligence:read` |
| POST   | `/api/v1/organizations/{organization_id}/api-clients`     | Provision a machine-client credential (`users:manage`) — returns the raw secret once; optional `expires_at` |
| GET    | `/api/v1/organizations/{organization_id}/api-clients`     | List an organization's machine clients (`users:manage`, never the secret) |
| POST   | `/api/v1/organizations/{organization_id}/api-clients/{id}/rotate` | Rotate a machine client's secret (`users:manage`) — org/scopes/identity survive; old secret dies immediately |
| POST   | `/api/v1/organizations/{organization_id}/api-clients/{id}/revoke` | Revoke a machine client (`users:manage`) |
| POST   | `/api/v1/data/ingestion`                                   | Submit structured enterprise operational data, batched (**machine-client authenticated**, `safety_data:write`); `Idempotency-Key` supported (Enterprise Data Ingestion v0.1) |
| GET    | `/api/v1/data/ingestion/batches`                           | List an organization's ingestion batches — **human OR machine caller**; `safety_data:read` |
| GET    | `/api/v1/data/ingestion/batches/{batch_id}`                | One batch's full status and per-record results — **human OR machine caller**; `safety_data:read` |
| POST   | `/api/v1/intelligence/predictions`                         | Generate/refresh a prediction for one site — **human OR machine caller**; `prediction:read`; server-computed only, see below; accepts `Idempotency-Key` |
| GET    | `/api/v1/intelligence/predictions/{entity_id}`              | The latest recorded prediction for one site — **human OR machine caller**; `prediction:read` |
| GET    | `/api/v1/intelligence/predictions/{entity_id}/history`      | Paginated prediction history, newest first, wrapped in the standard response envelope — **human OR machine caller**; `prediction:read` (Intelligence Platform Integration v0.1) |
| POST   | `/api/v1/intelligence/datasets/validate`                    | Register + validate a `SYNTHETIC` or `REAL` dataset version (`governance:manage`) — server-computed quality report |
| GET    | `/api/v1/intelligence/datasets`                             | List an organization's dataset versions (`governance:read`) |
| GET    | `/api/v1/intelligence/datasets/{dataset_version_id}`         | One dataset version, with its full quality report (`governance:read`) |
| POST   | `/api/v1/intelligence/models/train`                          | Train one model — Logistic Regression or Gradient Boosting — from a dataset version (`governance:manage`); `422 INSUFFICIENT_DATA` if minimum data requirements aren't met |
| GET    | `/api/v1/intelligence/models`                                | List an organization's models (`governance:read`) |
| GET    | `/api/v1/intelligence/models/{model_id}`                     | One model's full record (`governance:read`) |
| POST   | `/api/v1/intelligence/models/{model_id}/validate`            | `TRAINED -> VALIDATED` (`governance:manage`) — calibration status checked server-side |
| POST   | `/api/v1/intelligence/models/{model_id}/approve`             | `VALIDATED -> APPROVED` (`governance:manage`) — reviewer is always the authenticated caller, never client-supplied |
| POST   | `/api/v1/intelligence/models/{model_id}/reject`              | `-> REJECTED` (`governance:manage`) — requires a reason |
| POST   | `/api/v1/intelligence/models/{model_id}/deploy`              | `APPROVED -> DEPLOYED` (`governance:manage`) — also usable to redeploy a previously `undeploy`-ed version |
| POST   | `/api/v1/intelligence/models/{model_id}/undeploy`            | `DEPLOYED -> APPROVED` (`governance:manage`) — pulled from serving without retiring |
| POST   | `/api/v1/intelligence/models/{model_id}/retire`              | `-> RETIRED` (`governance:manage`) — history is never deleted |
| GET    | `/api/v1/intelligence/models/{model_id}/card`                | The model card — intended/prohibited use, limitations, metrics (`governance:read`) |
| GET    | `/api/v1/intelligence/models/{model_id}/validation-report`   | A freshly-generated governance report with an APPROVE/REJECT/REVIEW recommendation (`governance:read`) |
| GET    | `/api/v1/intelligence/models/{model_id}/monitoring`          | Prediction monitoring + post-outcome-maturity performance monitoring (`governance:read`) |

**As of Intelligence Platform Integration & Enterprise API v0.1, every
route in the table above requires authentication** — the knowledge
source/document/version/chunk routes (previously trusting the URL
directly) were retrofitted to close that gap; see [Intelligence Platform
Integration & Enterprise API
Architecture](#intelligence-platform-integration--enterprise-api-architecture)
for the full design. The membership endpoints, the ingestion endpoint,
the retrieval search and RAG query endpoints, the knowledge endpoints,
and the intelligence/API-client endpoints are all authenticated (the
retrieval, RAG, knowledge, and intelligence-analytics endpoints
additionally require a permission check whenever an `organization_id` is
supplied) — see [Identity architecture](#identity-architecture) for what
that means in practice (development-mode only, no real identity provider
connected yet), and
[Universal ingestion architecture](#universal-ingestion-architecture) /
[Semantic Knowledge Architecture](#semantic-knowledge-architecture) /
[Evidence-Grounded RAG](#evidence-grounded-rag) /
[Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)
for the ingestion, retrieval, RAG, and intelligence endpoints' own
authorization rules. Every `/api/v1/intelligence/datasets/*` and
`/api/v1/intelligence/models/*` governance route additionally requires
`governance:read` (every `GET`) or `governance:manage` (every mutating
call) — granted by default only to `ORG_ADMIN` (`governance:manage`) and
`ORG_ADMIN`/`HSE_MANAGER`/`HSE_ANALYST`/`VIEWER` (`governance:read`; note
`HSE_USER` has neither) — see
[Predictive Model Validation & Governance Architecture](#predictive-model-validation--governance-architecture)
for the full authorization design. The intelligence ingestion endpoints are the
exception to every other authenticated route in this codebase: they use
**machine-client (API key) authentication**
(`app/api/deps_machine_auth.py`), never the development-mode human
header — see that section for why. There is deliberately no endpoint to
*create* or modify chunks — see [Knowledge Quality & Semantic Chunking
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
* **DataSource** — a registered external system SIE ingests structured
  operational data from (an EHS platform, an ERP, an IoT feed) — see
  [Enterprise Data Ingestion & Validation Foundation
  Architecture](#enterprise-data-ingestion--validation-foundation-architecture)
  below, which reuses this model as the "ingestion source" concept. Adds
  `organization_id`, `source_type`, `last_sync_at`,
  `system_identifier`, `schema_version`, `config_metadata`,
  `api_client_id`. Distinct from — and not used by — the file-upload
  ingestion engine below, which reads standalone files, not external
  systems.
* **EnterpriseIngestionBatch, EnterpriseIngestionRecord** — one row per
  submission and one row per input record through
  `POST /api/v1/data/ingestion`, for traceability; see [Enterprise Data
  Ingestion & Validation Foundation
  Architecture](#enterprise-data-ingestion--validation-foundation-architecture)
  below for the full design.
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

**SIE Milestone 20: Production Authentication & Identity Foundation
v0.1** implemented real token verification — see `docs/PRODUCTION_AUTH.md`
(repository root) for the full design. The diagram and "not implemented
yet" language immediately below describe the architecture as it stood
before that milestone; kept here for continuity since every layer it
names is still exactly as described except the top box, which is now real.

```
OIDC/OAuth2-compatible identity provider
    │  (real token verification — app/services/oidc_verifier.py,
    │   SIE Milestone 20)
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
depending on any specific provider's SDK. `app/services/oidc_verifier.py::OIDCTokenVerifier`
(SIE Milestone 20) is a real, provider-neutral implementation of that
protocol — see `docs/PRODUCTION_AUTH.md` (repository root). Connecting a
*specific* provider (its own login/redirect flow) remains future work;
the verification boundary itself is no longer hypothetical.

### Authentication vs. authorization vs. tenant isolation

Three distinct concerns, each with its own module, deliberately not
conflated:

* **Authentication** — "who is making this request." Answered by
  verifying a token's signature against an identity provider and
  extracting its claims (`OIDCTokenVerifier` — see `TokenVerifier` above
  and `docs/PRODUCTION_AUTH.md`), then resolving those claims to a `User`
  via `IdentityResolverService`. `DEV_MODE=True` still uses the
  development-only header mechanism described below instead; production
  (`DEV_MODE=False`) uses real OIDC/OAuth2 verification, never a
  fallback to the development mechanism.
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

*(As of the Semantic Knowledge Engine v0.1 and Evidence-Grounded RAG v0.1
milestones below, this is no longer true: pgvector is enabled, semantic
similarity search exists, and an evidence-grounded LLM reasoning layer
exists on top of it — see [Semantic Knowledge
Architecture](#semantic-knowledge-architecture) and
[Evidence-Grounded RAG](#evidence-grounded-rag).)*

## Semantic Knowledge Architecture

    KnowledgeChunk -> EmbeddingService -> EmbeddingProvider -> Vector
        -> KnowledgeChunkEmbedding (pgvector storage)
        -> RetrievalService -> Metadata filter -> Vector similarity
        -> Ranked RetrievalResult -> Provenance

This was the Semantic Knowledge Engine v0.1 milestone: it proves SIE can
retrieve semantically relevant knowledge chunks reliably, with tenant
isolation and full provenance.

**SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1** added a real, production-capable
`EmbeddingProvider` (`SentenceTransformerEmbeddingProvider`, wrapping a
genuine `sentence-transformers` model) alongside the deterministic
`HashingEmbeddingProvider` used below and throughout this milestone's own
evaluation — see `docs/SEMANTIC_EMBEDDING.md` for the full architecture,
production deployment guide, and evaluation results. Nothing in this
section's own description of `RetrievalService`'s behavior changed: the
real provider sits behind the exact same `EmbeddingProvider` interface,
selected purely by configuration (`EMBEDDING_PROVIDER`).

`RetrievalService` returns evidence — it
still does not call an LLM, construct a prompt, or generate an answer;
that is a separate layer built directly on top of it, unmodified, in the
[Evidence-Grounded RAG](#evidence-grounded-rag) milestone documented
below. Still no BM25/keyword search, reranking model, or additional
search engine exists anywhere in this codebase — see
["What RAG deliberately does not do"](#what-rag-deliberately-does-not-do).

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
this module stays importable without it — and is not the default.

**Update (SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1):** `SentenceTransformerEmbeddingProvider` is now
a real, tested, production implementation — see
`docs/SEMANTIC_EMBEDDING.md` for the full architecture, the recommended
production model (`sentence-transformers/all-MiniLM-L6-v2`), and exactly
what real-model validation was (and was not) performed in this
sandboxed, network-restricted environment. `HashingEmbeddingProvider`
remains the default and the only provider CI itself exercises — the
paragraph above still accurately describes it. No commercial AI provider
is hardcoded into the domain layer anywhere; `EMBEDDING_PROVIDER`
(`app/core/config.py`) is a plain setting resolved once, at the edge, by
`get_embedding_provider()`.

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
`migrations/versions/0006_semantic_embeddings.py` read this one value
live (not baked in as a literal); neither hardcodes a dimension of its
own. Changing it requires a new migration (a pgvector column's dimension
is fixed at creation time) and re-embedding every chunk under a new
`EMBEDDING_MODEL_VERSION`.

**Design decision: one configured vector dimension per deployment, not
several at once.** This is the architecture pgvector itself imposes — a
`vector(N)` column is fixed-width at creation time — and it is what this
codebase has assumed since migration 0006 was first written. This
corrective milestone reviewed that assumption deliberately rather than
changing it silently, and hardened it instead of redesigning it: a new
`EmbeddingDimensionMismatchError` (`app/embeddings/embedding_service.py`)
is raised **before** any provider call or database write, the moment a
provider's `dimensions` disagrees with `settings.EMBEDDING_DIMENSIONS` —
turning what would otherwise be an opaque `psycopg.errors.DataException`
deep inside an `INSERT` into an immediate, actionable error naming the
provider, its model, its real dimension, and the configured column
width. It deliberately aborts the whole batch in
`generate_embeddings_for_version` rather than being collected as N
per-chunk `FAILED` outcomes — a dimension mismatch is a deployment-level
configuration error, not a fact about any individual chunk. Supporting
multiple simultaneous embedding dimensions in one deployment (e.g. a
second pgvector column at a different width) is future work, not
something this milestone needed: nothing in the current requirements
calls for two models with different dimensions running side by side in
production.

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

| Provider | Recall@1 | Recall@3 | Recall@5 |
| --- | --- | --- | --- |
| `HashingEmbeddingProvider` | 0.83 | 1.00 | 1.00 |
| `SentenceTransformerEmbeddingProvider` (`all-MiniLM-L6-v2`, recommended production model) | not measured in this environment | not measured in this environment | not measured in this environment |

The `HashingEmbeddingProvider` row is real and honestly-calculated (10 of
12 queries found their expected topic at rank 1; all 12 found it within
the top 3). This execution environment's egress policy blocks
`huggingface.co` (confirmed via the outbound proxy returning a
policy-denial 403 to that host), so the recommended production model's
weights could never be downloaded here — that row remains genuinely
unmeasured, not fabricated or estimated.

**Update (SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1)** did produce a real, honest hashing-vs-real
comparison anyway, using a small model *trained from scratch, entirely
offline* (not `all-MiniLM-L6-v2`, and not a substitute claimed to
represent it) — see `docs/SEMANTIC_EMBEDDING.md`'s "Evaluation" section
and `docs/SEMANTIC_EVALUATION_REPORT.md` for the full results,
methodology, and an explicit, harder (keyword-disjoint) paraphrase query
set added specifically to avoid rewarding lexical-overlap shortcuts.
Running `SentenceTransformerEmbeddingProvider` against the actual
recommended pretrained model and reporting real numbers for *that*
specific checkpoint remains future work for an environment with that
egress path open — this fixture's numbers, from any provider, say
nothing about how any embedding model would perform on real
organizational content; they say only whether the retrieval pipeline,
end to end, correctly surfaces topically relevant evidence on this one
small fixture.

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

    Semantic Retrieval (Semantic Knowledge Engine v0.1)
        -> Hybrid Retrieval (keyword search + vector search -> fusion)
        -> Reranking
        -> Evidence Selection (built — see Evidence-Grounded RAG)
        -> RAG (built — see Evidence-Grounded RAG)
        -> LLM Reasoning (built — see Evidence-Grounded RAG)

`RetrievalService` was deliberately shaped so this evolution could be
additive, and the [Evidence-Grounded RAG](#evidence-grounded-rag)
milestone below is exactly that: it calls `RetrievalService.search()`
unmodified and layers evidence selection, sufficiency, and an LLM
reasoning step on top, without changing `RetrievalService`'s own public
contract. What still does **not** exist anywhere in this codebase: no
BM25/keyword search, no Elasticsearch/OpenSearch or any other additional
search engine, no reranking model, no ANN vector index (see "Indexing
decision" above), and no autonomous/tool-using agent — see
["What RAG deliberately does not do"](#what-rag-deliberately-does-not-do)
for the complete, current list.

## Evidence-Grounded RAG

    User Question
        -> Authorization / Tenant Context      [existing, reused unchanged]
        -> RetrievalService                     [existing, reused unchanged]
        -> EvidenceSelectionService              (app/rag/evidence_selection.py)
        -> evaluate_sufficiency                  (app/rag/sufficiency.py)
        -> detect_conflicts                      (app/rag/conflict.py)
        -> build_grounded_context                (app/rag/context_builder.py)
        -> LLMProvider                           (app/llm/provider.py)
        -> citation validation                   (app/rag/citations.py)
        -> RAGResponse, with citations/provenance (app/rag/results.py)

This is the Evidence-Grounded RAG v0.1 milestone: a controlled reasoning
layer over SIE's existing retrieval evidence. **The LLM is not the
source of truth.** SIE's knowledge sources are the evidence; the LLM is a
reasoning/language-generation layer operating over retrieved evidence —
never a fact source in its own right, and never presented as one. If
sufficient evidence cannot be retrieved, SIE says so explicitly
(`INSUFFICIENT_EVIDENCE`) rather than inventing an answer from the
model's general/pretrained knowledge.

`POST /api/v1/knowledge/rag/query` is the one HTTP entry point
(`app/api/v1/rag.py`) — same authorization shape as
`POST /api/v1/knowledge/retrieval/search` (see
[Semantic retrieval API](#running-with-docker-compose-recommended) /
`app/api/v1/retrieval.py`'s own docstring): every request must be
authenticated, and `filters.organization_id`, if present, must be
authorized (`knowledge:read` in that organization) before it is ever
passed down. There is no second tenant-isolation mechanism — RAG reuses
`RetrievalService`'s exactly, unmodified. The client cannot select an
embedding model or an LLM provider/model; both are resolved server-side
from app settings.

### LLM provider abstraction

`app/llm/provider.py::LLMProvider` is a `Protocol`
(`generate(request) -> response`, plus `provider_name`/`model_name`/
`model_version`/`is_external`) — the exact same "configuration-based
boundary, nothing above it imports a concrete implementation" shape
`app/embeddings/provider.py::EmbeddingProvider` already establishes.
`RAGService` depends on this protocol only; it never imports OpenAI,
Anthropic, Google, or any other commercial SDK directly.

**`FakeLLMProvider`, a deterministic, dependency-free, offline test/dev
provider, is the only provider actually exercised anywhere in this
milestone** — in development, in the test suite, and in the RAG
evaluation harness alike, for the identical reason
`HashingEmbeddingProvider` is the only embedding provider actually
exercised: tests and CI must never require network access or a
commercial API key. It builds a short, templated, genuinely-grounded
answer from whatever `[E#]` evidence it actually finds in the supplied
context — deterministic, and clearly self-identified in every field it
returns (`provider_name="fake"`, `model_name="sie-fake-test-llm"`) so a
response can never be mistaken for one from a real AI model.

`OpenAICompatibleLLMProvider` is the documented extension point for a
real provider — any HTTP service exposing an OpenAI-compatible
`/chat/completions` endpoint (this covers OpenAI itself, and self-hosted/
open-source inference servers that speak the same schema). It is
implemented and code-reviewed but **was not exercised against a real
model/API in this environment**: no reachable LLM API endpoint in this
session's sandboxed egress policy, and per explicit instruction, no
alternative/substitute model was exercised in its place either. Do
not present it as validated. (`SentenceTransformerEmbeddingProvider`
was in this identical position until SIE Milestone 21 — see
`docs/SEMANTIC_EMBEDDING.md` for how that milestone worked around the
same egress restriction to still produce a genuine, honestly-labeled
real-model result; the same technique could apply here in a future
milestone, but has not been attempted for the LLM layer.) Selected via
`LLM_PROVIDER=openai_compatible`,
configured entirely through `app/core/config.py` settings
(`LLM_MODEL_NAME`, `LLM_API_BASE_URL`, `LLM_API_KEY`, `LLM_TEMPERATURE`,
`LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`) — the API key is read
once from an environment variable, never committed, never logged, and
never placed in any `LLMResponse` or exposed through the API.

**Guardrail against shipping the test provider by accident.**
`LLM_PROVIDER` defaults to `"fake"` — the identical asymmetry
`EMBEDDING_PROVIDER`/`HashingEmbeddingProvider` already has relative to
`DEV_MODE`: the test/CI-safe default is also the value that must never
quietly reach a real deployment. `build_llm_provider()` (and therefore
`get_llm_provider()`, what application startup and every request path
actually call) **raises `FakeLLMProviderInProductionError` and refuses to
construct the provider at all** whenever it would resolve to `"fake"`
while `APP_ENV` is `"production"`/`"prod"` — the same "fail closed" shape
`DEV_MODE` and `EmbeddingProvider`'s own guard already use.

### Evidence selection — not every retrieved chunk reaches the prompt

`app/rag/evidence_selection.py::EvidenceSelectionService` filters, in
order: drop `INSUFFICIENT`-quality extractions; drop `LOW`-relevance
matches (RetrievalService's own similarity floor is looser than what is
usable *as grounding evidence*); drop near-duplicate content (Jaccard
token overlap over a configurable threshold, `RAG_DEDUP_SIMILARITY_THRESHOLD`);
prioritize `VERIFIED` sources (a stable reorder, never a discard); then
cap at `RAG_MAX_EVIDENCE_ITEMS` and `RAG_MAX_CONTEXT_CHARACTERS` — the
character cap drops whole items rather than truncating one mid-content,
so a citation always points at its item's complete text, never a
silently-cut fragment. Every surviving item keeps its full
`RetrievalResult` (rank, similarity, verification status, extraction
quality, location, scope, organization_id, ...) unchanged, and is
assigned a stable citation id (`E1`, `E2`, ...) in final order.

### Evidence sufficiency — deterministic rules, never delegated to the LLM

`app/rag/sufficiency.py::evaluate_sufficiency` computes one of
`SUFFICIENT` / `PARTIAL` / `INSUFFICIENT` from `RelevanceLevel` buckets
and counts alone — never from anything resembling an LLM confidence
score (milestone's own instruction: "do not call this AI confidence").
The exact rules:

1. Zero selected evidence items -> `INSUFFICIENT`.
2. At least one `HIGH`-relevance item **and** at least
   `RAG_SUFFICIENT_MIN_EVIDENCE_COUNT` (default 2) items overall ->
   `SUFFICIENT`.
3. Anything else (some evidence exists, but rule 2's bar isn't met) ->
   `PARTIAL`.

### Abstention and partial evidence

When `evidence_state == INSUFFICIENT`, `RAGService` returns
`outcome=INSUFFICIENT_EVIDENCE` **without ever calling the LLM** — the
deterministic gate runs first, so a provider that might otherwise answer
confidently from general/pretrained knowledge never gets the chance to.
The response's `abstention_reason` states what was searched, how many
candidates were found, how many survived evidence selection, and suggests
a next step (rephrase, narrow/widen scope, confirm ingestion).

When `evidence_state == PARTIAL`, the request still reaches the LLM (the
system prompt instructs it to distinguish what is directly supported from
what cannot be established — see below), and the response additionally
carries an explicit `PARTIAL_EVIDENCE` warning so a client can always see
this structurally, independent of the generated prose.

**Unsupported-claim guardrail.** Even when evidence was supplied to the
LLM, an answer that cites *none* of it is rejected rather than returned
(`outcome=UNSUPPORTED_CLAIM_REJECTED`, `answer=None`) — an uncited claim
from a pipeline that is supposed to be evidence-grounded is exactly the
failure mode this milestone forbids, so it is treated as untrustworthy
regardless of how confident it reads.

### Source conflicts — never resolved automatically

`app/rag/conflict.py::detect_conflicts` is a small, explicit, **deterministic**
rule — not machine learning, and not claimed to be a general-purpose
contradiction detector. Two evidence items that both contain a requirement
cue word ("required"/"must"/"shall"/...) are flagged as conflicting when
their topic-word overlap (Jaccard, after removing stopwords and
requirement/negation cue words) clears `RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD`
(same subject) and exactly one of them contains a negation cue
("not"/"no"/"never"/"without"/...) while the other does not (opposite
polarity) — e.g. "Hard hats are required." vs. "Hard hats are not
required." When a conflict is detected, `RAGService` returns
`outcome=SOURCE_CONFLICT` **built directly from the conflicting evidence,
without ever calling the LLM** — both sources are named, both statements
quoted verbatim, and the response states plainly that SIE cannot resolve
the conflict automatically. This is a defense-in-depth heuristic, not a
guarantee: a paraphrased conflict with no shared vocabulary, or one that
doesn't hinge on an explicit negation word, will not be detected.

### Prompt injection defense — documented as defense in depth, not a guarantee

`app/rag/prompt.py`'s versioned system prompt explicitly instructs the
model to treat retrieved evidence as DATA, never as instructions — even
text that reads like "ignore previous instructions" inside a document's
content. `app/rag/context_builder.py` enforces the structural half of
this: system instructions, the user's question, and retrieved evidence
are three separate fields all the way to the `LLMProvider` boundary
(`LLMRequest`), never concatenated into one blob, and every evidence item
is wrapped in explicit `UNTRUSTED DATA`/`BEGIN DOCUMENT CONTENT`/`END
DOCUMENT CONTENT` delimiters. **This is documented, not claimed, as
defense in depth.** A real LLM reads its entire input as one token
stream; nothing about string concatenation or delimiter text
*cryptographically* prevents a sufficiently adversarial document from
influencing a real model's behavior, and this codebase makes no claim
that it does — see `tests/test_rag_context_builder.py` and
`tests/test_rag_api.py`'s injection test for exactly what is and is not
verified.

### Citations — generated from actual evidence, validated, never fabricated

The LLM is asked to cite `[E#]` markers matching the evidence ids it was
actually given (see the grounded-context format below) — and it is never
trusted to have done so correctly. `app/rag/citations.py::validate_and_sanitize_citations`
checks every `[E#]` token in the generated answer against the evidence
ids that were *actually supplied*: a valid one is left untouched; an
invalid one (e.g. `[E999]` when no such id exists) is replaced with an
explicit `[citation removed: not found in supplied evidence]` placeholder
and reported as an `INVALID_CITATION_REMOVED` warning. The final response
never contains a fabricated evidence reference.

### Structured evidence context

Each evidence item passed to the LLM is rendered with its full provenance
— Evidence id, Source, Document, Version, Location, Verification,
Extraction quality, Authority (where set), Scope, Similarity, and
Content — exactly the shape the milestone's own example lays out. No
internal database id is ever included in this text; the model only ever
sees the stable `[E#]` identifier, never a raw `chunk_id`/`document_id`/
`source_id`. Those internal ids remain available on the structured
`Citation` objects in the API response for a client that needs to link
back to the source record (see "Provenance" below) — they simply never
appear inside the generated prose itself.

### Provenance — Response -> Citation -> Chunk -> Version -> Document -> Source

Every `Citation` in a `RAGResponse` wraps the original `RetrievalResult`
unchanged, which in turn was built from real joined rows
(`KnowledgeChunk` -> `KnowledgeDocumentVersion` -> `KnowledgeDocument` ->
`KnowledgeSource`) — see `app/retrieval/retrieval_service.py`. Nothing in
the RAG layer summarizes, rewrites, or drops this chain; every field
(`document_title`, `source_name`, `version_label`, `location`,
`verification_status`, `extraction_quality`, `similarity`, `scope`,
`organization_id`) survives from retrieval all the way to the final HTTP
response.

### Tenant isolation, global knowledge, and privacy

RAG reuses `RetrievalService`'s tenant isolation exactly — `allowed_organization_id`
is resolved and authorized by `app/api/v1/rag.py` before `RAGService` is
ever called, the same "resolve-then-authorize-then-pass-a-trusted-value"
shape used everywhere else in this codebase. There is no second
tenant-isolation mechanism. GLOBAL and authorized-organization evidence
can appear together in one response, each citation's `scope` field
preserving which is which — this matters when they conflict (see "Source
conflicts" above).

**External LLM privacy boundary (`ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA`,
default `False`).** If any selected evidence is organization-private
(not GLOBAL) and the configured `LLMProvider.is_external` is `True`,
`RAGService` refuses to call it (`outcome=PRIVACY_BLOCKED`) unless this
setting is explicitly enabled — SIE never silently transmits private
content to an external provider. `FakeLLMProvider.is_external = False`
(it never leaves this process); a real provider defaults to
`is_external=True` unless a deployment explicitly configures a genuinely
self-hosted/private endpoint (`LLM_PROVIDER_IS_EXTERNAL=False`). SIE
makes no claim about any specific commercial provider's own
privacy/data-retention policy — organizations may eventually require
self-hosted models, private model endpoints, regional processing, or
no-training/data-retention guarantees; this milestone represents provider
configuration separately from core logic specifically so that remains
possible without a redesign.

**No training on organization data.** SIE does not use organization data
to train the embedding model or the LLM in this milestone, and there is
no model-training or fine-tuning pipeline anywhere in this codebase.
Organization data is retrieval context only.

### Prompt versioning and reproducibility

Every `RAGResponse` carries `prompt_version` (`app/rag/prompt.py` — a
plain version-string-keyed dict, so an older prompt's exact text stays
retrievable even after a newer one is added), plus a `retrieval_metadata`
envelope (retrieval/selection counts, embedding model identity, timing).
Internally (not exposed over HTTP — see "What the API response never
contains" below), `RAGResponse.reproducibility` additionally carries the
query, retrieval filters, and every selected chunk's id/version/
similarity/relevance — so a later challenge to a generated answer can
always identify exactly what evidence and model configuration produced
it. This is written into the existing `AuditLog` (see "Audit and
observability" below), not into a new database table.

### Audit and observability

RAG requests reuse the existing `app/services/audit_service.py`
(`AuditAction.RAG_QUERY_EXECUTED`) rather than adding a new database
table — see `app/rag/rag_service.py`'s own docstring for why a dedicated
table was judged unnecessary: `AuditLog.event_metadata` already gives a
tenant-scoped, indexed, JSON-capable place for outcome, evidence state,
evidence/citation/conflict/warning counts, prompt version, model
identity, timing, success/failure, and the full reproducibility payload
above. The raw query text and generated answer are included only when
`LOG_RAG_QUERY_TEXT`/`LOG_RAG_ANSWER_TEXT` are explicitly enabled (both
default `False`) — identical to `RetrievalService`'s own
`LOG_RETRIEVAL_QUERY_TEXT` precedent. `logger.info("rag_query", ...)`
separately emits safe, content-free metrics (durations, counts,
outcome/evidence_state) for observability tooling.

### What the API response never contains

No system prompt, no raw prompt text, no raw embedding vector, no API
key, no internal database credential, no private storage path. See
`app/schemas/rag.py`'s own docstring.

### What RAG deliberately does not do

No predictive analytics, no machine learning, no autonomous or
tool-using agents, no external web search or web crawling, no model
fine-tuning or training pipeline, no reinforcement learning, no automatic
incident intervention or workflow execution, no BM25/keyword search or
additional search engine, no reranking model, and no conversation
memory/personality/open-ended general-knowledge chat — SIE RAG is a
safety-intelligence evidence system, not a general-purpose chatbot. These
remain future/separate milestones, not part of what this codebase does
today.

### A note on what citations do and do not mean

**SIE does not guarantee that generated answers are correct simply
because they contain citations. Citations indicate supporting source
material; users remain responsible for appropriate professional
verification of safety-critical decisions.**

## Intelligence & Predictive Analytics Architecture

    External Systems (Safelytic, other HSE systems, ERP/HR/CMMS, IoT, audits, ...)
        -> Data Ingestion (validate -> normalize -> idempotent upsert)
        -> Canonical SafetyEvent
        -> Feature Engineering (point-in-time correct)
        -> Indicators (leading / lagging)
        -> Risk Signals (deterministic, rule-based)
        -> Future Predictive Models (interface only — not built here)

This is the Intelligence & Predictive Analytics Foundation v0.1
milestone. **This milestone does not claim to predict accidents or
injuries.** It establishes the trustworthy analytical foundation
(canonical event model, provenance, temporal integrity, data quality,
exposure normalization, feature engineering, deterministic indicators and
signals) required for future predictive modeling — see
`app/intelligence/predictive_model.py`'s own docstring for exactly what
remains before real predictive ML exists.

### SIE is not Safelytic-only

Nothing in `app/intelligence/` (the core data-intelligence package) or
its `safety_events` table is Safelytic-specific. `app/intelligence/adapters.py::DataSourceAdapter`
is the one abstraction boundary every source integrates through
(`validate`/`normalize`/`transform`/`ingest`) — `GenericJSONAdapter` is
the only adapter this milestone actually implements (the one the REST
API uses), but a future Safelytic-specific, CSV-column-mapping, or any
other source's adapter implements the same interface without any call
site above it changing. Any authorized external application —
Safelytic, another HSE platform, an ERP/HR/CMMS system, an IoT/sensor
feed, an audit platform, or a custom integration — connects the same
way, through the same versioned REST API, and never needs direct
database access (milestone item 37).

### Canonical safety event model

One table, `safety_events` (`app/models/safety_event.py`), spans all
eleven data domains the milestone names — incidents, near misses, safety
observations, inspections, audits, corrective actions, permits, training,
workforce, equipment, and environmental conditions — via `event_type`/
`event_subtype` (plain, extensible strings, not a closed native-enum
column) plus a flexible `attributes` JSON column for whatever
domain-specific structured fields that type needs (e.g.
`{"hours": 10000}` for a workforce exposure record,
`{"equipment_id": "...", "failure_type": "..."}` for equipment). This is
deliberately **not** one specialized table per domain — the milestone's
own instruction: *"Do not create dozens of highly specialized tables
unless there is a clear need... the model must remain extensible."*
Adding a new subtype, or even a new domain, never requires a migration.

`event_type`/`severity`/`status`/`data_quality_status` are Python-side
validated vocabularies (`app/intelligence/enums.py`) but plain, indexed
`String` database columns — the same choice already made for
`OrganizationMembership.role` (see `app/services/permissions.py`), and
deliberately avoiding a repeat of migration 0005's enum-type-creation
defect (see "Known gaps" below) for a vocabulary expected to evolve
without a migration.

### External data ingestion

    external system -> DataSourceAdapter.validate() -> .normalize()
        -> .transform() -> .ingest() -> SafetyEventIngestionService -> SafetyEvent row

`POST /api/v1/intelligence/events` (single) and
`POST /api/v1/intelligence/events/batch` (batch, up to 1000 records) are
the two ingestion endpoints. Batch ingestion processes each record inside
its own database savepoint (`db.begin_nested()`), so **one malformed
record can never corrupt or abort the rest of the batch** (milestone item
38) — the response reports created/updated/skipped/rejected counts and a
per-record result (outcome, data-quality status, validation issues).

### Machine-client authentication

External systems authenticate as a **machine client**
(`ApiClient` — `app/models/api_client.py`), not as a human user — the
development-mode `X-SIE-Dev-User-Id` header (`app/api/deps_auth.py`) is
explicitly documented as unfit for production and is never accepted by
the ingestion endpoints (`app/api/deps_machine_auth.py`). A machine
client is:

  * organization-associated (one client belongs to exactly one
    organization; its credential can never write another organization's
    data)
  * scoped explicitly at creation time (`app/services/permissions.py::Permission`
    values, e.g. `safety_data:write`) — never inherited from a human
    role, and never wider than what was granted
  * authenticated via `Authorization: Bearer <client_id>:<secret>`,
    where `<secret>` is a long (`secrets.token_urlsafe(32)`), high-entropy,
    SIE-generated value — **never a human-chosen password**
  * hashed at rest with sha256 (see `app/services/api_client_service.py`'s
    own docstring for why a slow password-hashing KDF like bcrypt/scrypt
    is unnecessary here: the secret's entropy, not hash speed, is what
    protects it), verified with `secrets.compare_digest()` (constant-time)
  * rotatable and revocable — `POST .../api-clients/{id}/rotate` /
    `.../revoke`, both audited

The raw secret is shown to the caller **exactly once**, at
creation/rotation time, and is never stored, logged, or retrievable
again — only `secret_prefix` (a short, safe-to-display fragment)
persists for identification afterward.

### Idempotent ingestion

A record's identity is `(organization_id, source_system,
source_record_id)` — `safety_events`'s own `UniqueConstraint`. Resending
the identical record is a genuine no-op
(`IngestionOutcome.SKIPPED_IDEMPOTENT`, detected by comparing a sha256
content hash of the normalized payload — no duplicate row, no wasted
write); resending the same record with different content updates the
existing row in place (`UPDATED`). A record repeated *within the same
batch* is flagged `duplicate_in_batch` on its own result rather than
silently creating two rows.

### Data quality framework

Every stored record carries `data_quality_status`
(`app/intelligence/enums.py::DataQualityStatus`):

  * `VALID` — no issues.
  * `PARTIAL` — a non-blocking issue (e.g. an unrecognized severity
    value) — still stored, still used in analytics, the issue visible.
  * `QUARANTINED` — a blocking issue (e.g. missing/unparseable
    `event_time`, an impossible date or duration) — **still stored**
    (milestone item 12: "do not silently 'fix' questionable data"), but
    excluded from every feature/indicator/signal calculation.
  * A payload missing its minimum identity fields (`source_system`,
    `source_record_id`, `event_type`) is `REJECTED` — no row is written
    at all; there is nothing to deduplicate or classify.

Validation (`app/intelligence/validation.py`) is a small set of
deterministic rules — never machine learning, never a "confidence"
score. Normalization (`app/intelligence/normalization.py`) never
destroys the original value: `SafetyEvent.source_value` always preserves
exactly what was received, alongside the normalized fields.

**Data quality, risk, and (future) prediction confidence are three
distinct concepts, never collapsed into one field or score** (milestone
item 13) — a record can be `data_quality_status=PARTIAL` while
describing a `severity=CRITICAL` event; nothing in this codebase implies
otherwise.

### Provenance

    RiskSignal -> supporting_event_ids -> SafetyEvent.id
        -> SafetyEvent.source_system / source_record_id (external record)
        -> SafetyEvent.source_value (original payload, preserved)
        -> SafetyEvent.ingestion_batch_id (one ingestion call's records)
        -> SafetyEvent.normalization_version / schema_version

Every `FeatureValue` and `RiskSignal` carries `source_event_ids` — the
actual `SafetyEvent.id`s that produced it (capped at 50 for payload
size) — so a later question ("what evidence produced this signal?") is
always answerable down to the original source record, exactly the same
"stable citation, full provenance chain" principle already established
for [Evidence-Grounded RAG](#evidence-grounded-rag)'s citations.
`ingestion_batch_id` is a plain UUID column (one per ingestion call), not
a foreign key into a separate batch-tracking table — batch-level
statistics are computed on demand by aggregating `safety_events`,
avoiding a second, easily-inconsistent table for something this
codebase can already answer by querying the one it has (the same
"don't add a table you can compute from instead" judgment call already
made for RAG request audit metadata reusing `AuditLog`).

### Temporal integrity — no future information may leak into a historical feature

`app/intelligence/temporal.py::events_as_of()` is the **one and only**
query builder every feature/indicator/trend/anomaly/signal calculation
in this codebase uses to fetch `SafetyEvent` rows. It filters on
`event_time <= as_of`, and — by default — also on `ingestion_time <=
as_of`: a record that *happened* before `as_of` but was only *reported
or ingested* afterward (a backdated report) would not actually have been
knowable at that historical moment either, so it is excluded too unless
a caller explicitly opts into the more lenient event-time-only check.
Centralizing this in one function, rather than letting each feature
write its own filter, makes a leakage bug in a *new* feature
structurally hard to introduce — and lets one regression test
(`tests/test_temporal_leakage.py`) protect every caller at once. Data
quality is filtered here too: `QUARANTINED`/`INVALID` records never
reach a feature calculation.

### Analytical windows and exposure normalization

Configurable windows (7/30/90/365 days by default,
`settings.INTELLIGENCE_ANALYTICAL_WINDOWS_DAYS`) — never hard-coded per
call site. Where exposure data exists (`WORKFORCE`/`EXPOSURE_HOURS`
events — represented as ordinary `SafetyEvent` rows, not a second table),
raw counts are normalized into rates per 100,000 hours
(`app/intelligence/exposure.py`): **10 incidents in 10,000 hours and 10
incidents in 500 hours never report the same rate.** When no exposure
data exists at all, the rate is reported as the explicit
`EXPOSURE_DATA_UNAVAILABLE` sentinel — never a fabricated or silently
misleading number.

### Feature engineering

`app/intelligence/features.py::compute_feature_set()` is a pure function
over an already-fetched, already-point-in-time-filtered event list (plus
an already-computed exposure figure) — trivially unit-testable, and the
only place point-in-time correctness can be gotten wrong stays
`events_as_of()`, not each feature. ~20 deterministic features: event
frequency (incident/near-miss/observation/audit/inspection counts),
severity (average severity, high-potential event count, severe event
count), corrective actions (open/overdue counts, closure rate, recurring
count), training (expired certification count, completion rate,
competency gap count), equipment (overdue inspection count, failure
count, maintenance-overdue count), operational context (contractor
activity count, activity diversity, location concentration), and
exposure-normalized rates. Every `FeatureValue` records its name, value,
window, `as_of`, `source_event_ids`, `calculation_version`
(`feature-v1`), and a `data_quality` label — a feature whose value
depends on a denominator that doesn't exist (a rate with nothing to
divide by) reports `value=None` with an explicit `unavailable_reason`,
never a misleading `0`; a legitimately-zero *count* stays a real,
meaningful `0`.

### Indicators, trends, and anomaly detection

**Indicators** (`app/intelligence/indicators.py`) are a thin,
labeling-only layer over features — `LAGGING` (incident count, severe
event count, incidents per 100,000 hours) measures outcomes already
realized; `LEADING` (near-miss count, observation count, overdue action
count, inspection count, training completion rate) measures activity
believed to precede outcomes. Neither is ever presented as a predictive
probability.

**Trend analysis** (`app/intelligence/trends.py`) is ordinary
least-squares linear regression over period-bucketed values, classified
against a relative-slope threshold (`settings.INTELLIGENCE_TREND_SLOPE_THRESHOLD`)
— `INCREASING`/`DECREASING`/`STABLE`/`INSUFFICIENT_DATA` (fewer than
`settings.INTELLIGENCE_TREND_MIN_PERIODS` non-empty periods). Documented,
not hidden, and deliberately relative rather than absolute, so small
fluctuations around a large baseline don't get overfit into a false
trend.

**Anomaly detection** (`app/intelligence/anomaly.py`) is a z-score
against a rolling baseline mean/population-standard-deviation — chosen
specifically for being fully explainable (every number in the result is
directly inspectable, nothing is a learned weight). No deep learning —
see the milestone's own instruction. A zero-variance baseline is handled
without dividing by zero (any deviation is anomalous; no deviation is
normal, `z_score=None` rather than fabricated).

**Correlation, never causation** (`app/intelligence/association.py`,
milestone item 26): a deterministic Pearson correlation over two aligned
series can only ever report `ASSOCIATION_OBSERVED` /
`NO_ASSOCIATION_OBSERVED` / `INSUFFICIENT_DATA` — there is no
`CAUSATION_CONFIRMED` outcome, and never will be. Observing that overtime
and incidents move together, however strongly, never establishes that
one causes the other.

### Risk signals

Five deterministic, rule-based signal types
(`app/intelligence/signals.py`, `calculation_version="risk-signal-v1"`):
`HIGH_POTENTIAL_EVENT_CLUSTER`, `OVERDUE_ACTION_SURGE`,
`EQUIPMENT_FAILURE_CLUSTER`, and `UNSAFE_OBSERVATION_SURGE` compare a
current-window count against a baseline (the mean of several preceding,
non-overlapping, same-length periods) via a fixed surge multiplier
(`settings.INTELLIGENCE_SIGNAL_SURGE_MULTIPLIER`) and a minimum absolute
count (`settings.INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT`);
`TRAINING_COMPLIANCE_DROP` compares the training-completion-rate feature
directly against a threshold (`settings.INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD`).
**A signal never fires from too little data** (milestone item 53): if the
underlying feature's own `data_quality` is `INSUFFICIENT_DATA`, no signal
is generated, regardless of what the raw arithmetic would say — a site
with one or two events, even if every one is severe, produces zero
signals. Every signal carries its observed period, affected entity,
`supporting_features`, `supporting_event_ids`, `data_quality`, and
`calculation_version` — never called a prediction, never a probability.

### Entity-level analysis

Every analytics function accepts an `entity_type`/`entity_id` pair
(`organization` by default, or `site` when `site_id` is supplied) —
`app/intelligence/temporal.py::events_as_of()` filters by it directly.
Nothing in this architecture assumes "organization" is the only
analytical level; project/department/contractor/activity/equipment/shift
filtering follows the same shape and can be added without a redesign.

### Data sufficiency and freshness

`app/intelligence/sufficiency.py::classify_data_sufficiency()`:
`SUFFICIENT_DATA` (>= `settings.INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS`,
default 10), `LIMITED_DATA` (>=
`settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS`, default 3), otherwise
`INSUFFICIENT_DATA` — a site with three days of data is never compared,
unqualified, to one with three years.

`app/intelligence/reliability.py::compute_source_reliability()` reports,
per source system connected to an organization: record counts by data-
quality status, the latest event/ingestion time, and `is_stale` (latest
ingestion older than `settings.INTELLIGENCE_FRESHNESS_THRESHOLD_DAYS`,
default 7 days) — analytics never silently present stale data as
current.

### Tenant isolation and privacy

Ingestion trusts only the authenticated `ApiClient`'s own
`organization_id` — there is no client-supplied `organization_id` field
on the ingestion request body at all, so there is nothing for a
malicious or buggy caller to spoof. Every read endpoint requires
`organization_id` as an explicit, authorized query parameter
(`intelligence:read`), the same authenticate-then-authorize-then-pass-a-
trusted-value shape already established for retrieval/RAG — there is no
second tenant-isolation mechanism. `events_as_of()` itself always filters
on `organization_id` as part of its one shared query — verified
end-to-end (through the full HTTP API, not only at the service layer) in
`tests/test_intelligence_api.py`.

Safety data can carry sensitive employee information. `SafetyEvent.description`
and any `attributes` key listed in
`settings.INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS` (employee name/id,
medical details, disciplinary action, by default) are classified as
sensitive (`app/intelligence/privacy.py`): never included in any
feature/signal/analytics output (those only ever carry counts, rates,
and `source_event_ids` — never event content), and never logged verbatim
unless a deployment explicitly opts in
(`LOG_INTELLIGENCE_EVENT_DESCRIPTION`, default off). This is a
classification/exclusion mechanism, not encryption or field-level access
control — those remain future work if a deployment needs them.

### Audit and observability

Ingestion (single and batch, one summary entry per batch rather than one
per record), analytics queries, and API-client lifecycle events (create/
rotate/revoke) are all recorded via the *existing* `AuditService`/
`AuditLog` — no new database table for this milestone either. Audit
metadata is always shape/outcome/counts/identifiers — never a raw
`description`, raw `attributes`, or full `source_value` payload.

### Future predictive-model interface

`app/intelligence/predictive_model.py::PredictiveModel` documents the
eventual interface (`fit`/`predict`/`explain`) and `Prediction`'s target
output shape (`risk_score`, `probability`, `feature_snapshot`,
`explanation`, `supporting_signals`, ...) — **no model is trained or
implemented, and no API route calls `predict()`.**
`NullPredictiveModel` is the one concrete implementation, and it
deliberately raises `NotImplementedError`, proving the interface is
wired and testable without ever fabricating a number that could be
mistaken for a real prediction (milestone item 29). The explainability
chain the milestone requires (`Prediction -> Model -> Feature snapshot ->
Feature values -> Source events`) is already fully wired for everything
below the model itself — a future model only has to plug into it.

### What this milestone deliberately does not do

No sophisticated predictive ML, no accident/injury probability, no model
training or fine-tuning pipeline, no reinforcement learning, no
autonomous or tool-using agents, no external web search/crawling, and
**no automated safety decisions** — this codebase never stops equipment,
suspends workers, blocks permits, issues disciplinary actions, notifies
regulators, closes actions, or makes a compliance decision on its own.
SIE provides intelligence; humans remain responsible for decisions.

### Genuine limitations

  * **Signal/trend/anomaly thresholds are documented initial defaults**,
    not statistically validated against real incident data — the same
    "not scientifically validated" caveat this codebase already carries
    for its retrieval/RAG thresholds.
  * **The surge-detection heuristic in `app/intelligence/signals.py` is
    a fixed multiplier over a short baseline**, not a general-purpose
    statistical process-control method — it will need real deployment
    data to tune responsibly.
  * **No persisted feature/signal history.** Features and signals are
    computed on demand, synchronously, from `safety_events` directly —
    correct and fully explainable for this milestone, but there is no
    materialized feature store yet for point-in-time historical
    backtesting at scale; introducing one (and the async
    ingestion-worker evolution `app/intelligence/ingestion_service.py`
    is already shaped to support) is future work.
  * **Entity resolution across source systems is not implemented** — two
    systems spelling the same contractor's name differently are treated
    as two different contractors; `app/intelligence/normalization.py`
    deliberately does not attempt to reconcile this (milestone item 14:
    "do not destroy source values").
  * **No per-organization retention policy enforcement** — see the
    milestone's own instruction not to implement automatic deletion yet;
    organizations may eventually require different retention rules for
    raw source records, normalized records, features, and audit logs,
    and none of that is built here.

## Predictive Intelligence Architecture

    SafetyEvent (point-in-time filtered, app/intelligence/temporal.py)
        -> FeatureSnapshot (app/predictions/feature_snapshot_service.py)
           -- versioned, persisted, immutable, auditable --
        -> LabelResult (app/predictions/labels.py)
           -- built independently from FeatureSnapshot; never a feature --
        -> TrainingExample (app/predictions/dataset.py)
        -> chronological train/validation/test split (app/predictions/temporal_split.py)
        -> LogisticRegressionModel (hand-rolled; app/predictions/logistic_regression.py)
        -> evaluation (Recall/Precision/PR-AUC first; app/predictions/metrics.py)
        -> walk-forward backtest (app/predictions/walk_forward.py)
        -> ModelRegistryEntry (TRAINED; app/predictions/model_registry.py)
        -> [human review: VALIDATED -> APPROVED -> DEPLOYED]
        -> predict_as_of() (app/predictions/predictor.py)
        -> Prediction (PREDICTED or NO_PREDICTION; app/models/prediction.py)
        -> explain_prediction() (app/predictions/explain.py)

This is the Predictive Risk Modeling Specification v0.1 milestone —
before implementing any predictive ML, it establishes a rigorous,
auditable specification (`app/predictions/spec.py`) answering what
exactly SIE predicts, for what unit, over what horizon, from what
information, and when it must refuse to answer — and only then builds
the pipeline that specification requires. **Per the milestone's own
boundary, only a prototype baseline model is trained here, on synthetic
data — this milestone does not claim production predictive
performance.**

### The specification (`app/predictions/spec.py`)

Every other module in `app/predictions/` implements a decision this one
module documents and versions — nothing below re-derives or silently
redefines these:

* **Target: Elevated Safety Event Risk.** Whether a site experiences at
  least one qualifying `INCIDENT` within the horizon. Evaluated against
  the existing data model before being chosen (`SafetyEvent` already
  carries `event_type`/`event_time`/`site_id`/`organization_id` with
  proven temporal-integrity guarantees); no other candidate target
  (severity prediction, contractor attribution, time-to-next-incident) is
  as well supported by what this codebase reliably captures today. Only
  this one target is implemented (`PREDICTION_TARGET_VERSION`).
* **Prediction unit: Site.** `SafetyEvent.site_id` is a real, populated
  foreign key and the natural granularity at which "elevated risk" is
  operationally actionable — a site manager can act on it.
* **Horizon: 30 days**, with exact inclusive/exclusive semantics —
  `horizon_start = as_of` (**exclusive**, `event_time > as_of`),
  `horizon_end = as_of + 30 days` (**inclusive**, `event_time <= horizon_end`).
* **Target definition never conflates report types.** Only a recorded
  `INCIDENT` (with `data_quality_status` `VALID`/`PARTIAL`) qualifies —
  never a `NEAR_MISS` or `OBSERVATION` (those are *leading-indicator
  features*, see below, precisely because using them as the target
  itself would conflate "an incident happened" with "something was
  reported"). A `QUARANTINED`/`INVALID` future record never flips the
  label either way.
* **Reporting bias is documented, not assumed away.** More near-miss/
  observation reports can mean conditions worsened *or* that reporting
  culture improved — this codebase never presents leading-indicator
  activity as a direct risk measurement, only as a predictor on a
  documented hypothesis (`REPORTING_BIAS_NOTE`).

### Deterministic label generation — never a feature

    generate_label(organization_id, site_id, as_of, horizon_days)
        -> SafetyEvent rows strictly after as_of, within the horizon
        -> LabelResult(label: 0 | 1, supporting_event_ids)

`app/predictions/labels.py::generate_label()` is a pure, deterministic
function of future events — and it is the *only* module in this package
allowed to look past `as_of`. **Feature/label separation is
non-negotiable**: `app/predictions/feature_snapshot_service.py` never
calls it, never reads its output, and never reads any event with
`event_time > as_of`; `LabelResult.supporting_event_ids` exists purely
for audit/evaluation, never as a model input. This separation has a
dedicated regression test (`tests/test_feature_label_separation.py`)
proving a feature vector is byte-for-byte unchanged by adding or removing
future label-window events, and vice versa — plus four additional,
milestone-mandated temporal-leakage regression tests
(`tests/test_predictive_temporal_leakage.py`) covering a future incident
never entering a snapshot, a backdated (late-ingested) report being
excluded, a label never counting an at-or-before-`as_of` event, and a
backtested prediction being unaffected by events inserted after its
`as_of`.

### Versioned, persisted feature snapshots

    compute_feature_set_v1(organization_id, site_id, as_of)
        -> app.intelligence.features.feature_engineering_service.compute()
           at 7d / 30d / 90d windows (reused unchanged)
        -> app.intelligence.trends.classify_trend() / app.intelligence.anomaly.detect_anomaly()
           (reused unchanged)
        -> FeatureSetV1 -> FeatureSnapshot (persisted, immutable)

`FeatureSnapshot` (`app/models/feature_snapshot.py`) is what makes a past
prediction reproducible and auditable months later: one row per
`(organization_id, entity_type, entity_id, as_of, feature_set_version)`
— idempotent (`get_or_build_feature_snapshot()` reuses an existing row
rather than recomputing/duplicating one), and never mutated once written.
Every value is a uniform `SnapshotFeature` (value, data quality,
calculation version, source event ids, an explicit
`unavailable_reason`) regardless of whether the underlying computation
was a count, a rate, a trend direction, or an anomaly status — so the
whole snapshot stays one flat, JSON-serializable dict. **A feature this
module cannot reliably compute keeps `value=None` with an explicit
reason — never fabricated as `0` unless `0` is the real, computed
answer** (a genuine zero incident count is a real, meaningful value, not
missingness).

`FEATURE_SET_V1` (`app/predictions/vectorization.py::FEATURE_NAMES`)
composes counts/rates (`incident_count_7d/30d/90d`, `near_miss_count_30d`,
`observation_count_30d`, `overdue_action_count_30d`,
`overdue_action_rate`, `work_hours_30d`, `incidents_per_100000_hours`,
`severe_event_count_90d`, `high_potential_event_count_90d`,
`equipment_failure_count_90d`, `overdue_equipment_inspection_count`,
`training_compliance_rate`, `expired_training_count`,
`action_closure_rate`), trend directions
(`incident_trend`/`near_miss_trend`/`observation_trend`), and anomaly
statuses (`incident_anomaly`/`equipment_failure_anomaly`) — every one
built entirely from the already point-in-time-safe
`app/intelligence/` modules from the prior milestone; no new temporal
filtering logic exists anywhere in `app/predictions/`.

### Model input: no fabricated feature values

`app/predictions/logistic_regression.py::FeaturePreprocessor` converts
the feature snapshot's `dict[str, float | None]` into the numeric vector
a linear model needs — but never by silently treating a missing value as
`0`. A missing feature is imputed with the **training split's own mean**
(computed once, at `fit()` time, only from training-partition data — never
from validation/test data, which would leak split information) **and** a
companion missingness-indicator column is added per feature, so the
model can still learn from the fact that a value was unavailable rather
than have that information silently disappear. `explain.py`'s
contribution accounting includes both terms, so a missing feature's real
effect on a prediction is never under-reported.

### Chronological splitting and walk-forward backtesting

`app/predictions/temporal_split.py::chronological_split()` splits on the
**sorted, distinct set of `as_of` dates** — never a random row-level
split, and no `as_of` date is ever split across two partitions (every
example sharing one `as_of`, across every site, lands in the same
partition) — so every training `as_of` precedes every validation `as_of`,
which precedes every test `as_of`.
`app/predictions/walk_forward.py::walk_forward_backtest()` goes further:
train on everything up to a rolling cutoff, evaluate on the next slice,
advance, repeat — proving the pipeline generalizes across many rolling
future periods, not just one split. Implemented to prove the
architecture works, not tuned to a benchmark: every fold's raw metrics
are returned individually, a fold with a single-class training set is
explicitly marked `skipped_reason="SINGLE_CLASS_TRAIN_SET"` rather than
silently fit, and nothing here adjusts hyperparameters based on backtest
results.

### Evaluation — Recall/Precision/PR-AUC first, never accuracy

`app/predictions/metrics.py` computes precision, recall, F1, PR-AUC,
ROC-AUC, Brier score, and calibration bins entirely in pure Python (no
`sklearn.metrics`) — **accuracy is never computed at all**, consistent
with the milestone's instruction that it is not a meaningful headline
metric under the class imbalance a rare safety-event target produces.
Every metric that is mathematically undefined for the data at hand
(PR-AUC/ROC-AUC need both classes present; a rate needs a non-zero
denominator) is reported as an explicit `None`, alongside `sample_size`/
`positive_count` so *why* is always inspectable — never a placeholder
number. `evaluate_by_data_quality()` reports every metric **separately**
for sufficient- and limited-data entities (never one pooled number that
hides how much of the apparent performance came from data-rich sites) —
`training.py` calls this for the train/validation/test split of every
trained model.

### The hand-rolled logistic regression baseline

`app/predictions/logistic_regression.py::LogisticRegressionModel` —
gradient descent with L2 regularization, implemented in pure Python.
**Deliberately not scikit-learn/numpy** (neither is a declared
dependency of this project, even though both happen to be importable in
this sandbox) and **deliberately not a neural network, LSTM,
transformer, or large ensemble** — the milestone rules those out
explicitly, and a linear model's coefficients are what make
`explain.py`'s "contributing feature" output honest and auditable. A
second model (Gradient Boosting) was designed for in the spec but is not
implemented — nothing in this milestone needed it to prove the pipeline.

### The minimal model registry — human review, never auto-promotion

    create_model_entry() -> TRAINED
        -> mark_validated() -> VALIDATED
        -> approve()        -> APPROVED
        -> deploy()         -> DEPLOYED  (retires any previously deployed
                                           model for the same organization
                                           + entity type)
        -> retire() / reject() -> RETIRED / REJECTED (terminal)

`ModelRegistryEntry` (`app/models/model_registry_entry.py`) is one table,
not MLflow — everything needed to reproduce, audit, and govern one
trained model version: model/training-data/feature-set/label-definition
versions, the exact training/validation/test date ranges, hyperparameters,
metrics, and the trained parameters themselves (coefficients, intercept,
feature means/stdevs — enough to reconstruct the model for prediction or
explanation without retraining). **Training only ever produces a
`TRAINED` row** (`app/predictions/training.py` calls
`create_model_entry()` and nothing else) — every later transition is a
separate, explicit, audited call in `app/predictions/model_registry.py`,
enforcing `app/predictions/enums.py::is_allowed_transition()`
(`InvalidModelTransitionError` on anything not in the allowed-transition
table). `organization_id` is required — one model is always trained on,
and only ever serves, exactly one organization's own data; there is no
pooled cross-tenant model anywhere in this milestone. A model is **never
overwritten**: every training run creates a new `model_version`
(`v1`, `v2`, ...), and old rows are retained (`RETIRED`, never deleted).

### No fake probabilities — calibration-gated exposure

`Prediction.probability` (`app/models/prediction.py`) is populated
**only** when the serving model's `ModelRegistryEntry.calibration_validated`
is `True` — a flag that defaults to `False` and is set only by an
explicit `mark_validated(calibration_validated=...)` call, never assumed.
Whenever it is `False`, a prediction still carries a `risk_score` and a
categorical `risk_category` (`ELEVATED`/`MODERATE`/`LOW`/
`INSUFFICIENT_DATA`, threshold-based —
`app/predictions/spec.py::ELEVATED_RISK_THRESHOLD`/
`MODERATE_RISK_THRESHOLD`) — never an uncalibrated score dressed up as an
interpretable probability like "73% accident probability."

### Explainability — contributing features, never causes

`app/predictions/explain.py::explain_prediction()` exploits the model's
own linearity: each feature's contribution to one prediction is exactly
`weight * standardized_value` (plus the missingness-indicator term, see
above) — no separate black-box explainer needed. Every result is
described as a **"contributing feature"** with a **"model association"**
to the prediction — the disclaimer and every per-feature note explicitly
state this is not a causal claim (`tests/test_predictions_explain.py`
asserts the word "causes" never appears in an affirmative sense).

### Mandatory abstention — never a forced prediction

    predict_as_of(organization_id, site_id, as_of, model)
        -> entity/model-governance checks    -> NO_PREDICTION, or continue
        -> historical sufficiency (cold start) -> NO_PREDICTION, or continue
        -> staleness check                     -> NO_PREDICTION, or continue
        -> feature snapshot data-sufficiency    -> NO_PREDICTION, or continue
        -> score -> PREDICTED

`app/predictions/predictor.py::predict_as_of()` is the single function
both live serving and internal backtesting use (it takes `as_of` as an
explicit parameter and never reads "now" internally) — the live
Predictions API always calls it with `require_deployed=True` (only a
`DEPLOYED` model ever serves a live prediction), while backtesting calls
it with `require_deployed=False` against a merely-`TRAINED` model.
`Prediction.outcome` is `NO_PREDICTION` with a specific
`AbstentionReason` (`COLD_START`, `INSUFFICIENT_HISTORICAL_DATA`,
`STALE_SOURCE_DATA`, `REQUIRED_FEATURES_MISSING`, `UNSUPPORTED_ENTITY`,
`MODEL_NOT_VALIDATED`/`MODEL_NOT_APPROVED`/`MODEL_UNAVAILABLE`) whenever a
prediction cannot be trusted — an abstention is itself a real, audited,
persisted outcome, never an exception the caller has to catch and never
skipped silently.

### Full provenance, tenant isolation, and input security

    Prediction -> model_id -> ModelRegistryEntry
               -> feature_snapshot_id -> FeatureSnapshot
                                       -> features[*].source_event_ids -> SafetyEvent
                                                                        -> source_system / source_record_id

Every step is a real foreign key, inspectable directly — nothing
summarized away. `POST /api/v1/intelligence/predictions` /
`GET /api/v1/intelligence/predictions/{entity_id}` verify authorization
(`prediction:read`), confirm the requested site actually belongs to the
authenticated organization (a 404, not a 403, for a cross-tenant id —
never revealing whether it exists elsewhere), resolve the organization's
own `DEPLOYED` model, and build the feature snapshot server-side, at
request time, from that organization's own data. **The request schema
(`PredictionRequest`) has no field for a client-supplied feature value,
risk score, or label at all** — only `entity_id` and an optional `as_of`
— so there is nothing for a client to inject; a mandatory
cross-tenant-isolation regression test suite
(`tests/test_predictive_cross_tenant_isolation.py`) proves org A's
features, labels, training, deployed-model lookup, and served
predictions are all unaffected by org B's data, even when both share
matching site names and identical `as_of` timestamps.

### Human oversight and safety language — non-negotiable

This system never automatically disciplines, terminates, or suspends a
worker, stops equipment, blocks a permit, issues a regulatory report, or
declares a person unsafe — nothing in `app/predictions/` calls any such
action, and no protected personal characteristic is ever a feature.
Every prediction response carries a fixed safety-language note
(`app/predictions/spec.py::SAFETY_LANGUAGE_NOTE`): *"This is a model
estimate, not a certainty. The model identifies elevated risk of a
qualifying safety event within the horizon based on available historical
data — it does not predict that an accident will occur."*

### Prototype model — synthetic data only

`app/predictions/training.py::train_baseline_model()` exists to prove
the complete pipeline is wired correctly end to end, per the milestone's
own boundary ("unless necessary to prove the architecture, do not train
a production predictive model in this milestone"). Every model it
produces carries `PROTOTYPE_MODEL_LABEL` in `ModelRegistryEntry.notes` —
*"Prototype Model — Synthetic Data... has NOT been validated against
real-world data and must never be described as production predictive
intelligence."* The synthetic dataset used to prove it
(`tests/fixtures/predictions/synthetic_training_dataset.py`) spans two
organizations, multiple sites, and roughly two years with a deliberate,
known LOW → ELEVATED → LOW incident-risk regime change — it demonstrates
the pipeline is technically sound, not that any resulting model has real
predictive validity.

### What this milestone deliberately does not do

No production model training or deployment, no deep learning/neural
networks, no autonomous predictions or automated interventions,
no worker-level risk scoring, no external web intelligence, and no
automated safety decisions of any kind. Model monitoring/drift-detection
was named here as explicit future work only — it is now built, in the
next milestone; see
[Predictive Model Validation & Governance Architecture](#predictive-model-validation--governance-architecture)
below.

## Predictive Model Validation & Governance Architecture

    DatasetVersion (SYNTHETIC | REAL, versioned, immutable)
        -> validate_dataset()          -- structured, multi-field DataQualityReport (never one score)
        -> check_minimum_requirements() -- SUFFICIENT | INSUFFICIENT_DATA (INITIAL GOVERNANCE DEFAULT thresholds)
        -> train_model()                -- Logistic Regression (hand-rolled) OR Gradient Boosting (scikit-learn)
        -> walk-forward evaluation, calibration, stability, error analysis -- identical methodology for both models
        -> ModelRegistryEntry(TRAINED)
        -> [human review: VALIDATED -> APPROVED -> DEPLOYED -> RETIRED]     (never self-approved, never auto-promoted)
        -> prediction/outcome/drift monitoring -> ModelReviewFlag(MODEL_REVIEW_REQUIRED)  (never auto-retrains/redeploys)
        -> model card + governance validation report (APPROVE | REJECT | REVIEW recommendation)

This is the Predictive Model Validation & Governance v0.1 milestone. Its
purpose is **not** to claim the Predictive Risk Modeling Specification
v0.1 baseline is accurate — it is to determine whether a model is
*trustworthy enough to responsibly deploy*: technically valid,
statistically defensible, sufficiently calibrated, stable across time and
data conditions, explainable, tenant-safe, data-quality aware,
monitorable, and governable. **Nothing in this milestone optimizes a
model to get a better metric, and nothing here trains a production model
on real data — every dataset committed to this repository remains
synthetic** (see "Real-data readiness" below for what *is* built so an
organization can supply real data at runtime).

### Dataset versioning — SYNTHETIC and REAL, never mixed silently

`DatasetVersion` (`app/models/dataset_version.py`,
`app/predictions/dataset_registry.py`) is the one place a predictive
dataset gets an identity: `dataset_id`, an auto-incremented
`dataset_version` (`v1`, `v2`, ... — never reused, never overwritten),
`environment` (`SYNTHETIC` or `REAL`, always explicit, never inferred or
defaulted), `organization_id`, `source_systems`, `date_range_start/end`,
`feature_set_version`, `target_version`, `prediction_horizon_days`, and
`created_at`. `register_synthetic_dataset()` and `register_real_dataset()`
are the only two entry points anything calls — both simply pin
`environment` before forwarding to `register_dataset()`, so there is no
code path that creates a dataset record without an explicit environment
tag. Every dataset version's own `quality_report` (see below) is
persisted alongside it, so a model trained from that version is
reproducible: `build_training_examples_for_dataset_version()`
deterministically reconstructs the exact `(site_ids, as_of_dates)` a
`DatasetVersion` implies from its own recorded organization/date-range/
horizon, rather than depending on any external caller state.

### Real-data readiness — infrastructure, not a real dataset

**No real confidential organizational data is committed to this
repository — every test fixture is synthetic.**
`register_real_dataset()` is the infrastructure an organization uses to
have SIE validate and version *its own* real data at runtime: it reads
whatever `SafetyEvent` rows that organization has already ingested
through the existing, generic API/batch ingestion pipeline
(`app/intelligence/ingestion_service.py`, from the Intelligence &
Predictive Analytics Foundation milestone) — it never accepts a raw file
or bulk payload itself, and nothing in `app/predictions/` writes real
event content to disk or to a fixture file. The only thing this module
persists about real data is *metadata* (counts, date ranges, a quality
report) — never the underlying event content, and `source_systems` is
required and validated non-empty for `REAL` (never defaulted to a
synthetic-fixture label the way `SYNTHETIC` is). This milestone does not
claim any real organization has supplied data yet — it claims the path
exists and is exercised by tests using synthetic events tagged `REAL` to
prove the environment-tagging and quality-report machinery itself is
correct, never to claim real-world validation occurred.

### Real-data validation — a structured report, never one score

    validate_dataset(organization_id, site_ids, date_range_start, date_range_end, as_of, thresholds)
        -> DatasetQualityReport(
               record_count, valid/partial/quarantined/invalid_count, duplicate_record_count,
               completeness: CompletenessReport (missing_site_rate, missing_severity_rate,
                              sites_with_no_exposure_records, missing_exposure_rate),
               freshness:    FreshnessReport (latest_event_time, latest_ingestion_time,
                              staleness_days, is_stale),
               distribution_notes: [...],
               overall_quality: GOOD | LIMITED | INSUFFICIENT,
           )

`app/predictions/data_validation.py::validate_dataset()` **never modifies
or discards a questionable record** — every check (completeness,
consistency, duplication, temporal integrity, freshness, distribution
anomalies) is read-only, and a record already `QUARANTINED`/`INVALID` by
the ingestion pipeline stays exactly as ingestion classified it; this
module only reports. `DatasetQualityReport` is deliberately a structured,
multi-field object — `to_dict()` never collapses it into one number a
caller could rubber-stamp. `overall_quality` is a coarse read of that
structure for the minimum-data gate below, not a replacement for reading
the individual fields. `duplicate_record_count` reflects that
`SafetyEvent`'s own `(organization_id, source_system, source_record_id)`
unique constraint already rejects true intra-organization duplicates at
the database level (`test_true_intra_organization_duplicates_are_rejected_at_the_database_level`)
— the field exists as defense-in-depth for any future, looser-guarantee
ingestion path, not because it is reachable through this schema today.

### Minimum data requirements — INSUFFICIENT_DATA, not a silently-trained model

`app/predictions/data_requirements.py::check_minimum_requirements()`
checks a dataset against `DataSufficiencyThresholds` — historical span,
number of sites, positive-label count, number of distinct prediction
windows, exposure-hours coverage, record completeness — **every field is
explicitly documented "INITIAL GOVERNANCE DEFAULT", never claimed as a
universal or industry-validated threshold**, and every field is
override-able per call. `POST /api/v1/intelligence/models/train` runs
this check before training anything: a dataset that fails returns
`422 MODEL_VALIDATION_STATUS=INSUFFICIENT_DATA` with the specific failed
checks named — never a model silently trained on too little data.

### Two comparison models, one identical methodology, neither auto-selected

`app/predictions/training.py::train_model()` trains **either** Logistic
Regression (`app/predictions/logistic_regression.py`, hand-rolled, from
the prior milestone) **or** Gradient Boosting
(`app/predictions/gradient_boosting.py`, via scikit-learn's
`GradientBoostingClassifier`) — chosen by the caller, never both fused —
against the **exact same** feature set, labels, `FeaturePreprocessor`
(mean-imputation + missingness-indicator columns, so both models see
identical missing-data handling), chronological train/validation/test
split, and evaluation methodology. **Gradient Boosting is the one
deliberate, fully-documented exception to this project's otherwise
consistent no-heavy-ML-dependency policy** — `scikit-learn`/`numpy`/
`scipy` are declared in `requirements.txt` for this reason only, per this
milestone's own explicit instruction to prefer an established, well-
maintained library for gradient boosting specifically rather than
hand-roll it; the Logistic Regression baseline remains pure Python.
Because a fitted sklearn ensemble has no honest lossless JSON
representation, `GradientBoostingModel.to_params()` serializes it as
pickle+base64 into the same JSON `parameters` column Logistic Regression
uses a plain weight list for — a deliberate, documented trade-off, never
hidden. `app/predictions/model_comparison.py` builds a side-by-side
report (precision/recall/PR-AUC/ROC-AUC, false positive/negative counts,
calibration, coverage/abstention rate, stability) for a human to read —
**it has no `pick_best_model()`/`select_best_model()` function at all**
(a dedicated test asserts neither exists as a module attribute); the only
way a specific model version ever gets deployed is the separate, human-
driven `approve()` → `deploy()` path described below.

### Calibration — "probability" only when it has been earned

`app/predictions/calibration.py::validate_calibration()` computes a
reliability curve (predicted-probability bins vs. observed event rate),
Brier score, and Expected Calibration Error (ECE — the count-weighted
average gap between each bin's predicted mean and its observed rate) on
the model's own held-out test split, at training time, and stores the
result on `ModelRegistryEntry.metrics["test"]["calibration"]` — never
recomputed from raw scores the API layer no longer has. The result is a
`PROBABILITY_STATUS` of `CALIBRATED` or `UNCALIBRATED`; `mark_validated()`
sets `ModelRegistryEntry.calibration_validated` from exactly this
status, and (as in the prior milestone) `Prediction.probability` is
populated **only** when that flag is `True` — otherwise a prediction
still carries a `risk_score`, described as a **"Model score"**, never
dressed up as a probability. The synthetic evaluation scenarios (below)
include datasets with known, approximately-engineered event frequencies
specifically to verify *directional* calibration consistency — this
milestone never claims statistical calibration validity from a small
synthetic sample, only that the calibration machinery itself computes
real, non-fabricated numbers.

### Configurable decision threshold — 0.5 is never assumed

`app/predictions/threshold.py` sweeps a configurable set of candidate
thresholds against a scored evaluation set and reports recall,
precision, false-negative rate, and false-positive rate at each one —
`select_threshold_by_recall_floor()` finds the lowest threshold meeting a
caller-supplied minimum recall, returning `None` (never a fabricated
answer) when no swept threshold reaches it. Nothing in this milestone
auto-selects or auto-applies a threshold to any deployed model; a
threshold choice is documented trade-off data for a human reviewer, not
a decision this code makes for them.

### Model stability — across time, sites, and data-quality categories

`app/predictions/stability.py` breaks recall/precision/PR-AUC down by
time period, site, and data-quality category and reports the resulting
variability (e.g., recall standard deviation across periods) rather than
one pooled number — a model that performs well in one period or one site
only is visible as such, never hidden inside an averaged headline metric.
`app/predictions/governance.py`'s approval criteria reads this
variability directly (`max_recall_variability_stdev`) as one of the
checks that can push a recommendation toward `REVIEW`.

### Error analysis — what the model misses, not just how often

`app/predictions/error_analysis.py` reports false negatives (predicted
normal, a qualifying incident occurred within the horizon) and false
positives (predicted elevated, none occurred) **as per-record detail**
(entity, `as_of`, data quality, score), not just an aggregate count —
consistent with this milestone's own instruction that *what kinds of
situations a model misses* matters more than the aggregate score, and
that a false positive is never automatically classified as useless (an
early warning that turns out to have no incident inside this particular
horizon is still potentially actionable safety information).

### Expanded walk-forward evaluation and six mandatory temporal-leakage tests

`app/predictions/walk_forward.py::walk_forward_backtest()` now returns a
`WalkForwardFold` per rolling window with explicit train/validation/test
periods, sizes, and metrics — each fold's own validation period becomes
the next fold's test period's predecessor, and the training window always
expands (`train = [start, cutoff]`, `cutoff += window_days`), matching
the milestone's own rolling-window example (train Jan–Dec 2024 / validate
Jan–Mar 2025 / test Apr–Jun 2025, then train Jan 2024–Mar 2025 / validate
Apr–Jun 2025 / test Jul–Sep 2025) — **future information never enters an
earlier training window.** `tests/test_predictive_temporal_leakage.py`
now enforces all six of the milestone's mandatory cases: a future event
never affecting a snapshot, a future-ingested (backdated) event being
excluded from a past `as_of`, a backdated event never retroactively
changing a past label, a target-window event never appearing as a
feature even though it can label, a model trained at `T` never using any
feature snapshot computed after `T`, and evaluating a model never
mutating or influencing its own training dataset.

### Reproducibility

Every trained `ModelRegistryEntry` records everything needed to
reproduce it without retraining: `dataset_version_id` (the exact
`DatasetVersion` it was built from), `feature_set_version`,
`prediction_target_version`, `label_definition_version`,
`training_data_version`, the exact `training_period`/`validation_period`/
`test_period` date ranges, `model_version`, and `hyperparameters` — on
top of the trained `parameters` themselves the prior milestone already
persisted. A model is **never overwritten**; every training run creates a
new, auto-incremented `model_version`.

### The extended model lifecycle — human approval, never self-approval

    create_model_entry() -> TRAINED
        -> mark_validated(calibration_validated=...)  -> VALIDATED
        -> approve(reviewer_user_id=...)               -> APPROVED   (writes a ModelApproval row)
        -> deploy()                                     -> DEPLOYED  (retires any previously deployed model)
        -> undeploy()                                   -> APPROVED  (pulled from serving, not retired)
        -> deploy()  [again]                             -> DEPLOYED  (controlled rollback / redeploy)
        -> retire()                                      -> RETIRED  (terminal; history never deleted)
        -> reject(reviewer_user_id=..., reason=...)      -> REJECTED (terminal)

`app/predictions/model_registry.py::approve()`/`reject()` **require** a
`reviewer_user_id` keyword argument — there is no default, so the model
can never approve itself — and each call writes a `ModelApproval` row
(`app/models/model_approval.py`: `model_id`, `model_version`,
`reviewer_user_id`, `decision`, `notes`, the full `validation_report` JSON
that was reviewed, `created_at`) in the same transaction that changes
status, so an `APPROVED`/`REJECTED` model always has a matching, audited
approval record. `is_allowed_transition()` (`app/predictions/enums.py`)
now additionally permits `DEPLOYED -> APPROVED` (`undeploy()`) — every
other transition table entry from the prior milestone is unchanged, so
there remains no path from `TRAINED` straight to `DEPLOYED`.
`app/api/v1/model_governance.py` — restricted to `governance:manage` —
is the only way any of this happens over HTTP; a client can never
directly set a model's status, calibration flag, metrics, or evaluation
results, and `approve()`/`reject()` always use the authenticated caller's
own user id as reviewer, never a client-supplied one.

### Prediction monitoring, outcome tracking, and drift — flags, never actions

    Prediction (already recorded at serving time)
        -> compute_prediction_monitoring()   -- counts, coverage, abstention rate/reasons,
                                                 data-quality/risk-category/score/probability distributions
        -> [prediction_time + horizon_days elapses]
        -> evaluate_prediction_outcome()     -- PredictionOutcome(outcome_known, actual_label, outcome_event_ids, evaluated_at)
        -> compute_model_performance_monitoring()  -- recall/precision/PR-AUC/calibration, ONLY over matured outcomes
        -> compute_data_drift() / compute_feature_drift() (PSI, mean/variance)
        -> check_model_for_review()          -- ModelReviewFlag(MODEL_REVIEW_REQUIRED), if drift crosses threshold

`app/predictions/monitoring.py`/`outcome_tracking.py`/`drift.py` are a
monitoring *foundation*, deliberately not a full MLOps platform: no
scheduler, no automatic dashboard, no external metrics system.
`evaluate_prediction_outcome()` refuses to evaluate a prediction before
its `horizon_days` has actually elapsed (never fabricates an early or
partial outcome), and `compute_model_performance_monitoring()` only ever
scores *matured* outcomes for exactly that reason.
`compute_psi()`/`compute_feature_drift()`/`compute_data_drift()` are
lightweight, fully explainable statistics (Population Stability Index,
distribution distance, mean/variance comparison) — no deep learning, no
opaque drift model — with thresholds documented as configurable
`INITIAL GOVERNANCE DEFAULT`s, not universally validated. **Crucially,
`check_model_for_review()` only ever creates a `ModelReviewFlag` row and
logs `MODEL_REVIEW_REQUIRED` — it never retrains, redeploys, or retires
anything itself** (`tests/test_predictions_drift.py`'s
`test_never_retrains_or_redeploys_a_model_on_drift_detection` proves this
by AST-parsing the module's own imports); a flagged model waits for
`acknowledge_review_flag(user_id=...)`, a human decision, and — if the
human decides retraining is warranted — a separate, future milestone.

### Model cards and the governance validation report

`app/predictions/model_card.py::build_model_card()` produces a machine-
and human-readable card: name/version/type, target, prediction unit,
horizon, training/validation data, features, known limitations, metrics,
calibration status, **intended use**, and an explicit **prohibited-use**
list (employee disciplinary decisions, individual worker risk scoring,
employment decisions, automatic permit rejection, automatic equipment
shutdown), and approval status. `app/predictions/governance.py::
generate_validation_report()` reads a model's own test-split metrics
(already computed at training time), its dataset's quality report, and
optional drift/stability summaries, and produces a structured
`ValidationReport` with an `APPROVE`/`REJECT`/`REVIEW` **recommendation**
— every individual `GovernanceCheck` (name, passed, hard/soft severity,
detail) is independently inspectable, never collapsed into the bottom
line alone. `ApprovalCriteria` (minimum recall/precision, maximum
false-negative rate, maximum recall variability, minimum data quality) is
explicitly documented `INITIAL GOVERNANCE DEFAULT` — a starting point
this codebase has not validated against real-world safety outcomes, not
a claim of correctness. **The recommendation is never auto-applied** — a
human still calls `approve()`/`reject()` separately, and nothing here
transitions a model's status. The milestone's own worked example (a
Model A with PR-AUC 0.71/recall 0.83/good calibration must not lose to a
Model B with a higher PR-AUC of 0.76 but recall 0.61/poor calibration)
is exactly what `model_comparison.py`'s side-by-side report and this
report's multi-check design exist to make visible, never automatically
decided.

### Nine expanded synthetic evaluation scenarios

`tests/fixtures/predictions/synthetic_training_dataset.py` exposes nine
named, documented scenarios built from one shared event-generation
engine (never an unrealistically perfect, single-shape synthetic
dataset): a stable period (flat risk), an increasing-risk period, a
decreasing-risk period (alongside the prior milestone's own LOW →
ELEVATED → LOW regime change), a sparse-data period, a stale-data period
(events stop well before the declared date range ends — verified against
`validate_dataset()`'s own `FreshnessReport.is_stale`), a reporting-bias
scenario (reporting volume drops independent of actual risk — a model or
report that reads "fewer near-misses reported" as "risk went down" is
exactly the mistake this scenario exists to catch), an equipment-failure
leading-indicator scenario (failures cluster ahead of an elevated-risk
period, not merely coincident with it), a corrective-action-
deterioration scenario, and a training-deterioration scenario (both:
increasingly OPEN/OVERDUE/EXPIRED rather than CLOSED/COMPLETED as risk
rises). `tests/test_predictions_synthetic_scenarios.py` checks the
generated *shape* of each scenario against its own documented promise —
never a model's learned performance.

### Tenant isolation and audit logging

Every governance object — `DatasetVersion`, `ModelRegistryEntry`,
`ModelApproval`, `ModelReviewFlag`, `PredictionOutcome` — carries
`organization_id` and is queried through it; organization A can never
train on, evaluate, inspect, retrieve, or list organization B's data,
models, predictions, or model metrics, even when A directly supplies B's
real object id (a scoped join returns nothing, and every HTTP route
returns `404`, never revealing existence). There is no pooled,
cross-tenant model training anywhere in this milestone.
`app/predictions/dataset_registry.py`/`model_registry.py`/`drift.py`/
`outcome_tracking.py`/`governance.py` all write through the existing
`audit_service` — `DATASET_VALIDATED`, `MODEL_VALIDATION_REPORT_GENERATED`,
`MODEL_APPROVED`, `MODEL_REJECTED`, `MODEL_DEPLOYED`, `MODEL_UNDEPLOYED`,
`MODEL_RETIRED`, `MODEL_REVIEW_REQUIRED`, `MODEL_REVIEW_ACKNOWLEDGED`, and
`PREDICTION_OUTCOME_EVALUATED` — and every one of those audit metadata
payloads is a flat mapping of identifiers/labels/statuses, never a
feature value, coefficient, or raw event payload
(`tests/test_predictions_governance_audit_logging.py` enforces this
directly against real `AuditLog` rows for every action in this list).

### Human oversight — advisory only, still true here

Nothing added in this milestone changes the prior milestone's safety
language or oversight boundary: predictions remain advisory. Nothing in
`app/predictions/` automatically suspends or terminates a worker, blocks
a permit, stops equipment, triggers disciplinary action, contacts a
regulator, or closes/modifies an organizational record — a
`ModelReviewFlag` is a request for human attention, never an action
taken on anyone's behalf.

### What this milestone deliberately does not do

No worker-level risk prediction, and no protected personal attribute is
ever used as a feature even if present in upstream source data. No
autonomous safety intervention or automated safety decision of any kind.
No automatic model retraining — drift detection only ever flags a model
for human review (`MODEL_REVIEW_REQUIRED`); a human decides whether, and
how, to retrain, as a separate, future milestone. No deep-learning
predictive model, no external web intelligence, and no autonomous agents.
No Kubernetes/Kafka/Spark/Flink/MLflow, no feature-store infrastructure,
no distributed training — `ModelRegistryEntry`/`DatasetVersion` remain
plain relational tables, deliberately not a dedicated ML platform. No
cross-tenant pooled model training. **Every dataset used to train or
evaluate a model in this repository's own tests is synthetic — this
milestone does not validate any model against real organizational data,
and does not claim production predictive performance.**

## Intelligence Platform Integration & Enterprise API Architecture

    external system -> Authorization: Bearer <client_id>:<secret>  (machine)
      OR human -> X-SIE-Dev-User-Id                                (human, dev-mode only)
        -> RequestContext (app/api/deps_context.py)
        -> authorize_context() / require_context_permission()  -- tenant identity from the
           authenticated caller only, never a client-supplied organization_id
        -> [rate limit] -> [request size limit] -> existing Service -> existing Intelligence Engine
        -> Result -> [request_id + standard error contract] -> Response

This is the Intelligence Platform Integration & Enterprise API v0.1
milestone. Its purpose is **not** to add new intelligence — every ML
calculation, vector search, RAG safeguard, and analytics computation
built in prior milestones is reused completely unchanged — it is to turn
SIE's separate intelligence foundations (knowledge, safety intelligence,
predictive intelligence, governance) into one secure, versioned,
multi-consumer platform. **SIE is not architected as "Safelytic's
backend."** Safelytic is one consumer, authenticated and authorized
exactly the same way any other external application (an HSE system, an
ERP, a construction-management platform) would be — see ["Third-party
integration example"](#third-party-integration-example) below for a
worked example proving that independence, not just asserting it.

The one architectural rule every change in this milestone was held to:
**the API layer orchestrates; it never computes.** `app/api/v1/*.py`
routes call existing services (`app/intelligence/*`, `app/retrieval/*`,
`app/rag/*`, `app/predictions/*`) and existing authorization/tenant
machinery — nothing in this milestone re-implements a calculation, a
retrieval rule, a privacy gate, or a provenance chain that already
existed. Every retrofit below is additive to what a prior milestone
built, never a parallel, second mechanism.

### `RequestContext` — one dependency, either caller kind

`app/api/deps_context.py`'s `RequestContext` composes the pre-existing
human mechanism (`app/api/deps_auth.py`'s dev-mode `X-SIE-Dev-User-Id`
header) and the pre-existing machine mechanism
(`app/api/deps_machine_auth.py`'s `Authorization: Bearer
<client_id>:<secret>`, built in an earlier milestone) into one type, so
a route that should accept either caller kind — analytics, predictions,
knowledge, retrieval, RAG — declares exactly one dependency rather than
duplicating every route twice. It is **not** a third authentication
system: it never verifies a credential itself, only wraps whichever of
the two existing mechanisms actually authenticated the request.
`authorize_context(db, context, permission, organization_id)` encodes
one rule uniformly for every route that uses it: a request naming no
`organization_id` (a GLOBAL-only read) requires only authentication; a
request naming an `organization_id` requires that permission *within
that organization*, resolved from the caller's own authenticated
identity — an `OrganizationMembership` role for a human, `ApiClient.scopes`
for a machine client — **never** from a client-supplied value trusted
at face value. A machine client's `organization_id` is always
`ApiClient.organization_id`; there is no field anywhere a machine
client can name a different organization and have it honored (item 36's
own rule, and see ["Tenant isolation"](#tenant-isolation-principle)
below for the cross-tenant tests that prove it).

GLOBAL-knowledge **writes** are a deliberate exception, kept out of
`authorize_context()` entirely: `app/api/v1/knowledge.py`'s own
`_authorize_manage()` requires platform-admin — a human-only concept —
mirroring the rule `app/api/v1/ingestion.py` already established. A
machine client can never write GLOBAL knowledge, because a machine
client has no platform-admin identity to check.

### Scopes — one vocabulary, not two

Machine-client scopes reuse `app.services.permissions.Permission` — the
exact enum human roles already resolve to — rather than a second,
parallel "intelligence:analytics"-style vocabulary. A scope granted to
an `ApiClient` (e.g. `Permission.INTELLIGENCE_READ`,
`Permission.PREDICTION_READ`, `Permission.KNOWLEDGE_READ`,
`Permission.SAFETY_DATA_WRITE`) means literally the same permission a
human role would need for the same action — least privilege by default,
one place to reason about what a permission actually grants.
`ApiClientService._validate_scopes()` rejects any scope string that
isn't a real `Permission` value at credential-creation time, so a
typo'd or invented scope fails loudly rather than silently granting
nothing (or, worse, something unintended once that string later becomes
a real permission).

### Credential lifecycle

Building on the existing `ApiClient`/`ApiClientService` architecture,
this milestone adds `expires_at` (optional; `authenticate()` rejects an
expired credential exactly like a revoked one, without touching
`status`/`revoked_at`, so the two remain distinguishable in an audit
trail) and machine-authenticated audit events (`API_AUTHENTICATED` on
every successful machine call, `API_ACCESS_DENIED` on a missing-scope
403 — never containing the secret, only `client_id` and scope
metadata). `POST .../api-clients/{id}/rotate` issues a new secret while
keeping the same `client_id`, organization, and scopes — the old secret
stops authenticating the instant rotation commits, the new one works
immediately, with no gap where neither credential works and no window
where both do.

### Standard response envelope, request IDs, and errors

`app/core/request_id.py`'s `RequestIdMiddleware` generates a UUID per
request (returned as `X-Request-Id` and available to every handler,
error response, and audit-log entry via `get_request_id()`) — outermost
in the middleware stack so it exists before anything else runs.
`app/core/errors.py` adds a parallel `error: {code, message,
request_id}` object to every error response **without changing FastAPI's
existing `detail` field at all** — full backward compatibility with
every existing consumer of an error body (item 35's own rule). Error
codes are a fixed, named set (`AUTHENTICATION_REQUIRED`,
`AUTHORIZATION_DENIED`, `TENANT_ACCESS_DENIED`, `RESOURCE_NOT_FOUND`,
`VALIDATION_ERROR`, `RATE_LIMIT_EXCEEDED`, `IDEMPOTENCY_CONFLICT`,
`INSUFFICIENT_DATA`, `PRIVACY_BLOCKED`, `MODEL_NOT_AVAILABLE`,
`INTERNAL_ERROR`); the unhandled-exception handler never leaks a stack
trace, a database error string, or an internal path — verified by a
dedicated test that a genuine `RuntimeError` raised inside a route still
produces only the safe, generic body over the wire.
`app/schemas/envelope.py`'s `ResponseEnvelope[T]`
(`data`/`status`/`request_id`/`timestamp`/`data_quality`/`provenance`)
is applied to exactly one genuinely new endpoint — `GET
.../predictions/{entity_id}/history` — never retrofitted onto an
existing response shape, for the same backward-compatibility reason.

### Idempotency, rate limiting, and request size limits

`Idempotency-Key` (`app/core/idempotency.py`) is wired into `POST
/api/v1/intelligence/predictions` only: repeating the same key with the
same request body replays the original response; repeating it with a
*different* body is a `409 IDEMPOTENCY_CONFLICT`; omitting the header
entirely never triggers either path. It is deliberately **not** wired
into event ingestion, which already has its own domain-level
idempotency (`(organization_id, source_system, source_record_id)`) —
adding a second, HTTP-transport-level mechanism on top would have no
semantic value there.

`app/core/rate_limit.py`'s `LocalRateLimiter` is a fixed-window,
per-key, thread-safe, **in-process** implementation — explicitly
documented as unsuitable for a multi-instance production deployment
(each instance would enforce its own independent window). The seam for
that is the `RateLimiter` Protocol itself: a future `RedisRateLimiter`
implements the same three methods and every call site
(`app/api/deps_rate_limit.py`'s `require_rate_limit(RateLimitClass.READ
| WRITE)`) is unchanged. Every machine-client and shared human/machine
route in this milestone carries a rate-limit dependency; a breach
returns `429 RATE_LIMIT_EXCEEDED`. `app/core/request_limits.py`'s
`RequestSizeLimitMiddleware` enforces `MAX_JSON_BODY_BYTES` on JSON
bodies specifically — a multipart file upload (the existing ingestion
endpoint) is exempt, since it already has its own, separately-controlled
upload-size limit that this milestone left untouched.

### Knowledge, analytics, and predictions over the API

Every read/write capability exposed here calls the exact same service
that has always computed it — `app/retrieval/retrieval_service.py`,
`app/rag/rag_service.py`, `app/intelligence/analytics.py`,
`app/intelligence/signals.py`, `app/predictions/predictor.py`. The one
genuinely new capability is `GET
/api/v1/intelligence/predictions/{entity_id}/history` — paginated,
newest-first, envelope-wrapped — and it reads the same `Prediction` rows
`POST .../predictions` always wrote; nothing about prediction storage or
computation changed to support it.

**Prediction safety is unchanged and still enforced at the API
boundary**: `PredictionRequest` has exactly two fields, `entity_id` and
an optional `as_of` timestamp — there is no field a client could use to
supply a feature value, a label, or a risk score, and a client-supplied
value under any of those names in the request body is simply ignored
(extra fields dropped by the schema, never read by the handler); the
server always computes its own feature snapshot. A dedicated OpenAPI
test (`tests/test_openapi_schema.py`) asserts the generated schema
itself has no such field on any predictive/governance request type, so
this stays visible in the published contract, not only enforced in
code.

**RAG's full safeguard pipeline is reachable, never bypassed, from
either caller kind.** Query → Authorization → Retrieval → Evidence
selection → Sufficiency → Privacy gate → LLM → Citation validation →
Response is exactly the same sequence `app/rag/rag_service.py` always
ran; `app/api/v1/rag.py` calls `rag_service.query()` once, with no
alternate, lighter-weight path for a machine caller. A `PRIVACY_BLOCKED`
outcome (the external-LLM-privacy-gate case) reaches the HTTP caller as
that exact outcome — a normal `200` with `outcome ==
"PRIVACY_BLOCKED"` and no `answer` — never silently upgraded into a
generated response by anything in the API layer (see
["Provenance and data quality survive the API
boundary"](#provenance-and-data-quality-survive-the-api-boundary)
below for how this is tested).

### Provenance and data quality survive the API boundary

Every provenance chain a prior milestone already computed is passed
through unchanged, never recomputed at the API layer: prediction →
model → feature snapshot → explanation (`model_id`, `model_version`,
`feature_snapshot_id`, per-feature contributions with direction and an
association note — never an opaque, unexplained number); RAG citation →
chunk → document version → document → source (`chunk_id`, `document_id`,
`document_version_id`, `source_id` on every citation); retrieval result →
the same chain; analytics risk signal → `supporting_event_ids`, the
exact real `SafetyEvent` rows that produced it. `tests/test_privacy_and_provenance_api.py`
proves this the strict way — not by re-deriving what the expected chain
*should* be, but by comparing the HTTP response directly against the
underlying stored row or the exact object a stubbed service call
returned, so an API layer bug that silently dropped or reshaped a
provenance field would fail these tests even though the endpoint still
returned `200`. `data_quality` (`GOOD`/`LIMITED`/`INSUFFICIENT`/`STALE`)
is likewise reported, never hidden, and an `INSUFFICIENT_DATA` result is
never quietly turned into a normal success.

### Audit logging and observability

Machine authentication (`API_AUTHENTICATED`), scope denial
(`API_ACCESS_DENIED`), and knowledge queries (`KNOWLEDGE_QUERY`) join
the existing `AuditAction` vocabulary, using the same
`audit_service.log()` every prior milestone already writes through — no
second logging mechanism. Audit metadata never contains a credential
secret, a raw incident description, or PII; a dedicated test asserts
this directly against the audit rows a real machine-authenticated
request produces. `app/core/observability.py`'s `AccessLogMiddleware`
records method/path/status/duration/caller-identity/request-id for every
request (never the request body) and attaches the active rate-limit
counters as response headers — a foundation for future metrics
aggregation, not a metrics backend itself.

### Health and dependency checks

`GET /health` (unversioned, pre-existing) and the two new endpoints,
`GET /health/live` and `GET /health/ready`, are deliberately distinct:
liveness never depends on anything external (an optional LLM/embedding
provider being unreachable must never fail it — both default to fully
offline `fake`/`hashing` implementations in every configured
environment), while readiness checks the one *required* dependency,
PostgreSQL, through the same `Depends(get_db)` every other route uses
(not a standalone connection that would silently bypass the test
suite's SQLite override) and returns `503` — never a raw driver
exception — when it's down.

### OpenAPI, developer documentation, and integration examples

`app/core/openapi.py` injects real `securitySchemes` for both
authentication mechanisms and a vendor extension, `x-sie-scopes`,
generated live from the `Permission` enum — never a hand-maintained,
driftable copy. `tests/test_openapi_schema.py` keeps the generated
schema honest: every declared path matches an actually-registered route
(and vice versa), every scope in `x-sie-scopes` matches a real
`Permission` value, and no predictive/governance request schema exposes
a client-writable outcome field. `docs/INTEGRATION_GUIDE.md` is the
developer-facing guide — both authentication mechanisms, tenant context,
ingestion, analytics, knowledge/RAG, predictions, provenance, the
envelope, the error contract, rate limits, a Python example client, and
two worked integration examples:

* **Safelytic integration example** — Safelytic authenticates with its
  own `ApiClient` credential like any other consumer; nothing in the
  intelligence engine contains Safelytic-specific logic, a
  Safelytic-only code path, or a Safelytic-only schema field.
* **Third-party integration example** — a fictional, unrelated HSE
  application ("ThirdPartyHSE") walks the exact same
  authenticate → ingest → query-analytics flow, using nothing Safelytic
  has that it doesn't, proving the app-independence claim rather than
  merely asserting it.

### Webhooks/outbound events — interface only

`app/services/webhook_events.py` defines `WebhookEventName`
(`risk.signal.created`, `prediction.available`,
`model.review.required`, `knowledge.updated`), an `OutboundEvent` shape,
and a `WebhookDispatcher` Protocol with a `NoOpWebhookDispatcher` as the
only concrete implementation today — mirroring the same
documented-but-unimplemented extension-point pattern
`app/ingestion/ocr.py` already established in an earlier milestone.
Nothing in this codebase calls `.dispatch()` yet; this is architecture
for a future milestone, not a working event bus, and no message broker
was introduced to support it.

### What this milestone deliberately does not add

No new predictive model, no deep learning, no autonomous or
tool-using agents, no automated safety intervention, no automated model
retraining, no external web crawling, no worker-level risk scoring — the
milestone's own stop condition. No Redis, no Kafka, no multi-instance
rate-limit coordination (the documented `LocalRateLimiter` limitation
above), no multi-language SDK (the Python example in
`docs/INTEGRATION_GUIDE.md` is illustrative documentation, not a
published package), no `/api/v2/` (the versioning scheme allows one
later without breaking `/api/v1/`, but none is built now). See
["Known gaps / next phase"](#known-gaps--next-phase) for this
milestone's own genuine, as-built limitations.

## Enterprise Data Ingestion & Validation Foundation Architecture

    external system -> POST /api/v1/data/ingestion  (machine-client, safety_data:write)
        -> DataSource ownership check (tenant-verified, never trusted)
        -> EnterpriseIngestionService (new orchestration layer)
        -> SafetyEventIngestionService.ingest_event()  (UNCHANGED per-record pipeline)
             validate -> normalize -> version-aware upsert -> SafetyEvent row
        -> EnterpriseIngestionBatch + EnterpriseIngestionRecord  (new tracking layer)
        -> existing Intelligence Layer (unchanged, consumes SafetyEvent rows as always)

This is the Enterprise Data Ingestion & Validation Foundation v0.1
milestone. Its purpose is to make SIE capable of receiving, validating,
normalizing, quality-classifying, and safely storing real organizational
operational/safety data from external systems — HSE/EHS platforms, ERP
systems, HR/training systems, permit-to-work systems, inspection
systems, incident management, CMMS/maintenance, construction/project
systems, manufacturing systems, IoT/telemetry, or a plain CSV/Excel
export turned into JSON by the caller's own pipeline. **SIE is not built
for any one named application** — see
[`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md)'s own §16 for a
worked example using a generic manufacturer, not Safelytic.

**The governing architectural rule this milestone was held to: build on
the existing `safety_events` architecture, never replace it.** Every
validation rule (`app/intelligence/validation.py`), normalization
function (`app/intelligence/normalization.py`), and the
idempotent-upsert pipeline (`app/intelligence/ingestion_service.py`) is
the exact same code the pre-existing `POST /intelligence/events`
endpoint already used — extended additively (see below), never
duplicated. Tenant isolation, machine-client authentication, scopes,
data-quality states, temporal/as-of handling, provenance, audit logging,
and the enterprise API conventions (request IDs, idempotency, rate
limiting, structured errors) are all the exact mechanisms prior
milestones already built — this milestone adds no second version of any
of them.

### What already existed and was reused, not duplicated

Inspection before writing any code found that `DataSource`
(`app/models/data_source.py`) — introduced in an early foundation
milestone, tenant-scoped, with `name`/`source_type`/`status` — was
already the exact concept this milestone's spec calls "ingestion
source." It was extended in place (four new columns: `system_identifier`,
`schema_version`, `config_metadata`, `api_client_id`) rather than
duplicated into a second, parallel `IngestionSource` table. The same
inspection found `DataSource`'s two existing HTTP routes had **no
authentication or authorization check at all** — a second zero-auth gap
in the same shape as the one closed in `knowledge.py` last milestone —
closed here the same way, with `RequestContext`/`authorize_context()`.

`SafetyEvent`'s idempotency key
(`UniqueConstraint(organization_id, source_system, source_record_id)`),
content-hash-based no-op detection, and per-record `db.begin_nested()`
savepoint batching (see that model's and
`SafetyEventIngestionService`'s own docstrings) are all reused
completely unchanged. `app.intelligence.enums.DataQualityStatus`
(`VALID`/`PARTIAL`/`QUARANTINED`) is reused as-is for every record this
milestone's endpoint classifies — no second quality-state vocabulary was
introduced.

### The generic enterprise ingestion contract

`app/schemas/data_ingestion.py::EnterpriseIngestionRecordCreate` is a
superset of the pre-existing `SafetyEventCreate` shape, adding the
fields the milestone's own generic contract calls for and the older
shape didn't have: `source_record_version` (the source system's own
revision marker), `correlation_id` (an optional link to a related
record or transaction), and `source_schema_version` (the payload-shape
version that specific record was sent under). All three flow all the
way down to new, additive, nullable columns on `SafetyEvent` itself
(plus a fourth, `ingestion_source_id`, linking to the registered
`DataSource`) — see [`docs/INTEGRATION_GUIDE.md` §16](docs/INTEGRATION_GUIDE.md)
for the full field-by-field contract and a worked example. No external
system is forced into a rigid, one-size-fits-all schema before
ingestion — every field but the four identity fields
(`event_type`/`event_time`/`source_system`/`source_record_id`) is
optional, and the original payload is always preserved (`source_value`
on the canonical event, or `payload` on the tracking record for the one
outcome — a validation rejection — where no canonical event exists to
hold it).

### Ingestion batch and record tracking

`EnterpriseIngestionBatch`/`EnterpriseIngestionRecord`
(`app/models/enterprise_ingestion_batch.py`,
`app/models/enterprise_ingestion_record.py`) are new, additive tables —
one row per submission and one row per input record, giving `GET
/api/v1/data/ingestion/batches[/{batch_id}]` something durable to read.
`EnterpriseIngestionBatch.id` is deliberately minted as the *same* UUID
value the pre-existing `SafetyEvent.ingestion_batch_id` column already
stamps on every row it writes — the two are trivially joinable with no
schema change to `SafetyEvent`, and no second batch-identity scheme was
introduced. Payload storage is deliberately not duplicated: a record
that produced or updated a canonical event has its payload on that
event already (`SafetyEvent.source_value`); only a validation-rejected
record — the one case with no canonical event to hold it — gets its own
JSONB copy on the tracking row itself. This is the existing
"structured JSON in a JSONB column" pattern already used throughout this
codebase, not a new filesystem/object-storage abstraction — the
milestone's caveat about avoiding "coupling the domain model to local
filesystem storage" applies to large binary files (see
[Universal ingestion architecture](#universal-ingestion-architecture)'s
own `StorageProvider`), not small structured records.

`app/intelligence/enterprise_ingestion.py::EnterpriseIngestionService`
is a thin orchestration wrapper — the same "business logic lives one
layer down" shape `app/api/v1/predictions.py` already uses around
`app/predictions/predictor.py` — around the *unchanged*
`SafetyEventIngestionService.ingest_event()` call. **The pre-existing
`POST /intelligence/events`/`/events/batch` endpoints are deliberately
left completely untouched** by this new tracking layer: both paths
write into the exact same canonical `safety_events` table the existing
intelligence layer already consumes; the new endpoint is the
fuller-featured one, not a replacement.

### Source-record versioning — the safest minimal foundation

Real enterprise systems resend and update records. `_version_ordering()`
(`app/intelligence/ingestion_service.py`) extends the existing upsert
logic additively — only active when a record actually supplies
`source_record_version` — with the deliberately narrow, documented
boundary the milestone's own escape hatch allows: strict newer/older
ordering applies **only** when both the stored and incoming version
values parse as plain integers, by far the most common real-world
convention. Two new `IngestionOutcome` values
(`SKIPPED_STALE_VERSION`, `REJECTED_VERSION_CONFLICT`) make the two new
cases explicit and auditable: an older, late-arriving version is
refused (never regressing the canonical timeline over a newer one
already applied), and the same declared version describing different
content is refused outright (SIE never guesses which is authoritative).
A non-numeric version scheme falls back to exactly today's pre-existing
behavior (content-hash-based, last write wins) — an explicitly
documented limitation, not a silent gap; see
[`docs/INTEGRATION_GUIDE.md` §16](docs/INTEGRATION_GUIDE.md) for the
full decision table.

### Tenant isolation

Exactly the existing rule, applied with no exceptions to every new
route: the organization for a write is always the authenticated
machine credential's own, pinned organization (`MachineClientContext.organization_id`)
— there is no field anywhere in the request body a client could use to
name a different one. A `source_id` supplied on a submission is
verified to belong to that same organization before use (404, never
403, for a source that doesn't exist or belongs to someone else — never
revealing which). Every read (`GET .../batches*`) requires an explicit,
authorized `organization_id` query parameter via the existing
`app.api.deps_context.require_context_permission()` — there is no
GLOBAL-shaped variant of an ingestion batch or source at all, so the
class of authorization bug fixed earlier this phase (a machine client
bypassing scope on a GLOBAL-shaped request) has no equivalent surface to
reappear on here. Comprehensive cross-tenant tests
(`tests/test_data_ingestion_api.py`, `tests/test_data_sources.py`) prove
organization A can never submit for, read, or reference organization
B's sources, batches, or canonical events.

### What this milestone deliberately does not add

No autonomous agents, no autonomous interventions, no worker-level risk
scoring, no automated safety decisions, no advanced/deep-learning
normalization, no LLM-based normalization (every transformation in
`app/intelligence/normalization.py` remains deterministic and testable),
no web crawling, no external intelligence feeds, no event-streaming
infrastructure, no Redis queues, no distributed workers, no automatic
model retraining or deployment. Processing is synchronous by design —
`EnterpriseIngestionBatch.status`'s `RECEIVED` value is the explicit
seam a future asynchronous implementation would use, not a state any
caller can currently observe. See
["Known gaps / next phase"](#known-gaps--next-phase) for this
milestone's own genuine, as-built limitations.

## Real-World Data Validation & Intelligence Calibration Architecture

    5 controlled scenarios (tests/fixtures/enterprise_scenarios.py)
        -> real EnterpriseIngestionService.ingest_batch()  (UNCHANGED, prior milestone's own service)
            -> data-quality benchmark (accepted/partial/quarantined/rejected/duplicate/version-conflict rates)
        -> real compute_summary/compute_trend/risk_signal_service/detect_anomaly  (all UNCHANGED)
            -> compared against each scenario's own known-correct direction
            -> EXPECTED / UNEXPECTED / INDETERMINATE calibration outcome
    + provenance-chain validation, predictive-dataset-readiness validation,
      multi-tenant isolation validation -- all against the same real, unmodified code paths

This is the Real-World Data Validation & Intelligence Calibration v0.1
milestone. **Its purpose is explicitly not to add intelligence
capability.** It asks a different question: does the SIE data and
intelligence architecture already built across every prior milestone
behave correctly and meaningfully on data shaped like a real
organization's safety/operational history, rather than on the narrow
synthetic unit-test fixtures each earlier milestone's own tests used?
**The governing rule this milestone was held to: do not redesign the
existing SIE intelligence architecture.** Every ingestion, validation,
normalization, analytics, signal, anomaly, and predictive-dataset call
below is the exact, unmodified code prior milestones already built and
tested — this milestone is validation, calibration, and evidence, not a
new feature.

### What already existed and was reused, not duplicated

Inspection before writing any code (this milestone's own item 1) found
every layer this calibration exercise needed already built and already
tested in isolation: `safety_events`, the enterprise ingestion API and
`EnterpriseIngestionService`/`SafetyEventIngestionService` (prior
milestone), deterministic validation and normalization
(`app/intelligence/validation.py`/`normalization.py`), the data-quality
vocabulary (`DataQualityStatus`), `events_as_of()`'s point-in-time
guarantee and `bucketed_counts()` (`app/intelligence/temporal.py`),
descriptive intelligence and feature engineering
(`app/intelligence/analytics.py`/`features.py`), leading/lagging
indicators and trend classification (`indicators.py`/`trends.py`),
anomaly detection (`anomaly.py`), risk signals (`signals.py`), predictive
dataset construction (`app/predictions/dataset.py`), tenant isolation,
and API authorization. Nothing in this list was changed by this
milestone; every calibration result below is a real, previously-existing
code path exercised against new, realistic test data — not new logic
being validated for the first time.

### Realistic scenario framework and five known-ground-truth scenarios

`tests/fixtures/enterprise_scenarios.py` is a generic (no
Safelytic-specific schema) fixture framework covering the milestone's own
required domain vocabulary — incidents, near misses, observations,
inspections, audits, permits, training, and maintenance/operational
signals — built with deterministic, seeded (`random.Random(seed)`)
relative-day-offset timing, the same convention
`tests/fixtures/intelligence/synthetic_dataset.py` already established.
Five scenarios (`tests/evaluation/calibration_harness.py`'s own
`_SCENARIO_EVALUATORS`), each with an explicit, known-correct expected
direction and careful non-causal language:

| Scenario | Shape | Expected (never claimed as causal) |
|---|---|---|
| A — Stable / Low Concern | Flat activity across four consecutive 30-day periods | Stable trends, no risk signals |
| B — Emerging Risk | Near misses/unsafe observations/overdue training/maintenance sharply up in the current 30 days against a quiet 90-day baseline; incidents stay flat | Leading indicators deteriorate; **no claim these factors caused an incident**, since none occurs |
| C — Lagging Event Increase | Leading indicators identical to a stable 4-period baseline; a sudden high-potential incident cluster in the current window | Lagging/trend/anomaly signals fire where statistically justified |
| D — Data Quality Degradation | Missing event dates, an invalid classification, an exact-duplicate resend, a same-version content conflict, missing identifiers, mixed with valid records | Degraded quality metrics; invalid/quarantined records excluded from analytics, never silently trusted |
| E — Recovery | An elevated period improving into a recovered current 30 days | Leading/risk indicators improve; **improvement in indicators is never asserted as proof of actual safety improvement** |

### A real calibration finding: point-in-time correctness and bulk-backfilled history

Calibrating against these scenarios surfaced a genuine, previously
unexercised interaction, not a bug: `events_as_of()`'s point-in-time
guarantee (`ingestion_time <= as_of`, strict by default — see
[Universal ingestion architecture](#universal-ingestion-architecture)'s
temporal design) is checked **per bucket** by `bucketed_counts()`, using
that bucket's own historical end date as `as_of`. A one-shot bulk
historical backfill — every row's `ingestion_time` stamped at the same
real "now" — is therefore, entirely correctly, invisible to every bucket
whose own boundary predates that real ingestion moment: strict
point-in-time correctness demands exactly this, since none of that
history was actually knowable to the system at any of those earlier
boundaries. The practical consequence: **retrospective trend
reconstruction over a one-time bulk backfill will appear to collapse
into the single most recent bucket** unless the data was ingested with a
realistic, near-real-time cadence. This is not something this milestone
changed in `app/intelligence/temporal.py` — redesigning that guarantee
was explicitly out of scope. The calibration harness instead simulates
the realistic case these scenarios describe (an organization operating
day to day, not migrating history in one sitting) by directly backdating
`ingestion_time` to track shortly after each event's own `event_time`
(`_backdate_ingestion_time_near_event_time()`, never through the
ingestion service, mirroring `tests/evaluation/intelligence_harness.py`'s
own pre-existing `stale_data_org` backdating) — documented as a genuine
limitation for real bulk-migration customers in
`docs/CALIBRATION_METHODOLOGY.md`, not patched around silently.

### Terminology mapping — the one new production capability

`app/intelligence/terminology_mapping.py` is this milestone's only
genuinely new production code — a small, deterministic (no LLM),
opt-in alias-mapping layer for the milestone's own item 4: heterogeneous
source terminology ("Near Miss"/"Near-Miss"/"NM"/"Potential Incident")
mapped to SIE's canonical vocabulary for incident types, observation
types, inspection types, audit findings, training status, and
maintenance status. It integrates through the existing, pre-built
`DataSourceAdapter` Protocol (`app/intelligence/adapters.py`) — exactly
that Protocol's own documented extension point — as a second, opt-in
implementation alongside the unchanged default `GenericJSONAdapter`,
never modifying the core validate/normalize/upsert pipeline.
**Ambiguous terminology is never guessed**: `map_event_type()`/
`map_event_subtype()`/`map_training_status()`/`map_maintenance_status()`
return an explicit `AMBIGUOUS` or `UNKNOWN` `MappingOutcome`, which
`TerminologyMappingAdapter.validate()` turns into a blocking
`ValidationIssue` — reusing `validate_and_normalize()`'s existing
blocking-issue-to-`QUARANTINED` rule rather than inventing a second
quarantine mechanism. The adapter preserves the "`source_value` is
exactly what was received" invariant: the payload's true original
terminology is preserved in `source_value` even though the canonical
`event.event_type`/`event_subtype` are the mapped values.

### Temporal validation, data-quality benchmarking, provenance, and calibration classification

`tests/test_enterprise_temporal_calibration.py` (item 5) is additive to
the pre-existing, mandatory 6-case `tests/test_temporal_leakage.py` —
every case here goes through the real `EnterpriseIngestionService` end
to end (never hand-seeded rows): the milestone's own worked example
(an incident dated 2026-01-10 but only ingested 2026-02-05 must not
appear in a 2026-01-31 snapshot), late-arriving historical batches, a
version correction re-stamping `ingestion_time` and the resulting
retroactive-visibility change this causes (a documented, asserted
characteristic of a single-physical-row upsert, not a bug), a stale
out-of-order version never disturbing already-applied newer content, a
plausible future `event_time` (accepted, but correctly excluded until
that time arrives), duplicate timestamps on genuinely distinct records,
and out-of-order batch arrival.

`DataQualityBenchmark` (`tests/evaluation/calibration_harness.py`, item
6) computes total/valid/partial/quarantined/rejected/duplicate/stale/
version-conflict/missing-timestamp/invalid-classification/missing-identifier
counts and completeness/acceptance/rejection/quarantine/duplicate/
temporal-validity rates directly from a real `EnterpriseIngestionResult`
— schema-validity metrics only, **never presented as factual correctness
of the underlying record** (the milestone's own explicit caution,
restated verbatim in every generated report).

`_validate_provenance()` (item 7) walks the full chain — external record
→ `EnterpriseIngestionRecord` → `EnterpriseIngestionBatch` → `DataSource`
→ canonical `SafetyEvent` — for every accepted record in a real ingested
batch, confirming external record id, source system, content hash,
normalization status, and schema version all survive intact.

Calibration itself (items 8-9) compares each scenario's real
`compute_trend`/`compute_summary`/`risk_signal_service.detect_all`/
`detect_anomaly` output against that scenario's own known-correct
direction, classified `EXPECTED`/`UNEXPECTED`/`INDETERMINATE` (never
forced to a binary pass/fail when a method genuinely can't support one —
e.g. anomaly detection below its minimum baseline period count).

### Predictive dataset readiness

`tests/test_predictive_dataset_readiness.py` (item 10) validates
`app/predictions/dataset.py::build_training_examples()` against
realistic, site-scoped scenario data: correct `(site, as_of)` keying, a
feature vector that genuinely reflects real ingested activity, no future
leakage (concretely — a snapshot built before a realistic escalation
shows the quiet baseline, one built after shows the real elevated count),
label construction using only events strictly after `as_of` within the
horizon, missing-data handling for a site with no events, tenant
isolation, and full reproducibility (byte-for-byte identical
`TrainingExample`s on a second build). **This validates dataset
construction correctness only — it does not improve, retrain, or claim
any predictive accuracy for the model itself**; feature/label separation
remains `tests/test_feature_label_separation.py`'s own, unmodified
regression test.

### Multi-tenant validation and reproducibility

Every scenario, provenance check, and predictive-readiness check runs
against a fresh, dedicated `Organization` per test; `_validate_tenant_isolation()`
(item 12) additionally proves two organizations ingesting *different*
scenarios in the same run never see each other's canonical events,
quality metrics, or predictive datasets. Every scenario/mapping/fixture
uses only deterministic, seeded randomness and relative time offsets
(item 11/13) — `tests/evaluation/test_calibration_evaluation.py` asserts
exact, seed-derived record counts per scenario (72/77/65/16/53) as a
direct reproducibility check, and the full calibration run was confirmed
byte-identical (aside from its own generation timestamp) across repeated
executions.

### Evaluation reports

`tests/evaluation/test_calibration_evaluation.py` (item 14) writes both
`docs/CALIBRATION_EVALUATION_REPORT.md` (human-readable) and
`docs/CALIBRATION_EVALUATION_REPORT.json` (machine-readable), each
stamped with the same label restated everywhere in this milestone:
**"Prototype / controlled-scenario calibration only — not a production
benchmark."** See
[`docs/CALIBRATION_METHODOLOGY.md`](docs/CALIBRATION_METHODOLOGY.md) for
the full methodology, how to run the evaluation, how to interpret its
results, and this milestone's own limitations — including the explicit
statement that these controlled scenarios do not establish production
accuracy on any real customer's data.

### What this milestone deliberately does not add

No advanced ML, no deep learning, no model retraining, no autonomous
agents, no autonomous interventions, no worker-level scoring, no
LLM-based normalization or mapping (`terminology_mapping.py` is entirely
deterministic, table-driven), no web crawling, no external intelligence
feeds, no event streaming, no Redis queues, no distributed workers, no
production alerting, no automated safety decisions. See ["Known gaps /
next phase"](#known-gaps--next-phase) for this milestone's own genuine,
as-built limitations.

## Real Enterprise Dataset Validation Foundation Architecture

    RawSafetyEventPayload[] (a fixture today; a real, anonymized enterprise
    dataset in a future step, unchanged call shape)
        -> EnterpriseIngestionService.ingest_batch()   (UNCHANGED, reused)
        -> IngestionSummary + DataQualitySummary        (item 2)
        -> TerminologyReviewEntry[] + summary            (item 3, app/intelligence/terminology_review.py)
        -> TemporalIntegrityReport                        (item 4)
        -> ProvenanceValidationReport                      (item 5, extends the chain to FEATURE/INDICATOR
                                                              and PREDICTIVE DATASET)
        -> IntelligenceReadinessReport                      (item 6)
        -> PredictiveReadinessReport                         (item 7)
        -> EnterpriseDatasetValidationReport                  (assembled, item 10's OBSERVED/MAPPED/
                                                                 QUARANTINED/REJECTED/UNAVAILABLE rendering)
    + queue_review_candidates() -> HseExpertReview rows        (item 8, evaluation-only)

This is the Real Enterprise Dataset Validation Foundation v0.1
milestone — the direct successor to Real-World Data Validation &
Intelligence Calibration v0.1 (above). **It builds a reusable
framework, not a validation result.** No confidential/customer data is
loaded in this milestone; `tests/fixtures/messy_enterprise_dataset.py`
is a clearly-labeled, deterministic, *synthetic* enterprise-shaped
fixture, and every report this framework generates carries that label
explicitly. See
[`docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md`](docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md)
for the full guide — how a future real dataset should be supplied,
required/optional fields, and the explicit statement that passing this
harness against the synthetic fixture does not constitute validation
against real customer data.

**The governing rule this milestone was held to, again: do not redesign
the existing SIE intelligence architecture.** `app/validation/enterprise_dataset_validation.py`
orchestrates the exact, unmodified `EnterpriseIngestionService`,
`SafetyEventIngestionService`, `events_as_of()`/`bucketed_counts()`,
`compute_summary()`/`compute_trend()`, `risk_signal_service`,
`detect_anomaly()`, `get_or_build_feature_snapshot()`, and
`build_training_example()`/`generate_label()` prior milestones already
built — this is production code (`app/`, not `tests/`, unlike Milestone
2's own calibration harness), because it is explicitly meant to be run
again, unchanged, against a real dataset once one is supplied.

### Terminology review structure

`app/intelligence/terminology_review.py` builds the item-3 `SOURCE_TERM
→ PROPOSED_CANONICAL_TERM → STATUS → REASON` structure entirely over
`terminology_mapping.py`'s existing, unmodified `map_event_type()`/
`map_event_subtype()`/`map_training_status()`/`map_maintenance_status()`
— no new matching logic anywhere. `TerminologyReviewStatus` carries the
underlying `MAPPED`/`UNKNOWN`/`AMBIGUOUS` outcome through unchanged, plus
an additional `REVIEW_REQUIRED`/`requires_review` flag set on every
non-`MAPPED` entry, so a reviewer can filter "everything that needs a
human" without knowing the underlying mapping vocabulary. An
`UNKNOWN`/`AMBIGUOUS` entry's proposed canonical term is always `None` —
never guessed.

### HSE expert review — evaluation only, never automated approval

`HseExpertReview` (`app/models/hse_expert_review.py`, migration `0012`)
is a new, tenant-scoped, persisted table for a future human HSE expert
to review terminology mappings, quarantined records, unexpected
classifications, representative intelligence outputs, and risk
indicators — `target_type`/`target_reference`/`provenance` describe
*what*, `outcome` (`CORRECT`/`INCORRECT`/`PARTIALLY_CORRECT`/
`NOT_ENOUGH_INFORMATION`, nullable = pending) and `reviewer_comment`
describe the human's judgment, once given.
`app/services/hse_review_service.py` is the one read/write path
(`queue_for_review()`/`submit_review()`/`list_reviews()`), and
`queue_review_candidates()` in the validation module turns a completed
report's own `requires_review` terminology entries and quarantined
records into pending rows automatically. **Nothing in this codebase
reads `outcome` and changes ingestion, mapping, or intelligence
behavior** — the exact same non-automation boundary `ModelReviewFlag`
(Predictive Model Validation & Governance v0.1) already draws for
model-performance review, applied here to a different target;
`tests/test_hse_expert_review.py` asserts this structurally (neither the
ingestion nor the mapping module imports this review mechanism at all).

### A second real finding: batch-level accounting vs. canonical-row accounting

Building the provenance and data-quality sections against realistic
messy data surfaced a second genuine subtlety (the first was Milestone
2's own bulk-backfill finding, reconfirmed unchanged above):
`EnterpriseIngestionBatch.accepted_records` counts *ingestion record
outcomes* whose own `quality_state` resolved to `VALID` — including a
duplicate resend, a stale version, or a version conflict that *resolved
against* an already-valid existing row without creating or changing a
canonical event. That is a different, equally legitimate thing from "how
many distinct canonical rows carry the content this specific record
describes." `ProvenanceValidationReport`'s own content-hash check
accounts for this directly: only the *last* content-bearing
(`CREATED`/`UPDATED`/exact-replay `SKIPPED_IDEMPOTENT`) record for a
given canonical event is checked against that row's current content —
an earlier `CREATED` record later superseded by a correction, or a
`SKIPPED_STALE_VERSION`/`REJECTED_VERSION_CONFLICT` record whose whole
point is that its content was never applied, correctly does *not* have
its own content_hash compared against the row's current state.

### What this milestone deliberately does not add

No production ML training, no model retraining, no autonomous agents,
no LLM-based classification, no automated safety decisions, no automated
intervention recommendations, no Kafka, no Redis, no production event
streaming, no unnecessary background workers, no Safelytic-specific
coupling, no customer-specific hard-coded mappings, no production
deployment infrastructure. See
[`docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md`](docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md)
for the full guide and ["Known gaps / next phase"](#known-gaps--next-phase)
for this milestone's own genuine, as-built limitations.

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

`LLM_PROVIDER` (`fake`) / `LLM_MODEL_NAME` / `LLM_MODEL_VERSION` /
`LLM_TEMPERATURE` (0.0) / `LLM_MAX_OUTPUT_TOKENS` (800) /
`LLM_TIMEOUT_SECONDS` (30.0) / `LLM_API_BASE_URL` / `LLM_API_KEY` (unset;
never committed, never logged) / `LLM_PROVIDER_IS_EXTERNAL` (`true`)
configure the LLM provider — see [Evidence-Grounded RAG](#evidence-grounded-rag)
above, in particular "LLM provider abstraction" for why `fake` is the
default and `FakeLLMProviderInProductionError`'s guardrail against it
reaching a real deployment. `RAG_MAX_EVIDENCE_ITEMS` (6) /
`RAG_MAX_CONTEXT_CHARACTERS` (6000) / `RAG_DEDUP_SIMILARITY_THRESHOLD`
(0.85) configure evidence selection; `RAG_SUFFICIENT_MIN_EVIDENCE_COUNT`
(2) configures evidence sufficiency; `RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD`
(0.3) configures source-conflict detection — all documented *initial*
defaults, the same "not scientifically validated" spirit as the chunking/
retrieval defaults above. `ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA` (`false`)
is the external-LLM privacy boundary. `LOG_RAG_QUERY_TEXT` (`false`) /
`LOG_RAG_ANSWER_TEXT` (`false`) gate whether a RAG request's raw query/
generated answer are ever written to the audit trail.

`INTELLIGENCE_ANALYTICAL_WINDOWS_DAYS` (`[7, 30, 90, 365]`) /
`INTELLIGENCE_DEFAULT_WINDOW_DAYS` (30) / `INTELLIGENCE_BASELINE_WINDOW_DAYS`
(90) configure analytical windows and baseline periods — see
[Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)
above. `INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS` (10) /
`INTELLIGENCE_LIMITED_DATA_MIN_EVENTS` (3) configure data sufficiency;
`INTELLIGENCE_FRESHNESS_THRESHOLD_DAYS` (7) configures staleness.
`INTELLIGENCE_TREND_MIN_PERIODS` (3) / `INTELLIGENCE_TREND_SLOPE_THRESHOLD`
(0.1) configure trend classification; `INTELLIGENCE_ANOMALY_MIN_BASELINE_PERIODS`
(4) / `INTELLIGENCE_ANOMALY_Z_SCORE_THRESHOLD` (2.0) configure anomaly
detection; `INTELLIGENCE_SIGNAL_SURGE_MULTIPLIER` (2.0) /
`INTELLIGENCE_SIGNAL_MIN_EVENT_COUNT` (3) /
`INTELLIGENCE_TRAINING_COMPLIANCE_THRESHOLD` (0.8) configure risk-signal
detection — all documented *initial* defaults, the same "not
scientifically validated" spirit as every other threshold in this
codebase. `INTELLIGENCE_SENSITIVE_ATTRIBUTE_KEYS` (employee name/id,
medical details, disciplinary action) / `LOG_INTELLIGENCE_EVENT_DESCRIPTION`
(`false`) configure the privacy boundary.

## Deliberate scope boundaries (v0.1)

To keep each foundation phase clean and reviewable, the following are
intentionally **not** included yet: real OIDC/OAuth2 token verification
for human users, a commercial identity provider dependency, OAuth2
client-credentials flow specifically (see below for what machine-client
auth *is* built), hybrid/keyword retrieval, a reranking model,
sophisticated predictive ML, autonomous or tool-using agents, external
web search/crawling, model fine-tuning or training, Safelytic
integration, Redis, Celery, Kafka, Kubernetes, production (S3/Azure/GCS)
object storage, commercial OCR, transcription, and automatic
external-source trust. (The AI/LLM layer and RAG themselves *are* now
implemented, evidence-grounded only — see
[Evidence-Grounded RAG](#evidence-grounded-rag). Machine-client [API
key] authentication for external system integration, and the
data-intelligence foundation for future predictive models, *are* now
implemented too — see
[Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture).)
See
[Identity architecture](#identity-architecture) for what *is*
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
Architecture](#semantic-knowledge-architecture) for the full design.
**As of the Evidence-Grounded RAG v0.1 milestone, an evidence-grounded
LLM reasoning layer *is* implemented** on top of that retrieval —
see [Evidence-Grounded RAG](#evidence-grounded-rag) for the full design,
and its own "What RAG deliberately does not do" section for what
remains genuinely out of scope (hybrid/keyword retrieval and reranking
in particular still are not implemented). **As of Intelligence Platform
Integration & Enterprise API v0.1, SIE is a versioned, multi-consumer
platform with a standard response/error contract, request IDs,
idempotency, rate limiting, request size limits, OpenAPI documentation,
health/readiness endpoints, and observability foundations** — see
[Intelligence Platform Integration & Enterprise API
Architecture](#intelligence-platform-integration--enterprise-api-architecture)
for the full design and that section's own "What this milestone
deliberately does not add" for what remains genuinely out of scope
(Redis-backed rate limiting, a real event bus, multi-language SDKs, and
`/api/v2/` in particular). **As of Enterprise Data Ingestion &
Validation Foundation v0.1, structured operational data from external
systems can be received, validated, normalized, quality-classified,
deduplicated, source-record-versioned, and safely stored with full
batch/record traceability** — see [Enterprise Data Ingestion &
Validation Foundation
Architecture](#enterprise-data-ingestion--validation-foundation-architecture)
for the full design and that section's own "What this milestone
deliberately does not add" for what remains genuinely out of scope
(async/background processing, CSV/XLSX/webhook/database/event-stream
connectors, and non-numeric source-record-version ordering in
particular). **As of Real-World Data Validation & Intelligence
Calibration v0.1, the existing ingestion/validation/analytics/predictive
pipeline has been calibrated against five controlled, realistic
scenarios with known-correct expected outcomes, plus dedicated temporal,
data-quality, provenance, predictive-dataset-readiness, and multi-tenant
validation** — see [Real-World Data Validation & Intelligence Calibration
Architecture](#real-world-data-validation--intelligence-calibration-architecture)
and [`docs/CALIBRATION_METHODOLOGY.md`](docs/CALIBRATION_METHODOLOGY.md).
This milestone deliberately adds no new intelligence capability — see
that section's own "What this milestone deliberately does not add" — and
its results are explicitly **not** evidence of production accuracy on
real customer data. **As of Real Enterprise Dataset Validation
Foundation v0.1, a reusable, production-code harness
(`app/validation/`) can evaluate any dataset shaped like SIE's
enterprise ingestion contract — terminology review, temporal integrity,
end-to-end provenance (through feature/indicator and predictive-dataset
stages), intelligence readiness, and predictive-dataset readiness — plus
a structured, evaluation-only HSE expert review mechanism
(`HseExpertReview`)** — see [Real Enterprise Dataset Validation
Foundation Architecture](#real-enterprise-dataset-validation-foundation-architecture)
and [`docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md`](docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md).
No confidential or customer data is loaded in this milestone — every
dataset this repository evaluates is a clearly-labeled synthetic
fixture, and passing this harness against it is explicitly **not**
validation against real customer data.

## Known gaps / next phase

* **Fixed: migration 0005's enum-type-creation defect.** Discovered in
  the Semantic Knowledge Engine v0.1 milestone while integrating a real
  PostgreSQL + pgvector server for the first time in this project's
  history (previously, migration 0005 had only been dialect-tested via
  SQLite and an offline `--sql` dry run against PostgreSQL — neither can
  catch this). Root cause, confirmed live: `0005`'s
  `batch_alter_table.add_column()` calls add two new PostgreSQL
  enum-typed columns to the already-existing `knowledge_chunks` table;
  on real PostgreSQL, Alembic's `add_column` (batched or not) does not
  auto-create the enum type the column references — only
  `op.create_table()` does that. Every earlier native enum column was
  introduced via `create_table`, which is why this had never surfaced
  before. **Fixed inside migration 0005 itself** — it now creates both
  enum types explicitly (`sa.Enum(...).create(op.get_bind(),
  checkfirst=True)`, idempotent and a no-op on SQLite) before the
  `add_column` calls that reference them; the downgrade path is
  unchanged (it already dropped only the two types 0005 itself creates,
  never touching `extraction_method`, which migration 0004 owns).
  **Verified live**, in this corrective milestone, against a genuinely
  fresh PostgreSQL 16.13 + pgvector 0.6.0 database with the schema
  dropped and recreated first (`DROP SCHEMA public CASCADE; CREATE
  SCHEMA public;`), with **no manual intervention**: `alembic upgrade
  head` succeeds 0001 → 0006 end to end, a `downgrade` to 0004 followed
  by a re-`upgrade` to head round-trips cleanly, and both new enum types
  plus every expected table/extension exist afterward with nothing else
  disturbed. This is now also enforced by an automated regression test —
  `tests/test_migrations.py` (PostgreSQL-only; skipped when no real
  server is reachable) — which was itself confirmed to fail with the
  original `psycopg.errors.UndefinedObject` error when the fix was
  temporarily reverted, and to pass again once restored. `alembic
  upgrade head` against a fresh `docker-compose up` deployment is no
  longer blocked.
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
* **No semantic (embedding-aware) *chunking*.** `StructureAwareChunkingStrategy`
  is deterministic, structure-based splitting — see [Knowledge Quality &
  Semantic Chunking Pipeline](#knowledge-quality--semantic-chunking-pipeline).
  A future `SemanticChunkingStrategy` (or `TableAwareChunkingStrategy`,
  `LegalDocumentChunkingStrategy`, `SafetyProcedureChunkingStrategy`) can
  be added as another `ChunkingStrategy` implementation without changing
  the interface or any call site; none of that exists yet. (Embeddings,
  vector search, and RAG themselves *are* now implemented — see
  [Semantic Knowledge Architecture](#semantic-knowledge-architecture) and
  [Evidence-Grounded RAG](#evidence-grounded-rag).)
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
* **`HashingEmbeddingProvider` is not a trained semantic model** (it
  remains the default, and the only provider CI itself exercises). It is
  a genuine, deterministic, dependency-free feature-hashing embedding —
  see [Semantic Knowledge Architecture](#semantic-knowledge-architecture)
  — chosen specifically so tests and CI never need network access or a
  downloaded model. **SIE Milestone 21: Real Semantic Embedding &
  Retrieval Productionization v0.1** made `SentenceTransformerEmbeddingProvider`
  a real, tested production implementation — see
  `docs/SEMANTIC_EMBEDDING.md` for the recommended production model
  (`sentence-transformers/all-MiniLM-L6-v2`) and exactly what was (and
  was not) validated in this environment, which still cannot download
  that specific pretrained checkpoint. Before production use with a real
  pretrained model, that model's own semantic quality should be
  independently evaluated in an environment with network access — no
  `RetrievalService` or `EmbeddingService` call site would need to
  change to do so. Because
  `EMBEDDING_PROVIDER` defaults to `"hashing"` (unlike `DEV_MODE`, whose
  unsafe value is *not* the default), `build_embedding_provider()`
  (`app/embeddings/provider.py`) — and therefore `get_embedding_provider()`,
  which is what application startup and every request path actually
  call — **raises `HashingProviderInProductionError` and refuses to
  construct the provider at all** whenever it would resolve to
  `"hashing"` while `APP_ENV` is `"production"`/`"prod"`: the same "fail
  closed" shape `DEV_MODE` already uses for auth
  (`app/api/deps_auth.py`). A misconfigured production deployment cannot
  serve a single request on the hashing provider — it fails before any
  embedding is generated, not after silently returning
  semantically-meaningless vectors. Development, test, and CI
  environments (any other `APP_ENV` value) are unaffected.
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
* **No hybrid (keyword + vector) retrieval or reranking.** Explicitly out
  of scope — see [Semantic Knowledge Architecture](#semantic-knowledge-architecture)'s
  "Future architecture" diagram. (RAG and LLM integration themselves
  *are* now implemented — see [Evidence-Grounded RAG](#evidence-grounded-rag)
  — the gaps below are specific to that layer.)
* **The real LLM provider (`OpenAICompatibleLLMProvider`) has not been
  exercised against a real model/API in this environment.** No reachable
  LLM API endpoint in this session's sandboxed egress policy. It is
  implemented and code-reviewed, selectable via
  `LLM_PROVIDER=openai_compatible`, but not validated end to end against
  a live provider; do not present it as validated. `FakeLLMProvider`
  remains the only LLM provider actually exercised by this codebase's
  tests and evaluation harness. (`SentenceTransformerEmbeddingProvider`
  was in this same position until SIE Milestone 21 — see
  `docs/SEMANTIC_EMBEDDING.md` for how a locally-trained-from-scratch
  model was used to still produce a genuine, honestly-labeled real-model
  validation despite the identical egress restriction; that technique
  has not been attempted for the LLM layer.)
* **Source conflict detection is a narrow, keyword-based heuristic, not
  a general contradiction detector.** See [Evidence-Grounded RAG](#evidence-grounded-rag)'s
  "Source conflicts" section — it only catches a requirement-type
  statement paired with its explicit negation over shared vocabulary. A
  paraphrased conflict, or one with no shared significant words, will not
  be detected. `RAG_CONFLICT_TOPIC_OVERLAP_THRESHOLD` is a documented
  initial default, not tuned against any real-world conflict dataset.
* **Prompt injection defense is structural, not a guarantee.** Retrieved
  evidence is clearly delimited and never concatenated into the system
  instructions, and every test provider/test path confirms that
  structure — but this codebase makes no claim that string delimiting
  alone can prevent a sufficiently adversarial document from influencing
  a *real* model's behavior once it becomes one token stream inside that
  model's own context window. See [Evidence-Grounded RAG](#evidence-grounded-rag)'s
  "Prompt injection defense" section.
* **Evidence sufficiency/evidence-selection thresholds
  (`RAG_SUFFICIENT_MIN_EVIDENCE_COUNT`, `RAG_MAX_EVIDENCE_ITEMS`,
  `RAG_MAX_CONTEXT_CHARACTERS`, `RAG_DEDUP_SIMILARITY_THRESHOLD`) are
  documented initial defaults**, calibrated against
  `HashingEmbeddingProvider`'s own score distribution — the same
  "not scientifically validated" caveat the retrieval thresholds above
  already carry. They will need recalibrating if a different embedding
  or LLM provider is ever configured.
* **No persistent RAG request/generation table.** RAG audit and
  reproducibility metadata is written into the existing `AuditLog` table
  (`AuditAction.RAG_QUERY_EXECUTED`) rather than a new one — see
  `app/rag/rag_service.py`'s own docstring for why a dedicated table was
  judged unnecessary for this milestone. The full generated prompt/answer
  is never stored by default (`LOG_RAG_QUERY_TEXT`/`LOG_RAG_ANSWER_TEXT`,
  both off).
* **No RAG-level rate limiting or cost accounting beyond the per-request
  evidence/token caps.** `RAG_MAX_EVIDENCE_ITEMS`/`RAG_MAX_CONTEXT_CHARACTERS`/
  `LLM_MAX_OUTPUT_TOKENS` bound one request's cost; there is no
  per-user/per-organization quota, budget, or rate limit yet.
* **The RAG evaluation harness (`tests/evaluation/rag_harness.py`) is a
  small, synthetic, regression-catching check, not a production
  benchmark** — the same "Prototype evaluation" labeling the Recall@K
  harness already carries. Its "abstention correctness" metric is
  honestly below 1.0 on this fixture (~0.67, not asserted higher) for a
  real, documented reason: `HashingEmbeddingProvider` is a bag-of-words
  embedding, not a trained semantic model, so an unrelated query can
  occasionally still hash into overlapping vocabulary buckets and cross
  the relevance bar. A real embedding model would be expected to score
  closer to 1.0 here.
* **Intelligence & Predictive Analytics Foundation v0.1's own genuine
  limitations** (unvalidated thresholds, no persisted feature/signal
  history yet, no cross-source entity resolution, no retention-policy
  enforcement) are listed in full in
  [Intelligence & Predictive Analytics Architecture](#intelligence--predictive-analytics-architecture)'s
  own "Genuine limitations" section, not repeated here. **No
  sophisticated predictive ML exists in this codebase** — the one model
  implemented (a hand-rolled logistic regression,
  `app/predictions/logistic_regression.py`) is explicitly a prototype
  baseline trained on synthetic data only, never described as production
  predictive intelligence — see
  [Predictive Intelligence Architecture](#predictive-intelligence-architecture).
* **Predictive Risk Modeling Specification v0.1's own genuine
  limitations:**
  * **No real-world model performance claim of any kind.** Every model
    this milestone can produce is trained on the synthetic dataset in
    `tests/fixtures/predictions/synthetic_training_dataset.py` — its
    metrics prove the pipeline computes real, non-fabricated numbers
    correctly, not that any resulting model would perform usefully on
    real organizations' data.
  * **Model monitoring and drift detection were named here as future
    work — they are now implemented**, in the Predictive Model
    Validation & Governance v0.1 milestone; see its own "Genuine
    limitations" below for what remains true even with that built.
  * **No `model_evaluations` table** — per-split metrics live on
    `ModelRegistryEntry.metrics` (JSON) rather than a separate table;
    revisit if evaluation history needs to be queried independently of
    its model or compared across many models at once.
  * **A Gradient Boosting baseline was designed for here but not built —
    it now is**, in the Predictive Model Validation & Governance v0.1
    milestone (`app/predictions/gradient_boosting.py`, via scikit-learn).
  * **Staleness/cold-start/data-sufficiency thresholds
    (`MIN_HISTORICAL_DAYS`, `MIN_HISTORICAL_EVENT_COUNT`,
    `MAX_SOURCE_DATA_STALENESS_DAYS`, `ELEVATED_RISK_THRESHOLD`,
    `MODERATE_RISK_THRESHOLD`) are documented initial defaults**, not
    statistically validated against real incident data — the same
    "not scientifically validated" caveat this codebase already carries
    for its retrieval and intelligence thresholds.
* **Predictive Model Validation & Governance v0.1's own genuine
  limitations:**
  * **No real organization has actually supplied real data yet.** Every
    dataset used in this repository's own tests — including every `REAL`-
    tagged one — is synthetic; `register_real_dataset()`'s environment-
    tagging and quality-report machinery is proven correct, not that any
    model has been validated against genuine organizational data.
  * **Calibration is verified for directional consistency only.** The
    synthetic calibration checks confirm the reliability-curve/Brier/ECE
    machinery computes real numbers on data with a known approximate
    event frequency — this milestone never claims statistical calibration
    validity that would require a much larger, real-world sample.
  * **`ApprovalCriteria`/`DataSufficiencyThresholds`/drift thresholds
    (PSI 0.10/0.25, performance-drift delta, etc.) are documented
    "INITIAL GOVERNANCE DEFAULT" starting points**, not validated against
    real-world safety outcomes — the same caveat as every other threshold
    in this codebase, explicitly repeated here because this milestone is
    specifically about governance rigor.
  * **No automatic model retraining or scheduled evaluation.** Drift
    detection only ever writes a `ModelReviewFlag` and logs
    `MODEL_REVIEW_REQUIRED` — a human decides whether, and how, to
    retrain, and that retraining flow itself is unbuilt, by design (the
    milestone's own stop condition).
  * **`compute_psi()`'s bin-based estimate is noisy at small sample
    sizes** (documented directly against a real failure encountered
    while writing its own tests) — a real limitation of the statistic
    itself at low n, not something a code fix corrects; it becomes more
    reliable as the compared samples grow.
  * **The monitoring/outcome-tracking/drift modules are a foundation,
    not a full MLOps platform** — no scheduler, no external metrics
    system, no automated alerting integration; `compute_*_monitoring()`
    functions are called on demand (via the `GET .../monitoring` route)
    rather than continuously.
* **Intelligence Platform Integration & Enterprise API v0.1's own
  genuine limitations:**
  * **`LocalRateLimiter` is single-process, in-memory.** Explicitly
    documented as unsuitable for a multi-instance production deployment
    — each instance would enforce an independent window, so the
    effective limit scales with instance count. The `RateLimiter`
    Protocol is the seam a future `RedisRateLimiter` would fill without
    changing any call site; none is built in this milestone.
  * **No real event bus.** `app/services/webhook_events.py` is an
    interface and a `NoOpWebhookDispatcher` only — nothing in this
    codebase actually calls `.dispatch()` yet. Outbound webhooks
    (`risk.signal.created`, `prediction.available`,
    `model.review.required`, `knowledge.updated`) remain a documented
    future architecture, not a working feature.
  * **No multi-language SDK.** The Python example client in
    `docs/INTEGRATION_GUIDE.md` is illustrative documentation an
    integrator can copy from, not a published, versioned package.
  * **Human authentication is still development-mode only** — this
    milestone did not add real OIDC/OAuth2 token verification for human
    callers; see [Identity architecture](#identity-architecture) and the
    "No real authentication" gap above, both still true. Machine-client
    authentication (`ApiClient` bearer credentials) is the one mechanism
    in this codebase suitable for anything beyond local development
    today.
  * **Performance numbers are local-development-machine, single-request
    timings only** — no concurrency, no realistic production data
    volume, no warmed production hardware; see
    `docs/PERFORMANCE_BASELINE.md` and that report's own repeated
    caveat. They exist to catch a future gross regression, never to
    claim a production capacity or SLA figure.
  * **Observability is a foundation, not a metrics platform.**
    `AccessLogMiddleware` logs structured request lines and the
    rate-limiter exposes response headers; there is no aggregation,
    dashboarding, or alerting system wired up, and none was in scope.
  * **`/api/v2/` does not exist.** The versioning scheme (a bare,
    unprefixed `/api/v1/` namespace with no version-specific coupling
    baked into route logic) is intended to allow a future `/api/v2/`
    without breaking existing consumers, but nothing about v2 was
    designed or built — premature for a v0.1 platform with no external
    consumers yet.
* **Enterprise Data Ingestion & Validation Foundation v0.1's own genuine
  limitations:**
  * **Source-record-version ordering only protects plain-integer version
    schemes.** A non-numeric scheme (a semantic version, a date-stamped
    revision marker used as a version, ...) falls back to today's
    simpler, pre-existing behavior (content-hash-based, last write
    wins) — no ordering protection at all for that scheme. See
    `app/intelligence/ingestion_service.py::_version_ordering()`'s own
    docstring for the full, explicit reasoning.
  * **Processing is synchronous.** A large batch is processed inline,
    within the request, up to the existing 1000-record cap — there is
    no background/async processing. `EnterpriseIngestionBatch.status`'s
    `RECEIVED` value is the seam a future asynchronous implementation
    would use; no caller can currently observe that state.
  * **Only the JSON API path is implemented.** CSV/XLSX upload, a
    webhook receiver, a database connector, and an event-stream consumer
    are all documented future extension points (see
    `docs/INTEGRATION_GUIDE.md` §16) — the generic contract underneath
    them is built; the connectors themselves are not.
  * **No update endpoint for an ingestion source beyond its
    active/inactive status.** `PATCH .../data-sources/{id}/status` is
    the one mutation this milestone built; renaming a source or changing
    its `system_identifier`/`schema_version`/`config_metadata` after
    creation is not yet possible via the API.
  * **A rejected record's payload is retained only on its own tracking
    row**, not archived anywhere else — if that row is ever deleted, the
    original content is gone; SIE does not currently prune these rows,
    so this is a future-maintenance consideration, not an immediate gap.
* **Real-World Data Validation & Intelligence Calibration v0.1's own
  genuine limitations:**
  * **Retrospective trend reconstruction over a one-time bulk historical
    backfill will appear degenerate** (collapsed into the single most
    recent bucket) unless the data was ingested with a realistic,
    near-real-time cadence — a direct, correct consequence of
    `events_as_of()`'s per-bucket point-in-time guarantee, not something
    this milestone changed. See this file's own ["A real calibration
    finding"](#a-real-calibration-finding-point-in-time-correctness-and-bulk-backfilled-history)
    section and `docs/CALIBRATION_METHODOLOGY.md` for the full
    explanation and what a real bulk-migration integration would need to
    account for (backdating `ingestion_time` realistically, or querying
    with `strict_point_in_time=False` for that specific historical
    reconstruction use case — neither built here, both out of scope).
  * **Five controlled, synthetic scenarios are not a statistically
    representative sample of any real organization**, and calibration
    against them is not a precision/recall/accuracy metric against real
    ground truth (there is none to measure against yet). An `EXPECTED`
    calibration outcome means the existing code behaves as designed on
    this scenario, nothing more.
  * **Anomaly and signal thresholds calibrated here are this codebase's
    existing, unmodified configuration** (`INTELLIGENCE_*` settings) —
    calibration confirms they fire/don't fire as designed, not that
    those specific threshold values are the right ones for any
    particular real deployment.
  * **The terminology-mapping vocabulary
    (`app/intelligence/terminology_mapping.py`) covers a representative,
    not exhaustive, set of real-world aliases** per domain. An
    unrecognized term is quarantined/flagged, never guessed — by design
    — but that means a real integration will likely need its alias
    tables extended before go-live; there is no configuration UI or
    per-tenant override for this yet, only the module's own Python
    tables.
  * **`generate_label()` (predictive dataset construction) does not
    filter on `ingestion_time`**, unlike every other analytics/signal
    call in this codebase — an existing, prior-milestone design choice
    (labels are computed with full hindsight from already-collected
    historical data, not as a live "as of now" query) confirmed, not
    changed, by this milestone's predictive-readiness tests.
* **Real Enterprise Dataset Validation Foundation v0.1's own genuine
  limitations:**
  * **No real, anonymized customer dataset has been evaluated yet.**
    This milestone builds and validates the reusable framework itself
    against a synthetic, clearly-labeled fixture only — see
    `docs/ENTERPRISE_DATASET_VALIDATION_GUIDE.md` §12. Running it
    against a real dataset, and everything that finding might surface,
    is genuinely future work.
  * **The terminology review structure covers exactly the domains
    `terminology_mapping.py` already covers** (event type, event
    subtype, training status, maintenance status) — a status field on a
    `CORRECTIVE_ACTION` or other event type outside that set is not
    walked by `extract_term_observations()`; extending it means adding a
    new alias table to `terminology_mapping.py` first, not something
    this module invents on its own.
  * **`HseExpertReview` has no HTTP API yet** — only a service-layer
    read/write path (`app/services/hse_review_service.py`). Adding
    `POST/GET/PATCH` routes for it (with the same
    `RequestContext`/`authorize_context()` authorization every other
    resource uses) is a natural, small future extension, not built here
    to keep this milestone's scope to the validation framework itself.
  * **`PredictiveReadinessReport`'s exclusion reasons are coarse**
    (`NO_HISTORICAL_DATA`, or a caught exception's own class name) —
    real datasets may surface exclusion patterns worth their own named
    category; the harness reports whatever it actually observes rather
    than pre-guessing every possible real-world failure mode.
  * **Late-arriving-record detection uses a fixed 24-hour threshold**
    (`_LATE_ARRIVAL_THRESHOLD_HOURS` in
    `app/validation/enterprise_dataset_validation.py`) — a simple,
    documented default, not a value calibrated against any real
    integration's actual reporting cadence.
