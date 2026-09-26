# M43-IP-03: Public SIE Extraction / Cleanup (rebased)

**Status: implemented on branch `claude/sie-m43-ip-03-rebased`, not merged to
`main`.** This is a rebase-and-reapply of the original M43-IP-03 work
(`claude/sie-m43-ip-03-public-extraction`, three commits, never merged) onto
the current `main` tip — 30 commits had landed on `main` since that branch's
own baseline, so its diff was not cherry-picked directly; it was reconciled
against the current tree per this milestone's own instructions (§1 below).

- **Baseline** (this branch's parent): `main` @
  `6aa15ab59ae60b4bea49cf43a11a458ff3537be5`.
- **Original M43-IP-03 branch's own baseline**: `main` @
  `053bc4836cacd8edc58677539028d8a078f8676d` — 30 commits behind the baseline
  above.
- Commercial Core (unmodified by this milestone, not touched, not verified
  in this session — a separate repository this session has no access to):
  unchanged from whatever the original M43-IP-03 branch recorded.

## 1. How the rebase was actually done (not a blind cherry-pick)

1. Computed the merge-base of the original M43-IP-03 branch and current
   `main`: `053bc48` — confirming the reported "~3 commits ahead / 30 behind."
2. Diffed the original branch against `053bc48` to get its full, isolated
   change set (220 files, +1443/-49744 lines) — the actual set of file
   paths it touched, independent of unrelated `main` history.
3. For **every one of those paths**, diffed `053bc48` against the current
   baseline (`6aa15ab`) to determine whether `main` had changed that same
   file in the 30-commit gap. Result: **all but 6 paths were byte-identical**
   between `053bc48` and `6aa15ab`. The 6 that differed:
   `tests/test_intelligence_decisions_api.py`,
   `tests/test_intelligence_outcomes_api.py` (both gained new test functions
   on `main` after the original branch's baseline — see §9),
   `tests/test_migrations.py`, `tests/test_governing_standard_api.py`,
   `tests/test_governing_standard_concurrency.py`,
   `tests/test_governing_standard_service.py` (none of these last four were
   ever touched by the original branch at all — pure `main`-side additions,
   unrelated to this milestone's scope; see §8).
4. Because 214 of 220 touched paths were provably unchanged at their common
   ancestor, the original branch's own diff for those paths was **applied
   directly** (`git diff 053bc48..<old-branch> -- backend ':(exclude)...' |
   git apply`) rather than hand-reconstructed — this is not "blindly
   cherry-picking the old branch," it is confirming zero divergence and then
   reapplying a verified-identical change, which is what "reconcile against
   the current tree" reduces to when the tree has not actually moved for a
   given file. The 2 divergent test files were deleted directly (not
   patched) since both were being deleted outright regardless (§9). The
   documentation file you are reading was written fresh for this baseline,
   not copied.
5. Every new-in-the-gap file this milestone's scope could plausibly touch —
   the entire M43A Governing Standards feature (`app/api/v1/
   governing_standards.py`, its model/schema/service files, migration
   `0030`, two new dev bootstrap scripts, `core/config.py`'s
   `SIE_DEV_DEMO_DATA` flag, `core/openapi.py`'s new tag) — was independently
   read and its imports checked (see §8). None of it imports anything this
   milestone extracts; none of it is reclassified.

## 2. What changed, in one paragraph

Every file confirmed private by the original M43-IP-03 audit (traced back
to Commercial Core's own `PRIVATE_APP_FILES.txt`) has been removed from this
repository's working tree on this branch — the enterprise-intelligence,
predictive-modeling, RAG-orchestration, and ontology/terminology-governance
*algorithms*. Every HTTP endpoint that depended on one of those algorithms
is preserved (same path, same method, same authorization requirement) but
now returns `HTTP 501` through a single, explicit
`app/integrations/commercial_core.py` seam, rather than computing anything.
Nothing was renamed, wrapped, or wired through a new "public" module that
still contains the private logic (re-verified independently for this
baseline — see §7).

## 3. Reclassified/retained PUBLIC inside `app/intelligence/`

Unchanged from the original branch's own classification (re-verified: these
six files are byte-identical to the original branch's baseline, so the
original reasoning still applies verbatim to the current tree):
`adapters.py`, `ingestion_service.py`, `enterprise_ingestion.py`,
`schemas.py`, `normalization.py`, `validation.py`, `enums.py`, `temporal.py`
— generic ingestion/point-in-time infrastructure, load-bearing for public
code (`app/models/safety_event.py` imports `enums.py` directly), no
statistical/ML content. Every other file ever in that directory (27 files)
is deleted.

`app/risk_assessment/risk_area_resolution.py`, `risk_matrix.py`,
`reporting.py` remain PUBLIC, unchanged, same reasoning as the original
branch (§4 there). `candidate_generation.py` is deleted (calls the private
enterprise-intelligence engine).
`app/risk_assessment/risk_area_ontology_seed.py` **stays public and
unmodified** — see §5, the migration-0017 dependency.

## 4. New-since-original-branch: M43A Governing Standards — classified PUBLIC

`app/api/v1/governing_standards.py`, `app/models/governing_standard*.py`,
`app/schemas/governing_standard.py`, `app/services/governing_standard_service.py`,
migration `0030_sie_milestone_43a_organizational_standards_governance.py`,
`scripts/bootstrap_dev_demo_data.py`, `scripts/bootstrap_dev_identity.py` did
not exist when the original M43-IP-03 branch was created; they landed on
`main` afterward (SIE Milestone 43A). Independently audited for this
rebase, not inherited from any prior classification:

- **Content**: an append-only SELECTED/RETIRED event log over an
  organization's chosen external regulatory/governance standards (ISO
  45001, OSHA, IOGP, ...), plus a GLOBAL/organization-scoped catalogue.
  `core/openapi.py`'s own tag description for this feature states
  explicitly: "Does not reason about APPLICABILITY to any region,
  industry, site, activity, or hazard — that remains a later milestone's
  job... nothing here recommends, infers, or auto-selects a standard."
- **Imports checked** (`app/api/v1/governing_standards.py`,
  `app/services/governing_standard_service.py`,
  `app/models/governing_standard.py`, `app/schemas/governing_standard.py`,
  both new bootstrap scripts): only base infrastructure
  (`app.api.deps*`, `app.core.*`, `app.models.base`/`enums`,
  `app.services.audit_service`/`permissions`) and the feature's own
  model/schema/service files. Zero imports of anything this milestone
  extracts.
- **Conclusion**: generic governance/compliance record-keeping, not a
  proprietary intelligence algorithm (no scoring, no prediction, no
  anomaly detection, no ML) — matches the task's own "risk assessment
  lifecycle... approvals... audit trail" style of generic-public
  functionality, not its "proprietary ... governance algorithms" list
  (that list is about the *terminology/ontology mapping* governance
  machinery already extracted in §2 — a different, already-deleted
  subsystem; this is regulatory-standard *selection* bookkeeping only).

`core/config.py`'s `SIE_DEV_DEMO_DATA` flag and `core/openapi.py`'s new tag
are the only other new-in-gap changes; both independently confirmed to have
no coupling to anything extracted. `tests/test_migrations.py`'s new
migration-0030 round-trip test and the three new
`tests/test_governing_standard_*.py` files are untouched by this milestone
— they test only this same public feature.

## 5. Migration dependency — preserved exactly

`migrations/versions/0017_sie_milestone_25a_governed_risk_area_taxonomy.py`
imports `RISK_AREA_SEED_CONCEPTS`/`RISK_AREA_SEED_ONTOLOGY_VERSION` from
`app/risk_assessment/risk_area_ontology_seed.py` directly, to seed/backfill
`OntologyConcept` rows during `alembic upgrade head`. Re-verified for this
baseline: the file is untouched (byte-identical to the original branch's
own already-corrected version), migration `0017` still imports it at the
same three names, and `alembic heads` reports a single head (`0030`) with
no branching. This is deliberately **not** reconstructed from memory — it
was never deleted on this branch.

## 6. Runtime seed dependency — preserved

`scripts/seed_dev_environment.py` is untouched relative to the original
branch's own already-fixed version (confirmed byte-identical at
`053bc48`↔`6aa15ab` before the patch, so the original branch's fix for it
applies unmodified): it no longer imports from the deleted
`tests/fixtures/enterprise_scenarios.py`; its generic
`RawSafetyEventPayload`-builder logic lives in the new, public
`scripts/dev_seed_events.py`; it creates its demo risk assessment with
`generate_candidates=False`.

## 7. Repository-wide verification performed this session

- **AST-based import scan**, every `.py` file under `backend/` (excluding
  `.venv`/`__pycache__`), for an import of any of the ~40 deleted module
  paths: **zero hits**.
- **`app.main` import/startup check**: succeeds, 141 routes registered.
- **OpenAPI schema generation**: succeeds, 110 paths.
- **Distinctive private symbol grep** (`compute_enterprise_intelligence`,
  `EnterpriseIntelligenceService`, `compute_risk_score`,
  `RiskScoreCalculator`, `detect_enterprise_anomalies`,
  `compute_enterprise_trend`, `compute_concentration`,
  `TerminologyMappingEngine`, `OntologyGovernanceService`,
  `generate_candidates` (as a function def), `PredictiveModel`,
  `RAGService`, `build_evidence_selection`) across all tracked `*.py`:
  **one hit**, a docstring cross-reference in
  `app/schemas/field_intelligence_context.py` (see §10) — not executable
  code, not a leak.
- **`git diff --stat` sanity check on the two edited router files with a
  new-in-gap divergence** (`intelligence_decisions.py`,
  `intelligence_outcomes.py`): confirmed byte-identical to `053bc48`, so
  the original branch's router-level edit (gutting each to a `501`) applies
  to the current router content exactly.

## 8. The `app/integrations/commercial_core.py` seam

Unchanged in design from the original branch (the file has zero coupling
to anything that changed in the 30-commit gap, so it was reapplied as-is):
`CommercialCoreClient` is an interface; `NotConfiguredCommercialCoreClient`
is the only implementation this repository ships, and it always raises
`CommercialCoreUnavailable` (`HTTP 501`) naming the capability and pointing
at this document. Deliberately not a live network/RPC client — Commercial
Core has no HTTP route layer of its own yet. `app/api/v1/risk_assessments.py`'s
`generate_candidates=true` gate raises a plain `HTTPException(501, ...)`
rather than going through `commercial_core_client.unavailable(...)` — an
inherited, pre-existing stylistic inconsistency from the original branch,
not introduced by this rebase; both paths produce an honest `501` before
any state changes, so it was left as originally implemented rather than
altered outside this milestone's stated scope.

## 9. Endpoints affected

Same list as the original branch (all router files carrying this behavior
were confirmed byte-identical at the common ancestor, so the behavior is
unchanged): ingestion (`POST/GET .../events`, `.../events/batch`) and the
full Risk Assessment lifecycle except §11's one gate are unaffected;
`analytics/{summary,trends,signals}`, `features`, `enterprise`,
`sites/{id}`, `context`, `sites/{id}/context`, `memory-context`,
`sites/{id}/memory-context`, `attention`, `sites/{id}/attention`,
`decisions*`, `learning-candidates*`, `outcomes*`, `organizational-memory*`,
`predictions*`, `knowledge/rag/query`, and model-governance
`datasets*`/`models*` all return `501`.

**New-since-original-branch test content, resolved by this rebase**:
`main` had gained two new test functions each in
`tests/test_intelligence_decisions_api.py`
(`test_decision_creation_creates_an_audit_record`,
`test_decision_creation_audit_failure_leaves_no_partial_state`) and
`tests/test_intelligence_outcomes_api.py` (the equivalent pair for
outcomes) after the original branch's baseline — both pairs exercise the
same now-`501` endpoints end-to-end (asserting `201` + `AuditLog` rows +
transactional-rollback-on-fault-injection). Since the router files
themselves are unchanged and already fully `501`, and the entire
containing test files were already being deleted outright by the original
branch's own classification (609 and 677 lines respectively, full-file
deletions), these two new test functions are removed along with the rest
of their files by the same reasoning — **not independently re-verified
against `Thundhai/SIE-Commercial-Core`** in this session (that repository
is outside this session's repository scope); disclosed here rather than
assumed equivalent coverage exists, per this milestone's own "do not claim
verification that was not performed" rule.

## 10. Schemas — `field_intelligence_context.py` inert, not deleted

`app/schemas/field_intelligence_context.py` (`FieldIntelligenceContextRead`
and its nested shapes) is no longer imported by `app/api/v1/intelligence.py`
— the `/context` and `/sites/{id}/context` handlers `raise` before ever
touching a response schema. The file is left in place, unused, rather than
deleted (same disclosed policy the original branch already applied to
`app/schemas/enterprise_intelligence.py`'s nested shapes) — its own
docstring still names `compute_enterprise_intelligence()` in prose; this is
a stale cross-reference in a dead schema, not executable coupling. Flagged
here as a documentation-only follow-up candidate, not fixed in this
milestone (out of scope; would be a schema-cleanup change, not a boundary
change).

## 11. Two narrow behavior changes inside otherwise-public endpoints

Unchanged from the original branch: `POST /api/v1/risk-assessments?generate_candidates=true`
returns `HTTP 501` immediately, before any assessment row is created (verified by reading
the current `create_assessment()` handler directly — the check is the
first statement in the function body, before site/owner validation,
idempotency lookup, or any `db` write). `generate_candidates=false` (the
default) is unaffected. `RiskAssessmentDetailRead.intelligence_context` is
always `None` now (was a computed field), kept rather than removed for
response-shape compatibility.

## 12. Database boundary — still deferred

No SQLAlchemy model was removed and no migration was touched by this
milestone, on this branch, exactly as the original branch already decided.
Current state remains one shared database/schema between Public SIE and
Commercial Core's private-domain tables. Not resolved here — this
milestone's own scope is code/IP boundary, not schema separation.

## 13. Dependencies

`backend/requirements.txt`: unchanged from the original branch's own edit
(confirmed byte-identical baseline) — `scikit-learn`/`scipy` removed,
`numpy` kept (`sentence-transformers`' own dependency, used by the kept
`app/embeddings/provider.py`). **Not re-verified via a fresh venv install
in this session** — this repeats the original branch's own disclosed
limitation; a `pip check`/fresh-install pass against the edited
`requirements.txt` is a reasonable follow-up before this branch is
considered final.

## 14. Test suite

**Baseline** (this branch's parent, `main` @ `6aa15ab`, before any change
in this session): `python -m pytest -q` → **2070 passed, 235 skipped, 6
failed**. All 6 failures reproduced and confirmed to be a real Postgres
connection refused (`localhost:5432`) — this sandbox has no reachable
PostgreSQL server and no working Docker daemon, so the Postgres-marked/
Postgres-requiring tests (`@pytest.mark.postgres`-gated ones skip cleanly;
these 6 are migration-round-trip and evaluation-report-writer tests that
are not properly gated behind that marker) genuinely cannot run here. Not
a regression — reproduced identically before touching any file.

**After this milestone**: `python -m pytest -q` → **959 passed, 67
skipped, 5 failed**. All 5 remaining failures are the *same* Postgres-
connection-refused gap (one of the original 6,
`tests/evaluation/test_calibration_evaluation.py::test_zzz_write_calibration_report`,
no longer exists — that entire file was itself private-domain test content
extracted by this milestone). **Zero new failures introduced.**

**Migrations**: `alembic heads` (SQLite, structural check only) reports a
single head, `0030` — unchanged, no branching introduced. A genuine
`alembic upgrade head` end-to-end run **was not performed** in this
session — migration `0006` requires a real PostgreSQL server with the
`pgvector` extension (`CREATE EXTENSION vector` has no SQLite equivalent),
and this sandbox has neither a reachable Postgres instance nor a working
Docker daemon. This is disclosed, not assumed passing; CI (which
provisions a real `pgvector/pgvector:pg16` service container) is the
authoritative check for this before merge.

**Seed script**: `scripts/seed_dev_environment.py` parses (AST check) with
no syntax errors; its own dedicated test file,
`tests/test_seed_dev_environment.py`, has both its tests correctly marked
`@requires_postgres` and both **skip** (not pass, not fail) in this
sandbox for the same reason as above. **Not run end-to-end against a real
database** in this session — disclosed, not claimed.

**Import/startup checks**: `app.main` imports cleanly (141 routes).
**OpenAPI generation**: succeeds (110 paths). **Lint**: `ruff check .` —
baseline (pre-change) 1113 findings; after this milestone, 902 findings
(fewer, expected — a large volume of deleted code removed its own
pre-existing findings with it; the remainder is pre-existing style debt
across the whole codebase, unrelated to and not introduced by this
milestone, and out of this milestone's scope to fix).

## 15. What this milestone did not do

Did not modify Commercial Core (no access to that repository in this
session). Did not merge anything. Did not implement M43B, recommendation
logic, AI-alternative reasoning, a Commercial Core HTTP service, a message
queue, new predictive models, new RAG intelligence, or any frontend
change. Did not rewrite Git history. Did not delete migrations or models.
Did not touch `claude/sie-m43a-organizational-standards` (that branch is
unrelated to this one; M43A's actual content already reached `main`
directly, independently of this rebase).

## 16. Recommended next steps

1. Run this branch's full suite in CI (real PostgreSQL + pgvector service
   container) to get the genuine `alembic upgrade head` and
   Postgres-marked test results this sandbox could not produce.
2. An independent audit re-verifying this rebase's own claims against the
   actual diff, before merge.
3. A DB-boundary milestone to resolve §12.
4. Independent re-verification, against `Thundhai/SIE-Commercial-Core`
   directly, that the two newly-disclosed test-coverage removals in §9
   (the audit-record and atomicity-fault-injection tests added to `main`
   after the original branch's baseline) have an equivalent private-domain
   test on the Commercial Core side — this session could not check that
   repository.
5. A decision on `app/schemas/field_intelligence_context.py` and
   `app/schemas/enterprise_intelligence.py`'s now-fully-inert nested
   schema shapes (§10) — delete, or leave as documented-inert field
   shapes.
6. A fresh-venv `pip install -r requirements.txt` + full suite run to
   independently confirm §13's dependency-removal claim (time-boxed out of
   this session, as it was in the original branch's own).
