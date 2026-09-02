# SIE Real Enterprise Terminology & Ontology Calibration Report v0.1

**Status: human HSE review complete (Implement Approved HSE Terminology
Decisions v0.1).** All 18 real-dataset terms surfaced by the prior
milestones have now been explicitly decided by an authorized reviewer
through this codebase's own governed lifecycle
(`REVIEW_CANDIDATE → PROPOSED → APPROVED`/`REJECTED`) — **4 proposed,
3 approved, 15 rejected** (see §4 for why the 4th, `PPE Compliance`,
could not be safely approved). No term is left `REVIEW_CANDIDATE` or
`PROPOSED`. Approved decisions were reprocessed against the real
dataset's own quarantined records using the existing, unmodified
`reprocess_quarantined_records()` mechanism; rejected decisions were
left untouched and their records remain quarantined. This report
supersedes the "zero decided" framing of the prior milestone below —
history is kept for audit continuity, not restated as still true.

**Corrective-commit note (prior milestone, unchanged).** An independent
audit found this report's own `event_type`/`event_subtype` section
headers ("8 terms" / "10 terms") did not match the term tables directly
beneath them (7 rows and 11 rows, respectively) — a transcription error
in the headers, not in the underlying data or logic. Corrected then to
**7** `event_type` terms, **11** `event_subtype` terms, **18** total —
those counts are unchanged by this milestone; only their *status* changed
(§3).

**Dataset boundary, unchanged from every prior milestone.** The real
workbook was read locally, from a scratch directory outside this
repository, into a local, throwaway PostgreSQL database (created and
destroyed within this session, never the shared `sie` database, never
committed) — never copied into source control, a fixture, a test, or
this report. Only the terminology terms themselves (already public in
`REAL_ENTERPRISE_DATASET_EVALUATION_REPORT.md`), their occurrence
counts, and the resulting decision/provenance identifiers (UUIDs,
carrying no PII) appear below.

---

## 1. What was built (production code, this milestone)

| Component | File | Change |
|---|---|---|
| Compound `event_type`+`event_subtype` target | `app/intelligence/terminology_calibration_adapter.py` | `ActiveMappingProvenance.target_event_subtype`; `_resolve_event_subtype()` consults it only when the payload has no independent raw subtype value |
| Compound-subtype canonical validation | `app/services/terminology_calibration_service.py` | `_valid_compound_subtype_for()`; `approve_mapping()` validates `provenance["target_event_subtype"]` before approval, same "never invented" guarantee as `_canonical_terms_for()` |
| Compound-subtype reprocessing | `app/services/terminology_reprocessing_service.py` | applies `target_event_subtype` to a reprocessed record only when its own raw subtype value is empty |
| New-version carry-forward | `app/services/terminology_calibration_service.py` | `open_new_version()` now preserves a prior decision's `target_event_subtype` onto the new candidate row instead of silently dropping it |

**No schema migration.** `target_event_subtype` rides entirely on
`TerminologyMappingDecision.provenance`, the existing JSON column
already used for version-supersession bookkeeping — never a new column,
never a second ontology, never a new canonical value (`INCIDENT`,
`NEAR_MISS`, `PROPERTY_DAMAGE`, and `VEHICLE_INCIDENT` all already
existed in `app/intelligence/enums.py`/`terminology_mapping.py` before
this milestone).

**Why a compound target is needed at all.** The real workbook's Incident
sheet has no subtype-bearing column at all — `app/validation/real_dataset_loader.py`'s
own documented mapping decision sets `event_type` from `Incident Type`
and nothing else. Without this mechanism, an `event_type`-only decision
for `NearMiss`/`PropertyDamage`/`VehicleAccident` could only ever
resolve `event_type`, leaving `event_subtype` permanently `None` and
collapsing all three (plus the already-`MAPPED` `Injury` term) into an
indistinguishable `event_type=INCIDENT` — a real loss of the very
distinction the human review was making. The compound mechanism lets one
governed `event_type` decision carry the reviewer's full classification
intent (`event_type` **and** `event_subtype`), reusing only pre-existing
canonical vocabulary, so the record keeps its distinguishing detail
without inventing anything or touching the ingestion format.

## 2. Lifecycle (unchanged since the original milestone)

```
UNKNOWN  (no decision row exists — the static table has no alias)
   |
REVIEW_CANDIDATE   (create_review_candidates())
PROPOSED           (propose_mapping() — explicit, authorized human input)
   |
   +-- APPROVED    (approve_mapping() — GOVERNANCE_MANAGE required)
   +-- REJECTED    (reject_mapping() — GOVERNANCE_MANAGE required)
```

## 3. Real dataset: the 18 terms, now decided

All 18 terms below were surfaced (again, identically — the underlying
data has not changed) by the existing, unmodified `terminology_review.py`,
then carried through `propose_mapping()`/`approve_mapping()`/`reject_mapping()`
by an authorized reviewer in a local, throwaway PostgreSQL database. Each
row's `decision_id` is the exact `TerminologyMappingDecision.id` a
reprocessed record's own `attributes["_terminology_calibration"]` traces
back to (see §5).

**Incident Type (`event_type`), 7 terms — 3 APPROVED, 4 REJECTED:**

| Term | Occurrences | Decision | Canonical `event_type` | Canonical `event_subtype` |
|---|---:|---|---|---|
| NearMiss | 6 | **APPROVED** | `INCIDENT` | `NEAR_MISS` *(compound target)* |
| PropertyDamage | 5 | **APPROVED** | `INCIDENT` | `PROPERTY_DAMAGE` *(compound target)* |
| VehicleAccident | 2 | **APPROVED** | `INCIDENT` | `VEHICLE_INCIDENT` *(compound target)* |
| FireIncident | 4 | REJECTED | — | — |
| Others | 3 | REJECTED | — | — |
| SecurityBreach | 2 | REJECTED | — | — |
| HazardObservation | 1 | REJECTED | — | — |

**Observation Category (`event_subtype`, context=`OBSERVATION`), 11
terms — 0 APPROVED, 11 REJECTED:**

| Term | Occurrences | Decision |
|---|---:|---|
| Working At Height | 128 | REJECTED |
| PPE Compliance | 117 | REJECTED — ontology limitation, see §4 |
| Electrical Safety | 47 | REJECTED |
| Environmental | 32 | REJECTED |
| Lifting Operations | 31 | REJECTED |
| Procedure Violation | 29 | REJECTED |
| Equipment Safety | 13 | REJECTED |
| Others | 13 | REJECTED |
| Documentation | 11 | REJECTED |
| Fire Safety | 4 | REJECTED |
| Emergency Preparedness | 2 | REJECTED |

**Rejection rationale (all 15).** None of these 15 terms has a
genuinely pre-existing, semantically exact SIE canonical value.
`FireIncident`/`Others`/`SecurityBreach`/`HazardObservation` and the 10
remaining Observation terms would each require inventing a new canonical
value (`FIRE_INCIDENT`, `SECURITY_BREACH`, `ELECTRICAL_SAFETY`,
`ENVIRONMENTAL`, `LIFTING_OPERATIONS`, `PROCEDURE_VIOLATION`,
`EQUIPMENT_SAFETY`, `FIRE_SAFETY`, `EMERGENCY_PREPAREDNESS`,
`HAZARD_OBSERVATION`) — explicitly forbidden by this milestone.
`Working At Height` and `Lifting Operations` are especially notable:
SIE *does* already have `WORK_AT_HEIGHT`/`LIFTING_OPERATION` canonical
values, but they belong to the `PERMIT` domain's own subtype vocabulary
(a permit-to-work classification), not `OBSERVATION`'s — reusing them
here would silently substitute a different domain for an approximate
match, which this milestone explicitly forbids. Both `Others` terms are
catch-all buckets with no single exact classification by construction.
`PPE Compliance` is the one case investigated in depth — see §4.

## 4. `PPE Compliance` — ontology limitation (not approved)

**Investigated, not force-fit.** SIE's existing, curated `OBSERVATION`
canonical subtype vocabulary (`app/intelligence/terminology_mapping.py::_SUBTYPE_ALIASES["OBSERVATION"]`)
is exactly: `UNSAFE_ACT`, `UNSAFE_CONDITION`, `POSITIVE_OBSERVATION`,
`HOUSEKEEPING_DEFICIENCY`, `PPE_ISSUE`. The nearest candidate,
`PPE_ISSUE` (raw aliases `"ppe issue"`/`"ppe non compliance"`), denotes
a specific **negative** finding — an issue or instance of
non-compliance. The real dataset's own `PPE Compliance` term is instead
the sheet's own **Observation Category** label (117 occurrences) — a
broad topic covering PPE-related observations generally, not
exclusively non-compliant ones. Approving `PPE_ISSUE` for every one of
those 117 records would silently assume each was a negative finding,
which the underlying category name does not establish — exactly the
"approximate category" substitution this milestone's own instructions
forbid ("do not silently substitute a different domain or approximate
category").

**Conclusion: no genuinely exact canonical Observation value exists for
`PPE Compliance` today.** Per this milestone's own explicit instruction,
the term is **not** approved. It remains `REJECTED`/quarantined — its
117 underlying records are untouched and still `QUARANTINED`, with
their original `PPE Compliance` source term fully preserved. This is a
genuine, reportable ontology gap, not a resolved term: SIE's
`OBSERVATION` subtype vocabulary would need a dedicated
"PPE compliance topic/category" value distinct from `PPE_ISSUE` for a
future, deliberate ontology-review milestone to add — out of this
milestone's explicit scope ("Do not expand the ontology").

## 5. Reprocessing outcome (real dataset, approved decisions only)

Only the 3 approved decisions (`NearMiss`, `PropertyDamage`,
`VehicleAccident`) were reprocessed, via the existing, unmodified
`reprocess_quarantined_records()`, called once per approved
`decision_id` — never a bulk reprocessing of all 450 quarantined
records, and never any of the 15 rejected terms.

| Metric | Count |
|---|---:|
| Total real records (Incident + Observation) | 1,045 |
| Quarantined before this milestone's decisions | 450 |
| Terminology decisions persisted | 18 |
| — Approved | 3 |
| — Rejected | 15 |
| Records reprocessed (left quarantine) | **13** (6 NearMiss + 5 PropertyDamage + 2 VehicleAccident) |
| Records remaining quarantined | **437** |
| Second reprocessing pass (idempotency check) | 0 additional records updated |

**Rejected terms verified still quarantined**, source terms unchanged:
`FireIncident` (4), `Others`/Incident (3), `SecurityBreach` (2),
`HazardObservation` (1), `Working At Height` (128), `Electrical Safety`
(47), `Environmental` (32), `Lifting Operations` (31), `Procedure
Violation` (29), `Equipment Safety` (13), `Others`/Observation (13),
`Documentation` (11), `Fire Safety` (4), `Emergency Preparedness` (2),
`PPE Compliance` (117) — summing to exactly 437, matching the
"remaining quarantined" count above with no unaccounted-for records.

**Exact provenance, spot-verified.** A reprocessed `NearMiss` record's
own `attributes["_terminology_calibration"]` carries, under both
`"event_type"` and `"event_subtype"` keys, the identical exact
`decision_id`/`mapping_version` of the one `APPROVED` decision that
produced it (the `event_subtype` entry additionally flagged
`"derived_from_compound_event_type_decision": true`, since one decision
drove both fields) — never a bare `"calibrated": true` marker. A
rejected `FireIncident` record was confirmed to carry **no**
`_terminology_calibration` key at all — it was never touched.

**Idempotency confirmed.** Re-running `reprocess_quarantined_records()`
for all 3 approved decisions a second time updated 0 records (nothing
left in `QUARANTINED` state for those scope keys to re-examine) — safe
to run more than once, no duplicate events, no conflicting provenance.

## 6. Mechanism regression coverage (synthetic data only)

Every new automated test in `tests/test_terminology_calibration.py`
uses **fabricated** terminology and a synthetic test organization/user —
never the real dataset — per this milestone's own testing requirements.
See the test file itself for the full battery (decision lifecycle,
reprocessing, rejection safety, provenance, tenant/source isolation,
ontology safety).

## 7. Architecture limitations discovered (cumulative, including this milestone)

1. **A plain re-ingest can never re-trigger reclassification for content
   that has not changed** (unchanged from the prior milestone —
   idempotency compares the raw payload hash, not its resolution).
2. **`training_status`/`maintenance_status` calibration has nowhere to
   plug into ingestion** (unchanged).
3. **`DataSourceAdapter.validate()`/`normalize()` take no database
   session**, so the adapter needs a precomputed active-mapping index
   rebuilt once per batch (unchanged).
4. **The real workbook's Incident sheet has no subtype-bearing column**
   (new finding, this milestone) — see §1's "why a compound target is
   needed" for the full explanation and the mechanism built to address
   it without modifying the ingestion format.
5. **SIE's `OBSERVATION` canonical subtype vocabulary has no dedicated
   "PPE compliance topic" value** distinct from the narrower `PPE_ISSUE`
   (new finding, this milestone) — see §4.

## 8. Recommendations for the next milestone

1. **A deliberate ontology-review milestone** (out of this milestone's
   scope) to decide whether SIE's `OBSERVATION` subtype vocabulary
   should gain a dedicated value distinct from `PPE_ISSUE` for the
   broader "PPE compliance" observation category — and, separately,
   whether any of the 14 other rejected terms warrant a genuinely new
   canonical value rather than remaining permanently unresolved.
2. **A minimal API router** (`app/api/v1/terminology_calibration.py`,
   still not built) so a real reviewer can drive the lifecycle from the
   product UI rather than a script.
3. The 437 still-quarantined records for the 15 rejected terms remain
   quarantined by design — no further action is expected on them unless
   a future ontology-review milestone changes the underlying vocabulary.

---

*See the companion `REAL_ENTERPRISE_TERMINOLOGY_CALIBRATION_REPORT.json`
for the same findings in machine-readable form, and
`tests/test_terminology_calibration.py` for the full, reproducible test
suite this report's mechanism claims are verified against.*
