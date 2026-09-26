# Database Boundary — Public SIE / Commercial Core

Status: schema separation implemented, within one shared PostgreSQL
database. Full physical database separation and a real Commercial Core
API are deliberately **not** implemented by this milestone — see
"Future Boundary" below.

## 1. Current state

`Thundhai/SIE` and `Thundhai/SIE-Commercial-Core` share one PostgreSQL
database. Two schemas now exist in it:

- **`public`** — Public SIE-owned tables. Everything not listed below.
- **`commercial_core`** — Commercial-Core-owned tables, created and
  moved into this schema by migrations `0031`-`0035` in this
  repository's own Alembic chain (Commercial Core has no live migration
  chain of its own — see its `migrations_reference/README.md`).

This is **schema separation**, not database separation: both schemas
live in the same physical database, so a cross-schema foreign key is a
real, PostgreSQL-enforced constraint, not a soft reference.

## 2. Ownership — tables moved into `commercial_core`

| Table | Migration | Notes |
|---|---|---|
| `ontology_concepts` | `0032` | See §4 — the one genuinely shared-dependency table |
| `recommendation_candidates` | `0033` (new table, provisioned directly here) | No Public SIE model — see §5 |
| `dataset_versions` | `0034` | Self-contained predictive-modeling cluster |
| `feature_snapshots` | `0034` | " |
| `model_registry_entries` | `0034` | " |
| `model_approvals` | `0034` | " |
| `model_review_flags` | `0034` | " |
| `predictions` | `0034` | " |
| `prediction_outcomes` | `0034` | " |
| `intelligence_decisions` | `0035` | +additive `recommendation_candidate_id` column from `0033` |
| `intelligence_outcomes` | `0035` | |
| `intelligence_outcome_verifications` | `0035` | |
| `intelligence_learning_candidates` | `0035` | |
| `intelligence_learning_candidate_governance_decisions` | `0035` | |
| `organizational_memories` | `0035` | |
| `organizational_memory_governance_decisions` | `0035` | |
| `terminology_mapping_decisions` | `0035` | See §3 correction |
| `hse_expert_reviews` | `0035` | See §3 correction |

## 3. Correction to an earlier draft classification

An earlier pass over this repository alone found no live Public SIE
service or router touching `terminology_mapping_decisions`/
`hse_expert_reviews` after M43-IP-03, and provisionally called them
"orphaned, deletion candidates." Checking `Thundhai/SIE-Commercial-Core`
directly (not assumed) found both tables have real, active owners there:
`app/services/{hse_review_service,terminology_reprocessing_service,
terminology_decision_artifact_service,terminology_calibration_service,
ontology_terminology_integration_service}.py`. Both belong in the
Commercial-Core-owned move (§2), not a separate "possibly dead" cleanup.
Neither table was deleted at any point — this only corrects which
schema they belong in.

## 4. `ontology_concepts` — shared-dependency table

**Ownership**: Commercial-Core-owned. Its full governance lifecycle
(propose/approve/reject/deprecate, permission-gated) lives exclusively
in `app/services/ontology_governance_service.py` in
`Thundhai/SIE-Commercial-Core` — M43-IP-03 already removed the
equivalent service from Public SIE.

**Public SIE's read dependency**: `RiskAssessmentFinding.risk_area_concept_id`
→ `commercial_core.ontology_concepts.id`, `ON DELETE RESTRICT`,
`NOT NULL`. `app/risk_assessment/risk_area_resolution.py::
resolve_risk_area_concept()` is the one place this is read, restricted
to `status == APPROVED` and `is_risk_area_eligible == True` rows.

**Why the FK is a real cross-schema FK, not a soft reference or a
contract call.** Because both schemas are in the same database, this
constraint enforces exactly as it did before the move — a concept
referenced by a finding still cannot be deleted; a finding still cannot
reference a nonexistent or non-approved concept. Converting this to a
soft UUID reference or a `sie-contract` DTO call is explicitly deferred
to whichever future milestone performs full physical database
separation (see §7) — doing so now would weaken a real guarantee to
solve a problem schema separation doesn't have.

**Migration `0017`'s seed data is unaffected.** Migration `0014` still
creates `ontology_concepts` in `public` and migration `0017` still seeds
its 11 GLOBAL rows there, unmodified — neither historical migration was
edited. Migration `0032` runs after both, on every install (fresh or
upgrade alike), and relocates whatever the table already contains at
that point — a fresh install and an already-upgraded database converge
on the identical final state.

## 5. `recommendation_candidates` — schema-only port, no application code

SIE Milestone 43C's `recommendation_candidates` table (Commercial Core's
own `migrations_reference/0031_sie_milestone_43c_recommendation_generation.py`)
is created directly in `commercial_core`, plus one additive
`intelligence_decisions.recommendation_candidate_id` column — migration
`0033` here. This repository provisions the *schema DDL only*: no
SQLAlchemy model for `recommendation_candidates` exists in
`Thundhai/SIE`, and nothing under `app/` imports
`app.recommendation.*` — Public SIE has no business reason to construct
or read a row in this table (every route that could is an unconditional
`501`, per M43-IP-03). `migrations/env.py`'s `include_object` filter
excludes this one table from `alembic check`/autogenerate comparisons,
so its absence from Public SIE's own models never shows up as a
spurious "drop" diff.

## 6. Cross-schema foreign keys (every one, unweakened)

| Source (commercial_core) | Target | `ON DELETE` |
|---|---|---|
| `ontology_concepts.organization_id` | `public.organizations` | CASCADE |
| `risk_assessment_findings.risk_area_concept_id` (public → commercial_core) | `ontology_concepts` | RESTRICT |
| `intelligence_decisions.site_id` | `public.sites` | SET NULL |
| `intelligence_decisions.linked_action_id` | `public.safety_actions` | SET NULL |
| `intelligence_decisions.{decided_by_user_id,...}` / every table's actor columns | `public.users` / `public.api_clients` | SET NULL |
| `intelligence_outcomes.decision_id` (composite, +organization_id) | `commercial_core.intelligence_decisions` | CASCADE |
| `intelligence_outcome_verifications.outcome_id` (composite) | `commercial_core.intelligence_outcomes` | CASCADE |
| `intelligence_learning_candidates.{outcome_id,verification_id}` (composite) | `commercial_core.intelligence_outcomes` / `intelligence_outcome_verifications` | CASCADE |
| `intelligence_learning_candidate_governance_decisions.candidate_id` (composite) | `commercial_core.intelligence_learning_candidates` | CASCADE |
| `organizational_memories.learning_candidate_id` (composite) | `commercial_core.intelligence_learning_candidates` | CASCADE |
| `organizational_memory_governance_decisions.memory_id` (composite) | `commercial_core.organizational_memories` | CASCADE |
| `terminology_mapping_decisions.organization_id` | `public.organizations` | CASCADE |
| `terminology_mapping_decisions.hse_expert_review_id` | `commercial_core.hse_expert_reviews` | SET NULL |
| `hse_expert_reviews.reviewer_user_id` | `public.users` | SET NULL |
| `recommendation_candidates.organization_id` | `public.organizations` | CASCADE |
| `model_registry_entries.dataset_version_id` | `commercial_core.dataset_versions` | SET NULL |
| `predictions.{model_id,feature_snapshot_id}` | `commercial_core.model_registry_entries` / `feature_snapshots` | SET NULL |
| `prediction_outcomes.prediction_id` | `commercial_core.predictions` | CASCADE |
| `model_approvals.model_id` / `model_review_flags.model_id` | `commercial_core.model_registry_entries` | CASCADE |

`ALTER TABLE ... SET SCHEMA` (the mechanism every migration in §2 uses)
never drops or requires recreating a foreign key in either direction —
PostgreSQL resolves an existing constraint by the referenced table's
object identity, not by re-parsing a schema-qualified name. No
migration in this milestone issues a single `DROP CONSTRAINT`/
`ADD CONSTRAINT` — only `SET SCHEMA`.

## 7. Future boundary (not implemented here)

```
Now:    Public SIE + Commercial Core --> shared PostgreSQL database
                                          (public schema, commercial_core schema)

Later:  Public SIE --> Commercial Core API --> Commercial-Core-owned database
```

Full physical database separation, a real Commercial Core HTTP API for
`ontology_concepts` reads, a `RiskAreaConceptDTO` in `sie-contract`,
converting the cross-schema FKs in §6 to soft references, and event-
driven synchronization are all explicitly deferred to a later milestone
— none of them are authorized or attempted here. Commercial Core's own
`cc_service` (as of `CC-SERVICE-07`) has one real authenticated inbound
route (`POST /internal/v1/recommendations/eligibility`, M43B only) —
everything else, including any future `ontology_concepts` API, is
future work on Commercial Core's own side, with no Public SIE outbound
client yet.

## 8. Migration safety

Every migration in `0031`-`0035` is a schema-metadata operation
(`CREATE SCHEMA`, `ALTER TABLE ... SET SCHEMA`) or a purely additive
table/column creation (`0033`) — no row is read, copied, rewritten, or
deleted by any of them. Every downgrade is the exact inverse (`SET
SCHEMA` back to `public`, `DROP TABLE`/`DROP COLUMN` for the additive
parts of `0033`). `0031`'s downgrade (`DROP SCHEMA` with no `CASCADE`)
fails loudly rather than silently dropping data if anything unexpected
remains in `commercial_core` — by migration order, `0032`-`0035`'s own
downgrades already empty it first.

## 9. Verification

- `tests/test_migrations.py` — every pre-existing per-revision
  downgrade/reupgrade round-trip test updated to assert against
  `commercial_core` (not `public`) wherever a table it checks is now at
  head in that schema; a new `commercial_core`-aware
  `_fresh_schema_engine()` (`search_path=public,commercial_core`) so
  the file's own pre-existing raw SQL keeps resolving unqualified table
  names correctly regardless of which schema a given migration has
  moved them into by that point in the chain.
- `tests/test_database_boundary_separation.py` (new) — the schema
  exists; `ontology_concepts` is in `commercial_core` and not `public`;
  the FK is genuinely cross-schema; `RESTRICT` still blocks deleting a
  referenced concept; `resolve_risk_area_concept()` still resolves
  correctly; the 11 seed concepts survive a fresh migration; upgrading
  from the pre-boundary state converges with a fresh install and
  downgrades cleanly; `governing_standards`/
  `organization_governing_standards` remain in `public`, unmoved; no
  `app/` file references `app.recommendation.*` or
  `recommendation_candidates`.
- `tests/conftest.py`'s SQLite-backed engine gets
  `schema_translate_map={"commercial_core": None}` so every existing
  SQLite-based test keeps passing unchanged — `commercial_core`-schema
  tables collapse onto SQLite's own single namespace for that suite
  only; real Postgres (CI, `alembic upgrade head`) uses the actual
  schema.
- `migrations/env.py` gains `include_schemas=True` (required for
  `alembic check`/autogenerate to diff against `commercial_core` at
  all) and the `include_object` filter from §5.

## 10. Known limitations, disclosed

- Real PostgreSQL validation (`alembic upgrade head` against a genuine
  multi-schema database, the new `test_database_boundary_separation.py`
  Postgres-marked tests, `alembic check`'s autogenerate diff) was not
  run in this sandbox — no reachable PostgreSQL/Docker here, same
  disclosed limitation as M43-IP-03. CI's real Postgres service
  container is the authoritative check.
- `ontology_concepts`' governance write-path gap (no API, on either
  side, for an organization to propose a new org-specific risk-area
  concept) is pre-existing since M43-IP-03, unrelated to this
  milestone, and not addressed here.
