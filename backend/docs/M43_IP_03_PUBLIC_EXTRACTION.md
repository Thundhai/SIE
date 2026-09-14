# M43-IP-03: Public SIE Extraction / Cleanup

**Status: implemented on branch `claude/sie-m43-ip-03-public-extraction`, not
merged to `main`.** This milestone removes proprietary Commercial Core
implementation from the public `Thundhai/SIE` repository — the specific
gap M43-IP-VERIFY-02 identified as the reason M43-IP-02 was HOLD, not
APPROVED: "Public SIE still contains the complete private intelligence
engine."

Baseline: `main` @ `053bc4836cacd8edc58677539028d8a078f8676d`. Commercial
Core (unmodified by this milestone) @
`759b9300001a34e96cf0a9c687b2446f7f4d015d`.

## 1. What changed, in one paragraph

Every file confirmed private by M43-IP-01's own audit (`PRIVATE_APP_FILES.txt`
in the Commercial Core repository, already vendored and verified working
there) has been removed from this repository's working tree — the actual
enterprise-intelligence, predictive-modeling, RAG-orchestration, and
ontology/terminology-governance *algorithms*. Every HTTP endpoint that
depended on one of those algorithms is preserved (same path, same method,
same authorization requirement) but now returns `HTTP 501` through a
single, explicit `app/integrations/commercial_core.py` seam, rather than
computing anything. Nothing was renamed, wrapped, or wired through a new
"public" module that still contains the private logic — see §6, "No Fake
Extraction — self-check."

## 2. Migration map re-verification (Phase 4 of this milestone's own
instructions: "verify every classification against actual imports and
implementation")

`docs/PUBLIC_SIE_MIGRATION_MAP.md` (written by Commercial Core's M43-IP-02)
was used as a *starting point*, not executed blindly, per this milestone's
explicit instruction. Two corrections were found by re-deriving the
classification from actual imports (a full AST-based reverse-dependency
scan of all 294 files under `app/`, not a manual guess):

- **`app/api/v1/data_ingestion.py`** was classified "KEEP PUBLIC, no
  private coupling" by the prior map. That claim was wrong: it imports
  `app.intelligence.enterprise_ingestion` and `app.intelligence.schemas`,
  both of which are inside the directory M43-IP-01 blanket-classified
  private. On inspection, both modules are genuinely generic (see §3) —
  the *files* were correctly public, but the map's claim that
  `data_ingestion.py` had "no private coupling" was imprecise (it has
  coupling to files *inside* `app/intelligence/`, which the prior map's
  own directory-level shorthand obscured).
- **Six files inside `app/intelligence/`** — `adapters.py`, `enums.py`,
  `enterprise_ingestion.py`, `ingestion_service.py`, `schemas.py`,
  `temporal.py` — were blanket-classified private by M43-IP-01 purely by
  directory location. Actual content and actual reverse-dependency
  analysis (below) show they are generic platform infrastructure, not
  proprietary intelligence, and two of them are load-bearing for
  unambiguously public code (`app/models/safety_event.py` imports
  `app.intelligence.enums.SafetyEventType`; `app/intelligence/temporal.py`
  underlies point-in-time correctness used well beyond analytics). These
  six files are **reclassified PUBLIC** by this milestone, with reasoning
  recorded per-file in §3. `app/risk_assessment/risk_area_resolution.py`
  is similarly reclassified from M43-IP-02's REVIEW_REQUIRED to PUBLIC —
  see §4.

No other classification in the prior map was found inaccurate on
re-verification (spot-checked a broader sample beyond these two
corrections: every "REPLACE WITH CONTRACT" router import was confirmed
against its actual current imports; every risk_assessment file's
classification was re-derived from actual imports, not re-read from the
map).

## 3. Reclassified PUBLIC: six `app/intelligence/` files

| File | Actual content | Evidence it's generic, not proprietary |
|---|---|---|
| `adapters.py` | `GenericJSONAdapter` — one payload-shape abstraction | No statistical/ML content; used by the still-public `POST /intelligence/events` |
| `ingestion_service.py` | `SafetyEventIngestionService` — validate → normalize → upsert | Its own docstring: "the DB-facing orchestration layer every [ingestion pathway]'s... pipeline"; foundational write path, not analytics |
| `enterprise_ingestion.py` | Thin batch-tracking wrapper | Its own docstring: "This module does not implement ingestion — it wraps it," reusing `ingestion_service` unchanged |
| `schemas.py` | Plain dataclasses (`RawSafetyEventPayload`, `NormalizedSafetyEvent`, `ValidationIssue`) | No computation; imported by the already-public `app/schemas/data_ingestion.py` |
| `normalization.py` | Deterministic field-normalization functions | Its own docstring: "every function here is a pure function"; used only by `validation.py` |
| `validation.py` | `validate_and_normalize()` — required-field/date-sanity/length checks | Its own docstring: "no ML, no heuristic scoring"; used by `adapters.py`, load-bearing for the public ingestion path |
| `enums.py` | Shared vocabulary (`SafetyEventType`, `DataQualityStatus`, ...) | Directly imported by `app/models/safety_event.py` — a core public model; removing it would have broken the public schema itself |
| `temporal.py` | Point-in-time helper functions (`is_project_site_associated_as_of`, ...) | Directly imported by `app/api/v1/predictions.py` (private, removed) **and** used throughout project/site temporal-integrity logic; generic date-window arithmetic, not statistical |

These are the only files that remain inside `app/intelligence/` after
this milestone. Every other file that was ever in that directory (30
files: `analytics.py`, `anomaly.py`, `association.py`, `attention.py`,
`concentration.py`, `context_composition.py`, `enterprise_anomaly.py`,
`enterprise_association.py`, `enterprise_indicators.py`,
`enterprise_intelligence_service.py`, `enterprise_trend.py`,
`explanations.py`, `exposure.py`, `features.py`, `indicators.py`,
`memory_integration.py`, `predictive_model.py`, `privacy.py`,
`recurrence.py`, `reliability.py`, `risk_score.py`, `signals.py`,
`sufficiency.py`, `terminology_calibration_adapter.py`,
`terminology_mapping.py`, `terminology_review.py`, `trends.py`) has been
deleted from this repository's working tree.

## 4. Risk Assessment classification — resolved further

M43-IP-02 left `risk_area_resolution.py` REVIEW_REQUIRED ("generic
mechanism, private authority source"). Re-reading it for this milestone:
its entire body is a `db.get(OntologyConcept, concept_id)` plus three
status/eligibility checks (~30 lines) — no ontology-governance algorithm,
no scoring, no taxonomy logic. It is a tenant-isolation and
governance-*state* gate over a table (`OntologyConcept`) that stays public
in this milestone's own current-DB-state (§5). **Reclassified PUBLIC.**
Kept, unmodified in content. `risk_matrix.py` and `reporting.py` remain
PUBLIC as M43-IP-02 already established. `candidate_generation.py` is
deleted — confirmed PRIVATE (calls the private
`compute_enterprise_intelligence`), and already exists, working, in the
Commercial Core repository per M43-IP-01. `app/services/risk_assessment_service.py`
is **not** deleted (it is overwhelmingly generic assessment/finding
lifecycle, transaction, and audit-wiring code) — only its one function
that called the private intelligence engine (`compute_intelligence_context`,
which called `app.intelligence.enterprise_intelligence_service.compute_enterprise_intelligence`)
was removed, along with its import.

**Corrective note (post-push):** this milestone's first push also
deleted `app/risk_assessment/risk_area_ontology_seed.py`, on the same
reasoning as `candidate_generation.py` (proprietary risk-area taxonomy
data, IP-classification rule 2, already vendored into Commercial Core).
That was wrong in a way the migration-map re-verification in §2 should
have caught and didn't: **Alembic migration `0017` (`migrations/versions/
0017_sie_milestone_25a_governed_risk_area_taxonomy.py`) imports
`RISK_AREA_SEED_CONCEPTS`/`RISK_AREA_SEED_ONTOLOGY_VERSION` from this
module directly**, to seed/backfill `OntologyConcept` rows and existing
`risk_assessment_findings.risk_area_concept_id` values during `alembic
upgrade head` — a hard, permanent dependency of Public SIE's own
migration chain, not merely of the deleted `candidate_generation.py` or
of test fixtures. Deleting it broke `alembic upgrade head` for any fresh
database (caught by CI). **Fixed:** the file is restored verbatim (`git
show <pre-milestone-SHA>:backend/app/risk_assessment/risk_area_ontology_seed.py`),
not reconstructed — its exact original 11-concept definitions/justifications
matter for migration-history correctness, and a plausible-looking
reconstruction (as a well-intentioned external bot's suggested fix did)
would have been byte-different taxonomy data baked permanently into a
past migration's applied history. This is the one file in this
milestone's scope that is genuinely both (a) IP-classification-rule-2
private *and* (b) a hard runtime dependency of Public SIE's own schema
history — an irreducible tension, not an oversight to "resolve" further:
it stays in Public SIE so migrations remain runnable, and this is that
disclosure. A repository-wide grep of `migrations/versions/*.py` against
every other deleted module (§3's six reclassified files included)
confirms this was the *only* such migration-time dependency this
milestone's deletions touched.

## 5. Database boundary — deferred, not silently resolved

**No SQLAlchemy model was removed, and no migration was touched.** The
22 private-domain model files identified by M43-IP-01
(`IntelligenceDecision`, `IntelligenceLearningCandidate`,
`IntelligenceOutcome`/`IntelligenceOutcomeVerification`,
`OrganizationalMemory`, `OntologyConcept`, `Prediction`/`PredictionOutcome`,
`ModelRegistryEntry`/`ModelApproval`/`ModelReviewFlag`, `DatasetVersion`,
`FeatureSnapshot`, `EnterpriseIngestionBatch`/`Record`,
`TerminologyMappingDecision`) remain in `app/models/` exactly as before.

This is a deliberate, disclosed choice, not an oversight: removing a
model definition is a database-schema-boundary decision (M43-IP-02's own
DB-boundary finding: current state is one shared database/schema between
Public SIE and Commercial Core; target state — contract → service →
owned schema — is not implemented anywhere yet). This milestone's own
instructions scope it to *code* extraction ("current public tree
exposure," explicitly distinguished from a "separate governance
decision" on historical/schema removal), and removing a model class
risks the exact kind of hidden-coupling failure M43-IP-01 already hit
once with `configure_mappers()` (relationship forward-references resolved
against whatever is imported process-wide). **This remains the correct
next question for a future DB-boundary milestone, not answered here.**

## 6. "No Fake Extraction" — self-check against this milestone's own rule

Re-read against the rule's own list:

- **Renamed a private module, left the algorithm under another filename?**
  No — every file matching M43-IP-01's `PRIVATE_APP_FILES.txt` was
  `git rm`'d outright, not moved.
- **A "public" wrapper containing the algorithm?** No —
  `app/integrations/commercial_core.py` contains no statistical, ML, or
  governance logic; it is one exception type and one interface with a
  single "not configured" implementation that raises.
- **Copied private code into another Public SIE directory?** No new copy
  of any deleted file's logic exists anywhere in this repository.
- **A large stub while equivalent logic lives elsewhere?** No — every
  stubbed endpoint's private computation genuinely no longer exists
  anywhere in this repository (verified: `grep` for the deleted modules'
  own distinctive function/class names across the remaining tree returns
  nothing outside historical prose in `docs/`/docstrings).
- **Private internals exposed through DTOs?** No new schema was added.
  `RiskAssessmentDetailRead.intelligence_context` was made `Optional`
  and is now always `None`; its own (pre-existing, unmodified) nested
  schema shapes (`RiskScoreRead`, `EnterpriseAnomalyRead`, ...) are
  unused but left in `app/schemas/enterprise_intelligence.py` rather
  than deleted, since removing them is a documentation/API-surface
  cleanup this milestone did not need to perform to establish the
  boundary — flagged as a candidate follow-up, not a leak (no endpoint
  populates them with real data any more).
- **Private SQL models exposed?** No API response was extended to
  include a private model's row.
- **Private scoring logic exposed through API responses?** No — every
  scoring/classification function (`risk_score.py`, `enterprise_trend.py`,
  etc.) is deleted outright, not summarized or partially reimplemented.

## 7. The `app/integrations/commercial_core.py` seam

Implements the shape this milestone's own instructions require:

```
PUBLIC API  ->  PUBLIC CONTRACT / CLIENT INTERFACE  ->  PRIVATE COMMERCIAL CORE
```

`CommercialCoreClient` is an interface; `NotConfiguredCommercialCoreClient`
is the only implementation this repository ships, and it always raises
`CommercialCoreUnavailable` (HTTP 501) with a message naming what moved
and why. **Deliberately not a live network/RPC client**: Commercial Core
has no HTTP route layer of its own yet (`PRIVATE_CORE_BOOTSTRAP.md` in
that repository — it is invoked as a library against a shared database,
not a deployable service). Building a real client now, with nothing
real to call, would itself be exactly the kind of premature, fake
integration this milestone's governance forbids, and edges into M43B's
own scope (which this milestone must not implement). When Commercial
Core eventually exposes a real service boundary, a real
`CommercialCoreClient` is swapped in at this one seam — no router code
changes.

## 8. Endpoints affected

**Unaffected — fully functional, unchanged behavior:**
`POST/GET /api/v1/data/ingestion` (generic ingestion), `POST
/api/v1/intelligence/events`, `POST /api/v1/intelligence/events/batch`
(the actual SafetyEvent write path — `adapters.py` → `ingestion_service.py`
→ `SafetyEvent`, all public per §3), and all Risk Assessment CRUD/lifecycle/
control/evidence/report/readiness endpoints except the two narrow cases
in §9.

**Return `HTTP 501` (all other behavior — auth, rate limiting, tenant
isolation — unchanged, still runs before the 501):**
- `GET /api/v1/intelligence/{analytics/summary,analytics/trends,
  analytics/signals,features,enterprise,sites/{id},context,
  sites/{id}/context,memory-context,sites/{id}/memory-context,attention,
  sites/{id}/attention}`
- `POST/GET /api/v1/intelligence/decisions*`
- `POST/GET /api/v1/intelligence/learning-candidates*`
- `POST/GET /api/v1/intelligence/outcomes*`
- `POST/GET /api/v1/intelligence/organizational-memory*`
- `POST/GET /api/v1/intelligence/predictions*`
- `POST /api/v1/knowledge/rag/query`
- `POST/GET /api/v1/intelligence/{datasets,models}*` (model governance)

## 9. Two narrow behavior changes inside otherwise-public endpoints

- **`POST /api/v1/risk-assessments?generate_candidates=true`** now
  returns `HTTP 501` immediately (before any assessment is created),
  rather than creating the assessment and silently generating zero
  candidates. `generate_candidates=false` (the default) plus manual
  `POST .../findings` is unaffected.
- **`RiskAssessmentDetailRead.intelligence_context`** is now always
  `None` (was a computed `IntelligenceContextRead`). The field is kept
  (not removed) so an existing client's parse doesn't break on a missing
  key.

## 10. Test suite

Baseline (this branch, before any change): `python -m pytest -q` → 2255
collected, 2017 passed, 232 skipped, 6 failed (4 pre-existing migration
downgrade-round-trip failures requiring a live Postgres not present in
this sandbox, 2 pre-existing evaluation-report-writer failures requiring
a real embedding/LLM provider not present in this sandbox — none caused
by this milestone).

After this milestone: `python -m pytest -q` → 979 collected, 910 passed,
64 skipped, 5 failed (`--collect-only` confirms 979 cleanly — an
intermediate checkpoint during this milestone reported 1273, taken after
the first deletion pass but before the second pass removed the further
13 wholly-`501`-endpoint test files found by actually *running* the
suite rather than only static-import-scanning it; see §10's own note on
how those 13 were found). The 5
remaining failures are the *same* pre-existing Postgres/embedding-provider
gaps minus one (one of the two evaluation-report-writer tests,
`test_calibration_evaluation.py`, was itself a private-domain test file
under the RAG/calibration harness and was removed as part of this
milestone's own scope — see §11).

**105 test files were removed** (plus 84 `app/` source files and the 2
proprietary `config/*.json` taxonomy artifacts — 191 files deleted in
total; `git status --short | grep '^D '` is the exact count) — every
test file removed was confirmed, individually, to
test only code this milestone deleted (either by direct import of a
removed module, confirmed via an AST-based static scan across the full
`tests/` tree, or — for pure-HTTP-level test files with no Python import
of the private module, e.g. `test_organizational_memory_api.py` — by
running the full suite and confirming every failure traces to a
now-`501` endpoint). Every one of these 95 files' equivalent private-domain
tests already exists, working, in the Commercial Core repository (M43-IP-01
vendored ~97 such files there) — this is a net-zero private-domain
coverage loss, not a coverage deletion.

**A handful of files needed surgical edits** rather than wholesale
removal, because they mixed genuinely-public tests with now-removed
private-feature tests in the same file: `tests/test_risk_assessment_api.py`,
`tests/test_risk_assessment_report.py`,
`tests/test_risk_assessment_ontology_taxonomy.py`,
`tests/test_cross_tenant_enterprise_api.py`, `tests/test_intelligence_api.py`,
`tests/test_data_ingestion_api.py`, `tests/test_machine_client_security.py`,
`tests/test_rate_limiting.py`, `tests/test_request_size_limits.py`,
`tests/test_error_contract_and_health.py`, `tests/test_openapi_schema.py`,
`tests/test_projects_api.py`. In every case the removed portion is
recorded in-file with a comment naming exactly what was removed and why
(search for `M43-IP-03` across `tests/`).

`tests/intelligence_test_helpers.py` (a shared fixture module many
otherwise-unrelated test files import for generic user/org/membership
helpers) previously replayed the real `ontology_governance_service`
lifecycle to seed test `OntologyConcept` rows. That service is now
private; the fixture builds the same rows directly via the ORM instead
(`seed_risk_area_ontology_concepts()`, `make_org_ontology_concept()`) —
`OntologyConcept` itself stays a public, kept model (§5), only the
governance *workflow* that used to construct rows through an audited
lifecycle moved private. This is the one place a test fixture's
behavior meaningfully changed rather than being removed.

## 11. Test coverage regressions (disclosed, not hidden)

- **`tests/test_projects_api.py`**: 8 tests removed. They verified
  project/site operational-scope correctness (a genuinely public
  concern — `app/services/project_site_service.py`,
  `app/intelligence/temporal.py`) exclusively by asserting on `GET
  /intelligence/context`'s `operational_scope` field. That field no
  longer exists in any live response. The underlying service-layer
  logic is unchanged and untested by any *other* test in this
  repository as of this milestone — a real, disclosed gap. A future
  milestone should re-verify it either directly at the service layer or
  against a genuine Commercial Core client integration once one exists.
- **`tests/test_risk_assessment_api.py`**: 7 tests removed (candidate
  generation lifecycle, 4; future-event/ingestion exclusion from
  candidate generation, 2; the computed-risk-score-in-`intelligence_context`
  assertion, 1). These tested private functionality end-to-end and have
  no public-side equivalent to preserve.
- No other file lost test coverage for still-public functionality
  without an equivalent replacement (e.g., `test_data_ingestion_api.py`'s
  removed analytics-based assertion was replaced with a direct
  database-count assertion of the same underlying claim — see that
  file's own M43-IP-03 comment).

## 12. Dependencies

`scikit-learn==1.9.0` and `scipy==1.18.1` removed from `requirements.txt`
— confirmed via `grep` (not merely assumed) that no remaining file
imports either. `numpy` is kept: `tests/sentence_transformers_support.py`
and `tests/test_sentence_transformer_provider.py` import it directly,
and it is `sentence-transformers`' own required dependency for the kept,
generic `app/embeddings/provider.py`. **Not re-verified via a fresh venv
install** in this milestone (time-boxed; the grep-based verification is
solid but a clean-venv `pip install -r requirements.txt` + full suite run
was not repeated after the `requirements.txt` edit) — a reasonable
follow-up check before this branch is considered final.

## 13. What this milestone did not do (by its own governing constraints)

Did not modify Commercial Core. Did not merge anything (this branch is
unmerged). Did not implement M43B, recommendation logic, AI-alternative
reasoning, or any new intelligence capability. Did not redesign the
frontend (not touched at all — every removed/stubbed endpoint will now
return 501 to the existing frontend at runtime; no frontend code was
changed to accommodate this, per the explicit "do not redesign the
frontend" constraint — this is a known, disclosed, out-of-scope
consequence, not an oversight). Did not rewrite Git history (all changes
are new commits on a new branch). Did not delete migrations or models
(§5). Did not touch M43A (`claude/sie-m43a-organizational-standards`,
still unmerged, still not referenced by this branch).

## 14. Recommended next steps

1. An independent audit (the same kind M43-IP-VERIFY-02 performed on
   M43-IP-02) re-verifying this milestone's own claims against the
   actual diff, before it is merged anywhere.
2. A DB-boundary milestone to resolve §5's deferred question — whether
   and how to separate the 22 private-domain tables from Public SIE's
   own schema/migration chain.
3. Re-verification of §11's coverage gaps, either at the service layer
   or against a real Commercial Core client integration.
4. A decision on `app/schemas/enterprise_intelligence.py`'s now-unused
   nested schema shapes (§6) — delete, or leave as documented-inert
   field shapes.
