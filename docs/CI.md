# Continuous Integration

**SIE Milestone 19: Continuous Integration & Quality Gate Foundation v0.1.**
CI infrastructure only — this workflow (`.github/workflows/ci.yml`) runs
the repository's existing backend and frontend checks for real, on
GitHub's own infrastructure, so every future milestone can be
independently verified rather than relying only on locally reported
results. It does not add, change, redesign, or skip any of those checks
— it runs the exact commands a contributor already runs locally.

## What CI checks

### Backend job

Runs on Ubuntu, against a real **PostgreSQL 16 + pgvector** service
container (`pgvector/pgvector:pg16` — the same image
`backend/docker-compose.yml` uses for local development; upstream
PostgreSQL 16 with the pgvector extension available to enable, not a
fork or a substitute). In order:

1. Install `backend/requirements.txt`.
2. Create the separate `sie_test` database (the application's own `sie`
   database is created by the service container itself), then enable and
   **verify** the `vector` extension is actually present on both
   databases — a real assertion that fails the job if pgvector genuinely
   isn't available, not an assumption.
3. `alembic upgrade head` against a fresh database — proves the full
   migration history applies cleanly end to end.
4. `python -m pytest -q` — the full backend suite, including the
   `@pytest.mark.postgres`-marked tests that need real pgvector operators
   (`tests/postgres_support.py`) and would otherwise self-skip. Nothing
   here is skipped, faked, or made non-fatal.
5. `alembic check` — verifies there is no autogenerate-detectable drift
   between the current models and the migration history's head state.

**Resolved (SIE Milestone 19A: Migration/Model Drift Resolution).** Step 5
originally failed on every run — a real, pre-existing condition Milestone
19's own first CI run correctly surfaced, not something it introduced:
migration `0006_semantic_embeddings` creates a raw composite index
(`ix_knowledge_chunk_embeddings_model_identity`) that
`app/models/embedding.py` never declared a matching `Index(...)` for, so
every `alembic check`/`--autogenerate` run proposed dropping a real,
still-used index (`RetrievalService._model_clause()` filters on exactly
that `(provider, model_name, model_version)` triple for every retrieval
search — confirmed before making this change). The fix is metadata-only:
`app/models/embedding.py`'s `__table_args__` now declares that same
index (same name, same three columns, non-unique) — the index itself
already existed in the database from migration 0006, so no new migration
was needed or added, and no existing migration was edited.
`tests/test_migrations.py::test_alembic_check_reports_no_drift_after_upgrade_head`
guards against this regressing silently — it runs the same
autogenerate-diff comparison `alembic check` does against a freshly
migrated, real PostgreSQL 16 database and fails if models and migrations
ever disagree again.

### Frontend job

Runs on Ubuntu using **Bun** — this repository's lockfile is `bun.lock`
(no `package-lock.json`/`yarn.lock`/`pnpm-lock.yaml` exists), so Bun is
the project's own established package manager, not a substitution this
workflow invented. `bun run <script>` executes the exact script
`package.json` already defines; nothing here redefines `test`, `lint`,
or `build`.

1. `bun install --frozen-lockfile`
2. `bun run test` (Vitest)
3. `bun run lint` — **exactly** what `package.json` already defines
   `lint` to be (`tsc --noEmit`); this workflow does not redesign the
   linting architecture.
4. `bun run build` (production Vite build)

## When CI runs

- Every push to `main` or any `claude/**` branch.
- Every pull request targeting `main`.
- On demand, via `workflow_dispatch`.

Branch protection (making these checks *required* before a PR can merge
to `main`) is deliberately **not** enabled by this milestone — see its
own completion report. That's a follow-on step once CI has been observed
running reliably across several commits.

## What a green build means — and doesn't

A green build means the repository's own existing automated checks
(backend migrations + pytest, frontend tests + typecheck + build) passed
against that exact commit, on GitHub's infrastructure, independent of any
locally reported result. **It is not a claim that SIE is
production-ready** — it does not cover production authentication (still
an open, separately-scoped item — see `docs/FRONTEND_ARCHITECTURE.md`
§7), does not run against real enterprise data, does not contact any
external LLM provider, and does not evaluate UX, security, or
performance beyond what the underlying test suites already assert.

## Environment / credentials

Every credential in the workflow (`sie`/`sie`, the local database
names) is an ephemeral, CI-only value scoped to the job's own service
container — the same defaults `backend/docker-compose.yml` already uses
for local development, never a real environment's credentials. No
secret, API key, or production credential is used or required; CI never
contacts an external LLM provider or touches real enterprise data.
