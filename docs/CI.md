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

**Known limitation, stated plainly:** step 5 currently fails, and always
will until someone changes `app/models/embedding.py` (out of scope for
this milestone — see below). This is a real, pre-existing condition, not
something Milestone 19 introduced: migration `0006_semantic_embeddings`
creates a raw composite index
(`ix_knowledge_chunk_embeddings_model_identity`) that
`app/models/embedding.py` has never declared an equivalent `Index(...)`
for. Every migration from `0007` through `0015`'s own docstring already
calls this out by name as a known, pre-existing, deliberately-untouched
drift predating that migration. This CI workflow does not paper over it
— `alembic check` runs unsuppressed and the backend job genuinely fails
on it, exactly as a real drift should make it fail. Fixing it means
editing a SQLAlchemy model, which SIE Milestone 19 (CI infrastructure
only, no application changes) is explicitly not scoped to do. See the
milestone's own completion report for the exact CI run this was observed
on.

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
