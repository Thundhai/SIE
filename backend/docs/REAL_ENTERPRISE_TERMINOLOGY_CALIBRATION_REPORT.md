# SIE Real Enterprise Terminology & Ontology Calibration Report v0.1

**Corrective-commit note.** An independent audit found this report's own
`event_type`/`event_subtype` section headers ("8 terms" / "10 terms")
did not match the term tables directly beneath them (7 rows and 11 rows,
respectively) — a transcription error in the headers, not in the
underlying data or logic. This is corrected below: **7** `event_type`
terms, **11** `event_subtype` terms, **18** total — unchanged from what
the tables themselves, and the companion `.json`, always actually listed.

**This report describes a calibration *mechanism*, not a completed terminology
review.** It builds and proves a controlled workflow for moving enterprise
terminology through `UNKNOWN → REVIEW CANDIDATE → PROPOSED → HSE REVIEW
→ APPROVED / REJECTED` — it does **not** itself perform HSE review of the
real dataset's own terms. No human HSE reviewer participated in this
session, so **zero** of the real dataset's 18 unresolved terms have been
proposed or approved here. Claiming otherwise would violate this
milestone's own final rule ("do not claim a mapping is HSE-approved
unless an explicit approval operation exists and was actually exercised
by an authorized reviewer"). Every `APPROVED`/`REJECTED` decision
demonstrated in this milestone's own automated test suite uses
**synthetic** terminology and a synthetic test user — never the real
dataset.

**Dataset boundary, unchanged from the prior milestone.** The real
workbook was read once, locally, from a scratch directory outside this
repository, purely to (a) surface its own genuinely unresolved terms
through the existing, unmodified `terminology_review.py`, and (b) create
`REVIEW_CANDIDATE` rows for them in a local, throwaway database (created
and destroyed within this session, never the shared `sie` database, never
committed). No raw record, narrative, or name from the workbook was
copied into source control, a fixture, a test, or this report — only the
terminology terms themselves (already public in the prior milestone's own
committed `REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`) and their
occurrence counts.

---

## 1. What was built

| # | Component | File |
|---|---|---|
| 3 | Persisted, versioned, auditable mapping-decision model | `app/models/terminology_mapping_decision.py` |
| 4 | Lifecycle service (candidate → propose → approve/reject → version) | `app/services/terminology_calibration_service.py` |
| 5-6 | Deterministic, non-guessing proposal mechanism | `terminology_calibration_service.suggest_candidates()` (read-only hint only) |
| 7 | Tenant + source-system scoping | `TerminologyMappingDecision`'s own scope key; verified by test |
| 8 | Versioning, full history retained | `open_new_version()`; verified by test |
| 9 | Explicit, authorized approval | `authorization_service.require(..., GOVERNANCE_MANAGE, ...)` baked into every mutating call |
| 10 | Integration with existing HSE review queue | `hse_review_service.queue_for_review()`/`submit_review()`, reused not duplicated |
| 11 | Data-quality gate unchanged | `CalibratedTerminologyMappingAdapter` — only `APPROVED` unlocks classification |
| 13 | Explicit historical reprocessing | `app/services/terminology_reprocessing_service.py` |
| 14 | Provenance | raw term → decision → canonical event `attributes._terminology_calibration` → feature/intelligence, all traceable |
| 15 | Audit logging | 6 new `AuditAction` entries, one per lifecycle transition + reprocessing |
| 16 | Migration | `migrations/versions/0013_real_enterprise_terminology_ontology_calibration.py` |

**Nothing pre-existing was replaced.** `terminology_mapping.py`'s static
alias table is unchanged and is still consulted *first*, for every
lookup — a calibration decision is only ever consulted as a **fallback**
when the static table itself says `UNKNOWN`/`AMBIGUOUS`.

## 2. Lifecycle implemented

```
UNKNOWN  (no decision row exists — the static table has no alias, exactly as before)
   |
REVIEW_CANDIDATE   (create_review_candidates() — one row per unique term, queued in the
   |                 existing HseExpertReview queue too)
PROPOSED           (propose_mapping() — an explicit, authorized administrator/HSE
   |                 candidate term, or `None` if there is insufficient confidence
   |                 to propose anything — "preferable to guessing", never auto-picked)
   |
   +-- APPROVED    (approve_mapping() — GOVERNANCE_MANAGE required; the only status
   |                 that makes the term eligible for canonical classification)
   +-- REJECTED    (reject_mapping() — GOVERNANCE_MANAGE required; term stays
                     unresolved for this version, permanently)
```

`REVIEW_CANDIDATE` and `PROPOSED` are collectively "PENDING" — this
milestone's own vocabulary (`section 11`) for "not yet decided." Both
`APPROVED` and `REJECTED` are **terminal**: the service layer refuses any
further mutation of a terminal row. Changing an already-decided mapping
opens a **new row** at the next `mapping_version` for the same scope key
(`open_new_version()`) — the old row, and its full approval/rejection
history, is never overwritten.

## 3. Real dataset: terms reviewed (candidates surfaced, none decided)

Re-running the existing, unmodified `terminology_review.py` against the
real workbook (locally, never committed) reproduces the prior milestone's
own finding exactly: **18 unique terms require review**, affecting up to
450 of the dataset's 1,045 records. Every one of the 18 was surfaced as a
`REVIEW_CANDIDATE` — **zero** were proposed, approved, or rejected in
this session.

**Incident Type (`event_type`), 7 terms:**

| Term | Occurrences | Status |
|---|---:|---|
| NearMiss | 6 | REVIEW_CANDIDATE |
| PropertyDamage | 5 | REVIEW_CANDIDATE |
| FireIncident | 4 | REVIEW_CANDIDATE |
| Others | 3 | REVIEW_CANDIDATE |
| SecurityBreach | 2 | REVIEW_CANDIDATE |
| VehicleAccident | 2 | REVIEW_CANDIDATE |
| HazardObservation | 1 | REVIEW_CANDIDATE |

**Observation Category (`event_subtype`, context=`OBSERVATION`), 11 terms:**

| Term | Occurrences | Status |
|---|---:|---|
| Working At Height | 128 | REVIEW_CANDIDATE |
| PPE Compliance | 117 | REVIEW_CANDIDATE |
| Electrical Safety | 47 | REVIEW_CANDIDATE |
| Environmental | 32 | REVIEW_CANDIDATE |
| Lifting Operations | 31 | REVIEW_CANDIDATE |
| Procedure Violation | 29 | REVIEW_CANDIDATE |
| Equipment Safety | 13 | REVIEW_CANDIDATE |
| Others | 13 | REVIEW_CANDIDATE |
| Documentation | 11 | REVIEW_CANDIDATE |
| Fire Safety | 4 | REVIEW_CANDIDATE |
| Emergency Preparedness | 2 | REVIEW_CANDIDATE |

None of these terms produced a static-table candidate list either (every
one resolves `UNKNOWN`, not `AMBIGUOUS`, against the existing alias
table) — `suggest_candidates()` has nothing to hint at for any of them; a
human reviewer proposing a canonical term for these would be supplying
genuinely new domain judgment, not confirming an existing near-match.

**STILL QUARANTINED: 450 / 1,045 records (43.1%)** — unchanged from the
prior milestone, and unchanged by this one. Building the calibration
*mechanism* does not, by itself, resolve a single term; resolving these
450 records requires an authorized HSE reviewer to actually use it.

## 4. Mechanism demonstration (synthetic data only)

The 35 automated tests in `tests/test_terminology_calibration.py`
exercise the full lifecycle end-to-end against **fabricated** terminology
(`"NearMiss"`/`"NEAR_MISS"` used only as a realistic-shaped example term,
never derived from a real record) and a synthetic test organization/user:

- A synthetic `REVIEW_CANDIDATE` was proposed and **approved** by a
  synthetic `ORG_ADMIN` test user, and confirmed to make a *subsequent*
  ingestion of that term resolve automatically — while a previously
  ingested, already-quarantined record of the same term was confirmed to
  **stay quarantined** until an explicit, separate reprocessing call.
- A synthetic mapping was explicitly **rejected**, and confirmed to
  remain unresolved.
- A synthetic mapping was approved, then a **new version** was opened,
  proposed differently, and approved — with the original version's own
  row, decision, and rationale confirmed untouched.
- A synthetic `VIEWER` and a synthetic user with no organization
  membership were both confirmed **unable** to propose, approve, or
  reject.
- Two synthetic organizations, and two synthetic source systems within
  one organization, were confirmed fully isolated from each other's
  decisions.
- Explicit reprocessing was confirmed tenant- and source-scoped, to
  require an `APPROVED` decision, to leave unrelated records untouched,
  and to stamp a fresh `ingestion_time` (preserving point-in-time
  correctness for any query from before the reprocessing run).

## 5. Architecture limitations discovered

1. **A plain re-ingest can never re-trigger reclassification for content
   that has not changed.** `SafetyEventIngestionService`'s idempotency
   check compares a hash of the *raw, originally-received* payload — a
   quarantined record's raw term is identical before and after a mapping
   is approved, so a real re-ingest of the same payload always produces
   `SKIPPED_IDEMPOTENT`, never a reclassification. This is why explicit
   reprocessing (`terminology_reprocessing_service.py`) had to call
   `validate_and_normalize()` and `SafetyEventIngestionService._apply()`
   directly rather than simply re-running `ingest_batch()` — a genuine,
   non-obvious finding from building this milestone, not a design
   preference.
2. **`training_status`/`maintenance_status` calibration has nowhere to
   plug into ingestion.** Those two domains are reviewed by
   `terminology_review.py` for reporting only; no ingestion adapter in
   this codebase (before or after this milestone) ever gates a record's
   canonical classification on them — only `event_type`/`event_subtype`
   are. Reprocessing explicitly refuses those two domains rather than
   silently no-op.
3. **`DataSourceAdapter.validate()`/`normalize()` take no database
   session** (by design — see `app/intelligence/adapters.py`), so
   `CalibratedTerminologyMappingAdapter` must be constructed with a
   precomputed active-mapping index (`build_active_mapping_index()`),
   fetched once per ingestion batch. A caller that forgets to rebuild
   this index after a new approval will keep resolving through the old
   snapshot until it does — an integration responsibility this report
   flags explicitly, not a runtime safeguard this milestone adds (adding
   one would risk a live per-record query inside a Protocol method that
   was deliberately kept DB-free).

## 6. Recommendations for the next milestone

1. **An actual HSE review of the real dataset's 18 candidate terms**,
   performed by an authorized human reviewer using this milestone's own
   `propose_mapping()`/`approve_mapping()`/`reject_mapping()` — this
   report deliberately stops short of that so it never has to claim an
   approval that did not happen.
2. **A minimal API router** (`app/api/v1/terminology_calibration.py`,
   not built this milestone since it was not required) so a real
   reviewer can drive the lifecycle from the product UI rather than a
   script — the service layer's own authorization checks are already
   API-boundary-ready.
3. Once real approvals exist, **explicit, deliberate reprocessing** of
   the real dataset's own 450 quarantined records, scoped and audited
   exactly as this milestone's mechanism already supports.

---

*See the companion `REAL_ENTERPRISE_TERMINOLOGY_CALIBRATION_REPORT.json`
for the same findings in machine-readable form, and
`tests/test_terminology_calibration.py` for the full, reproducible test
suite this report's mechanism claims are verified against.*
