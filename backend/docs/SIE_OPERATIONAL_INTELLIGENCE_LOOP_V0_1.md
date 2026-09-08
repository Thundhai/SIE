# SIE Operational Intelligence Loop — Architecture v0.1

**SIE Milestone M30 — Operational Intelligence Loop Foundation v0.1.**
Architecture-first, no production implementation. This document is the
result of inspecting the actual repository at commit
`81639825875f22c10b3d9342029a99fac8f467a2` — not milestone completion
reports, the code itself — and reasoning about how the pieces that
already exist should compose into one coherent system. It changes
nothing: no migration, no model, no endpoint, no route, no service, no
AI integration. Its only output is this document.

**Location note.** This document lives in `backend/docs/`, alongside
every other architecture document this codebase already produces
(`RISK_ASSESSMENT_FOUNDATION_V0_1.md`, `SIE_ENTERPRISE_ONTOLOGY_V0_1.md`,
`ENTERPRISE_INTELLIGENCE_RISK_ANALYTICS.md`) — the established
convention for a cross-cutting backend architecture document, even
though this one also reasons about the frontend and about external
integration. `docs/FRONTEND_ARCHITECTURE.md` remains the place for
*frontend implementation* history; this document is the place for the
*system-wide* "how does this all become one thing" question, which is
backend-rooted (the loop's stages are almost entirely backend
capabilities) and which future backend milestones will need to find
without digging through frontend history.

---

## 1. Executive Summary

SIE already contains most of the raw material for "the brain for the
field" — a deterministic, evidence-grounded, temporally-correct,
tenant-isolated intelligence platform sitting between raw field data and
human HSE decision-makers. What it does not yet have is a single,
named, cross-cutting *loop* that ties the pieces together, and a small
number of missing joints that currently make the loop's later half
(Intervention → Outcome → Learning) structurally impossible to close.

Every deterministic capability this document surveys is real, tested,
and — with one large exception — already wired end to end: raw
event/document ingestion with provenance and idempotency; a governed
ontology and terminology-calibration layer that keeps vocabulary
canonical without ever guessing; point-in-time-correct statistical
intelligence (indicators, trend, concentration, recurrence, anomaly,
association, a bounded deterministic risk score); a narrow, deliberately
conservative signal → candidate-finding pipeline; a fully governed human
risk-assessment workflow with M29A's single-authoritative-mutation-path
discipline for control effectiveness; an evidence-grounded RAG layer
with a hard deterministic gate in front of the one LLM call in the whole
system; and a completely separate, fully governed predictive-model
lifecycle (train → validate → approve → deploy, human-approved at every
promotion) that is, today, **built but has no real consumer** — the
single largest finding of this investigation.

The system's own code is unusually explicit about what it refuses to
do: no fuzzy/LLM guessing in terminology or risk-area resolution, no
automatic historical reprocessing, no inferring control effectiveness
or finding closure from an action's completion status, no autonomous
action of any kind toward the outside world. These are not gaps to
fill — they are the architecture's own load-bearing walls, and this
document's central recommendation is to keep building on top of them
rather than around them.

The loop this document defines — **OBSERVE → CAPTURE → UNDERSTAND →
CONTEXTUALIZE → REMEMBER → REASON → SIGNAL → EXPLAIN → DECIDE →
INTERVENE → VERIFY → OUTCOME → LEARN** — is not a new system to build.
It is a name for a sequence that already exists in fragments (§4), with
one honest, load-bearing gap: nothing today closes the loop back on
itself. An intervention happens, and SIE currently has no way to ask,
responsibly, "did it work?" Filling that gap — Field State (§6),
Intervention Intelligence (§10-11) — is the architectural spine of every
milestone this document proposes (§17).

## 2. Product Thesis

> "SIE is the brain for the field."

The repository's own architecture already agrees with this framing more
than it disagrees. SIE is not, anywhere in the current codebase, trying
to *be* an incident-management system, a document-management system, an
ERP, a CMMS, or an autonomous HSE manager. `docs/INTEGRATION_GUIDE.md`
states the boundary as plainly as this milestone's own instructions do:

> "SIE is an independent, multi-tenant safety intelligence platform...
> Regardless of caller, SIE never: automatically suspends or disciplines
> a worker, blocks a permit, shuts down equipment, contacts a regulator,
> closes an incident, modifies your organization's own records, retrains
> a predictive model, or takes any other autonomous action. Every
> response is advisory information for a human decision-maker."

That sentence, written for third-party integrators, is also the correct
internal description of SIE's own first-party frontend. The Risk
Assessment and Actions workspaces built in earlier milestones do not
violate this — closing a finding, approving a control's effectiveness,
and approving/deploying a predictive model are all explicit,
attributed, human-invoked actions gated behind elevated permissions
(`risk_assessment:approve`, a named `ModelApproval.reviewer_user_id`)
— never something SIE decided on its own.

```
FIELD / ENTERPRISE SYSTEMS
        |
      SIE   <-- understanding + memory + intelligence, never the record of truth
        |
HUMAN DECISION
        |
INTERVENTION
        |
FIELD OUTCOME
        |
      SIE   <-- learns, does not act
```

Where the thesis is currently under-realized is not in any
architectural violation — it's in incompleteness. SIE understands a
great deal about the past and the present (Events, Intelligence, Risk
Assessments). It has almost no architecture yet for the *current
moment* as a single answerable question ("what is the state of this
site right now" — §6, Field State), and it has no architecture at all
for closing the loop from intervention back to verified outcome (§10).
A brain that observes and explains, but never learns whether its own
past signals led anywhere, is not yet the brain for the field — it is a
very good nervous system for it. §17 proposes the milestones that close
this gap without asking SIE to become anything it has correctly refused
to become so far.

## 3. Current Architecture Assessment

This section is deliberately not a directory listing. It groups what
was found into the shape the rest of this document needs, and names
every place the investigation found two mechanisms doing adjacent jobs
(never a hidden conflict — this codebase documents its own seams
carefully — but real seams a reader of the whole system needs to know
about).

### 3.1 Two ingestion systems, correctly kept apart

`app/ingestion/` (+ `app/ingestion/adapters/`) is the **document/knowledge**
ingestion engine — unstructured files (PDF/DOCX/XLSX/...) flowing
through detection → validation → hashing → extraction → chunking,
eventually producing `KnowledgeChunk` rows for RAG. This has nothing to
do with safety events.

**Structured safety-event ingestion** is a second, separate pipeline,
reachable through two API surfaces that both funnel into the same
`SafetyEventIngestionService._upsert()`:
- the legacy `/intelligence/events` / `/events/batch` routes, and
- the newer, tracked `POST /api/v1/data/ingestion` (`EnterpriseIngestionService`),
  which wraps the identical call with `EnterpriseIngestionBatch`/
  `EnterpriseIngestionRecord` tracking.

Both produce identical, idempotent, versioned `SafetyEvent` rows. Only
the newer path produces a queryable batch/record audit trail — a real,
documented asymmetry (not a defect; the legacy path was deliberately
left untouched to avoid regression risk) worth knowing before assuming
"every ingested event has a batch to inspect."

### 3.2 The canonical event, and its one real limitation

`SafetyEvent` is a single wide table (deliberately not split per HSE
domain), carrying operational context, a `data_quality_status`
(VALID/PARTIAL/INVALID/QUARANTINED), and a rich provenance surface
(`source_system`, `source_record_id`, `source_value` — the untouched
original payload — `source_content_hash`, `normalization_version`,
`schema_version`, `ingestion_batch_id`, `ingestion_source_id`,
`correlation_id`). Deduplication/versioning is content-hash-based, with
optional strict-ordering when a source supplies a numeric
`source_record_version`.

**The one structural gap**: an update to an existing `SafetyEvent`
mutates the row in place. There is no row-level version chain, no
`superseded_by`, no "what did this look like before." The prior state
is only coarsely recoverable from `AuditLog` (counts/ids, never a
diff) — see §16, Gap G1.

### 3.3 Terminology and ontology — three governance layers, each doing a different job

```
raw source term
   |
STATIC ALIAS TABLE   (exact match after normalization; no fuzzy/LLM matching, ever)
   |  (UNKNOWN / AMBIGUOUS)
TERMINOLOGY MAPPING DECISION   (org-scoped, human-approved, versioned, never mutated in place)
   |  (optionally gated by)
ONTOLOGY CONCEPT   (GLOBAL or ORGANIZATION, PROPOSED -> APPROVED/REJECTED -> DEPRECATED)
   |
canonical SafetyEvent.event_type / event_subtype
```

This is a genuinely coherent, layered governance design: the ontology
is the platform's canonical vocabulary (governed by `GOVERNANCE_MANAGE`,
GLOBAL entries `PLATFORM_ADMIN`-only), terminology decisions are how an
individual organization's messy source vocabulary maps onto it, and
neither layer ever infers a mapping — every non-obvious case becomes a
human decision, persisted, versioned, and re-approvable without
mutating history. Reprocessing historical events against a newly
approved decision is a deliberate, explicit, human-invoked operation
only — approving a decision never silently rewrites the past.

One deliberately unfinished piece: the ontology's newer
`observation_topic` layer (hazard/subject-matter categories orthogonal
to event type, e.g. `WORKING_AT_HEIGHT`) is governed vocabulary with
**no storage location on `SafetyEvent` yet** — explicitly documented as
a known gap, not an oversight (see §16, Gap G2). This matters directly
for Field State (§6) and Contextual Reasoning (§15): "this site has
repeated *lifting* observations" is not yet a queryable fact anywhere in
the schema, because lifting-as-a-hazard-topic has nowhere to live.

### 3.4 Temporal correctness is a single choke point, not a convention

`app/intelligence/temporal.py::events_as_of()` is the one function every
statistical/predictive feature in the codebase uses to fetch events —
filtering on **both** `event_time <= as_of` (did it happen by then) and
`ingestion_time <= as_of` (was it *knowable* by then, catching
backdated/late-reported records). This single-choke-point design, plus
a dedicated regression-test suite (`test_temporal_leakage.py`,
`test_predictive_temporal_leakage.py`), is the strongest piece of
engineering discipline in the whole system and the reason §15 can make
a confident recommendation rather than a wish.

### 3.5 Deterministic statistical intelligence — one orchestrator, seven independent lenses

`enterprise_intelligence_service.py::compute_enterprise_intelligence()`
computes, from one tenant-scoped, as-of-filtered event set: indicators
(period-over-period counts), a two-point trend classification,
concentration (share-of-total across four dimensions), recurrence
(count-and-bucket pattern detection), a bounded 0-100 deterministic
"enterprise-risk-v1" score (five weighted, independently-gated
components), a z-score multi-metric anomaly scan, and Pearson
correlation between a closed set of seven metrics ("association" —
never causation, by construction: the vocabulary has no causal
sentence to reach for). Every explanation is a template with numbers
substituted in and an `evidence_reference` pointing at the exact
computed object — never LLM-generated. Nothing here is persisted or
cached; every request recomputes live (an accepted, documented v0.1
tradeoff — see §16, Gap G7).

### 3.6 Signal → candidate finding — the loop's clearest existing example

`app/risk_assessment/candidate_generation.py` is the one place in the
codebase that already implements a full slice of the loop this
document is naming:

```
ANOMALY / PATTERN  (already computed, §3.5)
   -> CandidateFindingDraft   (IDENTIFIED, likelihood = consequence = NULL)
      -> HUMAN REVIEW          (a governed candidate_status transition)
         -> RISK ASSESSMENT     (human supplies likelihood + consequence)
```

Only `ANOMALOUS` anomalies and `RECURRING`/`HIGH_RECURRENCE` patterns
draft a candidate today — a deliberately narrow v0.1 source list (every
other signal type is still fully exposed via `intelligence_context`,
just not yet auto-drafted). The metric→risk-area mapping is a
hand-maintained deterministic table resolving to a governed
`OntologyConcept`, explicitly never "fuzzy/LLM guessing" — a metric with
no unambiguous mapping is simply skipped, never assigned a guessed
category. This module is the best evidence in the repository that the
loop this document formalizes is not a hypothetical — it is already the
house style for exactly one join.

### 3.7 Risk Assessment: the most complete governed workflow in the system

DRAFT → IN_REVIEW → APPROVED → SUPERSEDED/ARCHIVED, with an
`ASSESSMENT_EDITABLE_STATUSES` gate that makes "historical integrity...
free, not engineered" — once approved, simply reading the row *is* the
historical snapshot; no copy-on-approve mechanism exists or is needed.
Findings carry a governed `risk_area_concept_id` (never a free string),
controls have a single authoritative effectiveness-mutation path
(M29A — closing a legacy path that could previously set effectiveness
directly), and two explicit, load-bearing principles recur at every
level of this domain:

- *"Control existence is not proof of effectiveness"* — nothing infers
  `EFFECTIVE` from a linked action's `COMPLETED` status.
- *"A completed action never automatically closes a finding"* — closure
  is a dedicated, `risk_assessment:approve`-gated endpoint requiring an
  explicit `closure_reason`.

Both are the exact discipline §10 (Intervention → Outcome → Learning)
needs to build on, already proven correct one level down (control) and
one level up (finding).

### 3.8 Actions: real per-resource history, no effectiveness verification

`SafetyAction` has an explicit terminal lifecycle (COMPLETED/CANCELLED,
no reopening) and its own append-only `SafetyActionHistory` — a
resource-scoped trail distinct from the platform-wide `AuditLog`,
exactly mirrored in the Risk Assessment domain's own
`RiskAssessmentHistory` (both explicitly justified in code as "two
sinks, two questions"). Explicitly documented: `COMPLETED` means "an
authorized actor marked this done," never "SIE verified the hazard is
resolved." There is no general Action-level effectiveness-verification
mechanism — only a *Risk-Assessment-linked control* gets an
effectiveness assessment, and only through the M29A dedicated path.

### 3.9 Evidence-grounded RAG — the one LLM call in the system, behind a deterministic gate

```
query -> RetrievalService.search()  (tenant + model-identity filtered pgvector search)
      -> EvidenceSelectionService.select()  (dedupe / quality / relevance / cap)
      -> evaluate_sufficiency()  --[insufficient]--> ABSTAIN, LLM never called
      -> detect_conflicts()      --[conflict]-----> SOURCE_CONFLICT, LLM never called
      -> [privacy gate]          --[blocked]------> PRIVACY_BLOCKED, LLM never called
      -> build_grounded_context()
      -> LLMProvider.generate()
      -> validate_and_sanitize_citations()  --[no valid citation]--> UNSUPPORTED_CLAIM_REJECTED
      -> RAGResponse (every surfaced [E#] resolves to a real chunk/document/source)
```

`app/llm/` is loosely coupled (a `Protocol`, `FakeLLMProvider` the
tested default, both fail closed under `APP_ENV=production` if
misconfigured) and used for exactly one thing: generating the prose of
a RAG answer, never classification, never feature extraction, never
anything in the deterministic pipeline. Embeddings/retrieval/RAG
operate **only** over the knowledge corpus — `SafetyEvent` data is never
embedded, never touched by the LLM. This is the cleanest possible
starting boundary for §12's AI participation model.

### 3.10 Predictions: fully governed, architecturally complete, structurally dormant

`app/predictions/` implements a complete, human-gated lifecycle —
`TRAINED → VALIDATED → APPROVED → DEPLOYED`, with a named-reviewer
`ModelApproval` row at every promotion, drift detection that only ever
*flags for human review* (`ModelReviewFlag`, never auto-retrains or
auto-redeploys), and a live-serving path (`predict_as_of()`) that
requires `require_deployed=True` and treats abstention as a first-class
persisted outcome, never an exception. This is real, tested, and
correctly separated from the other two "risk" concepts in the system
(§9). **It has no real consumer today** — the frontend's Intelligence
workspace doesn't even declare a `predictive_context` field in its
TypeScript types, though the backend response includes one. This is the
single largest concrete finding of this investigation (§16, Gap G0)
and the reason §17's milestone sequence treats "connect a governed
capability that already exists" as higher priority than "build
something new."

### 3.11 Authorization, audit, and API core — consistent, with two named seams

Tenant isolation is genuinely defense-in-depth everywhere it was
checked: a schema-level `organization_id` (`OrganizationScopedMixin`), a
query-level requirement (`TenantScopedRepository` has no "get by id
alone" method), and an authorization-level check
(`RequestContext`/`authorize_context()`, pinning a machine credential's
organization and never trusting a request-supplied override). Two
honest seams:
- **Two coexisting auth-dependency idioms** — most domain routers adopt
  `RequestContext` (human + machine, uniform); a smaller set of
  human-only administrative routers (model governance, API client
  management) still use an older `deps_auth`-only path. Documented as
  deliberate, not accidental, but a newcomer has to learn both.
- **`AuditLog` is write-only** — no route anywhere reads it back. A rich
  ~50-action-type audit trail exists with no query surface (§16, Gap
  G3), and `caller_kind` capture is a per-call-site convention in the
  metadata JSON, not a structural column every writer guarantees (§16,
  Gap G4).

### 3.12 The frontend already knows how to answer "what needs my attention"

`HomePage.tsx` composes three independent backend surfaces —
`GET /intelligence/enterprise` (risk/changing/attention), `GET /events`
(recent activity), `GET /intelligence/analytics/summary` (indicators/
signals) — each with its own loading/error state so one surface's
failure never blanks the page. This is, today, the closest thing SIE
has to a Field State view (§6): assembled client-side, from three
separate calls, with no persisted "current state of this site" object
behind it. The Intelligence and Risk Assessment screens deliberately
have **no fixture fallback** — a missing organization context is always
an honest empty state, never fabricated activity — a principle every
future screen this document's UX section (§20) touches should inherit
unchanged.

---

## 4. Operational Intelligence Loop

The spec's own proposed sequence (OBSERVE → CAPTURE → UNDERSTAND →
CONTEXTUALIZE → REMEMBER → REASON → IDENTIFY SIGNALS → EXPLAIN → HUMAN
DECISION → INTERVENTION → VERIFICATION → OUTCOME → LEARN) survives
inspection almost unchanged. Two real corrections, both confirmed by
the repository:

1. **CAPTURE happens before UNDERSTAND, but UNDERSTAND is itself two
   distinct steps the codebase already keeps separate**: raw
   normalization/provenance (ingestion — deterministic, no
   interpretation) versus canonicalization against governed vocabulary
   (terminology mapping/ontology — deterministic, human-governed,
   *interpretive* in the narrow sense of "which canonical concept does
   this map to"). Collapsing these into one "Understand" stage would
   hide the single most carefully engineered governance boundary in the
   system (§3.3). This document keeps them as 3a/3b below.
2. **REMEMBER is not a step between CONTEXTUALIZE and REASON — it is a
   standing capability every later stage reads from and writes to**
   (organizational memory, §8), not a queue position. It is listed
   below in loop order because every stage *touches* it, but
   architecturally it is a side capability, not a pipeline stage.

| # | Stage | Purpose | Inputs | Existing capability | Missing capability | Authoritative source | Determinism | Provenance | Temporal/as-of | Integration boundary | Likely milestone |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **OBSERVE** | Something happens in the field | Physical/operational reality | None (SIE has no sensors) | — (by design, out of scope) | External system | n/a | n/a | n/a | Field / external system → SIE | n/a |
| 2 | **CAPTURE** | Get the observation into SIE, unmodified except normalization | Raw payload (event or document) | `app/ingestion/`, `app/intelligence/ingestion_service.py`, `app/intelligence/enterprise_ingestion.py` (§3.1) | Real-time/streaming capture (today: request/response only, no queue/webhook consumer) | The submitting system (human form, API client, file upload) | Deterministic | `source_system`/`source_record_id`/`source_value`/`source_content_hash`/`ingestion_batch_id` | `ingestion_time` stamped; strict content-hash idempotency | Ingress API surface (`/data/ingestion`, `/intelligence/events`, `/ingestion`) | M31 |
| 3a | **UNDERSTAND (normalize)** | Turn a raw payload into a canonical `SafetyEvent`/`KnowledgeChunk` shape | Captured payload | Adapters, `normalization_version`, chunking pipeline | — | The ingestion pipeline itself | Deterministic | `normalization_version`/`schema_version` | n/a (structural, not point-in-time) | Internal | — |
| 3b | **UNDERSTAND (canonicalize)** | Map source vocabulary onto governed meaning | Normalized event/term | Static alias table → `TerminologyMappingDecision` → `OntologyConcept` (§3.3) | `observation_topic` layer has no `SafetyEvent` storage location yet (Gap G2) | Terminology calibration service + ontology governance | Deterministic, human-governed for the non-obvious cases | Mapping decision id + version recorded on the event | Reprocessing is explicit/human, never silent | Internal, governance-gated | M31 (topic wiring) |
| 4 | **CONTEXTUALIZE** | Relate this observation to where/what/who it concerns | Canonical event + org/site/activity | `organization_id`/`site_id` scoping, `attributes` payload | No cross-entity resolution (contractor/equipment/permit as first-class linkable entities) — see Gap G5 | Tenancy layer (§3.11) | Deterministic | Inherited from the event | n/a | Internal | M32 |
| 5 | **REMEMBER** | Make this observation part of the organization's durable safety history | Contextualized event | `SafetyEvent` table itself, `RiskAssessmentHistory`, `SafetyActionHistory`, `AuditLog`, `KnowledgeDocument` corpus (§8) | No row-level version history on `SafetyEvent` (Gap G1); `AuditLog` is write-only (Gap G3) | The persistence layer, broadly | Deterministic | Provenance fields per §3.2 | `ingestion_time` is the temporal anchor for "was this knowable" | Internal | M31 (event history), later (audit read API) |
| 6 | **REASON** | Compute what the accumulated history means, as of a moment | Windowed event set | `enterprise_intelligence_service.py`'s seven lenses (§3.5), risk matrix (human, in Risk Assessment) | No persisted/cached result (recomputed every read — Gap G7) | `events_as_of()` (§3.4) | Deterministic/statistical (never AI) | `calculation_versions` in `provenance` | `events_as_of()` — the loop's one hard temporal-correctness guarantee | Internal | — |
| 7 | **IDENTIFY SIGNALS** | Turn a statistical result into something worth a human's attention | Reasoned intelligence | Anomaly/recurrence/candidate-finding generation (§3.6) | Only 2 of 6+ signal types (anomaly, pattern) currently draft a candidate finding (deliberate v0.1 scope, not a defect) | `candidate_generation.py` | Deterministic mapping table, never fuzzy/LLM | `originating_calculation_version`, `evidence_reference` | As-of-consistent with the Reason stage | Internal | M31 (widen signal-source coverage) |
| 8 | **EXPLAIN** | State *why* a signal exists, evidence-first | Signal | `explanations.py` (template + `evidence_reference`), RAG `Citation` chain (§3.9) for knowledge-grounded questions | No unified "explain any intelligence object" surface — statistical explanations and RAG citations are two different mechanisms today (Gap G6) | Explanation generators (deterministic) + RAG (AI-assisted, evidence-gated) | Deterministic for statistical explanations; AI-assisted (gated) for RAG answers | `evidence_reference` / `Citation` chain | Same as-of as the signal it explains | Internal + optional AI boundary (§12) | M34 |
| 9 | **HUMAN DECISION** | A person decides whether/how to respond | Signal + explanation + evidence | Candidate-finding human review, risk rating entry, action creation-from-finding, control-effectiveness assessment — all in the Risk Assessment/Actions workspaces | Field State (§6) does not yet exist to give this decision full situational context in one view | The human, always | Human-governed, always | Attributed to `user_id`, recorded in domain history | The decision is timestamped; it acts on the as-of state it was shown | Frontend (Risk Assessment/Actions) | M32 |
| 10 | **INTERVENE** | Carry out the decided response | Decision | `SafetyAction` creation/assignment (M17/M18/M27) | No verification-of-implementation concept distinct from "status = COMPLETED" (§3.8, Gap G8) | Actions domain | Human-governed (execution), deterministic (state machine) | `SafetyActionHistory` | Actions reflect *current*, not historical, state by design (M27's own documented exception) | Frontend (Actions) + external systems (permit/work-order systems, out of SIE's ownership) | M33 |
| 11 | **VERIFY** | Confirm the intervention actually happened as claimed, and that any control is really effective | Completed action / assessed control | Control-effectiveness assessment (M29A) exists for *controls* only | No general action-implementation verification; no automatic link from "action completed" to "did the underlying condition change" (Gap G8) | Human, dedicated endpoint (control) — nothing analogous for actions generally | Human-governed | `assessed_by_user_id`/`effectiveness_rationale` (control only) | Assessed_at is its own timestamp, deliberately distinct from the action's own timestamps | Frontend | M33 |
| 12 | **OUTCOME** | Did the field state actually improve? | Post-intervention events over time | Nothing today computes this. `ActionResponseSummary` counts actions, never re-evaluates the originating signal | Recurrence-after-intervention comparison; before/after Field State comparison | Would need to be `events_as_of()`-based (Gap G9, the loop's largest gap) | Statistical, never causal (correlation-only, matching §3.5's existing discipline) | Would need explicit before/after evidence chain | This is the stage most exposed to future-data leakage if built carelessly — must reuse `events_as_of()` verbatim | Internal | M33 |
| 13 | **LEARN** | Feed verified outcomes back into organizational memory and, eventually, model training | Outcome result | `outcome_tracking.py` exists for *predictive models only* (reuses the same label function as training — §3.10) | No equivalent "did this intervention pattern work" feedback into organizational memory generally (Gap G9) | Prediction outcome tracking (models only today) | Statistical | Reuses training's own label logic (models); would need an analogous mechanism for interventions | Never evaluated before the outcome's own horizon matures | Internal | M33 |
| → | back to **OBSERVE** | The field continues; the next event is now informed by this cycle only through what a human chose to act on — SIE itself never auto-adjusts | | | | | | | | | |

### A. SIE ecosystem boundary

```
        +-----------------------------------------------------------+
        |                    FIELD / ENTERPRISE                     |
        |  workers, equipment, permits, contractors, environment,   |
        |  incident systems, inspection systems, HR/training, ERP,  |
        |  CMMS, IoT, other HSE platforms                           |
        +---------------------------+---------------------------+---+
                       | push (events, docs)   ^ pull (intelligence, RAG)
                       v                        |
        +-----------------------------------------------------------+
        |                            SIE                            |
        |  ingestion -> understanding -> memory -> reasoning ->      |
        |  signals -> evidence -> explanation                        |
        |  (never: auto-suspend, auto-close, auto-approve,           |
        |   auto-contact-regulator, autonomous action of any kind)   |
        +---------------------------+---------------------------+---+
                       |                        ^
                       v                        |
        +-----------------------------------------------------------+
        |                      HUMAN DECISION-MAKER                 |
        |         (in SIE's own frontend, or a third-party UI)      |
        +---------------------------+---------------------------+---+
                       |
                       v
        +-----------------------------------------------------------+
        |         INTERVENTION  (in the field, or in an external     |
        |         permit/CMMS/HR system SIE does not own)             |
        +-----------------------------------------------------------+
```

### B. Operational Intelligence Loop

```
 OBSERVE -> CAPTURE -> UNDERSTAND(normalize) -> UNDERSTAND(canonicalize)
    ^                                                    |
    |                                                    v
  LEARN                                          CONTEXTUALIZE
    ^                                                    |
    |                                                    v
  OUTCOME                                           REMEMBER  <-------+
    ^                                                    |            |
    |                                                    v            | (every stage
  VERIFY                                              REASON          |  reads/writes
    ^                                                    |            |  organizational
    |                                                    v            |  memory, §8)
 INTERVENE  <---  HUMAN DECISION  <---  EXPLAIN  <--  IDENTIFY SIGNAL  |
    |                                                                 |
    +-----------------------------------------------------------------+
```

---

## 5. SIE Ownership vs Integration Boundary

The repository already draws this line more clearly, and more
consistently, than most greenfield architectures do — the task here was
to describe it accurately, not invent it.

**SIE owns** (confirmed, not assumed):
- Ingestion, normalization, and provenance of safety data it is given
- The governed ontology and terminology-mapping layer
- Deterministic statistical intelligence (indicators/trend/concentration/
  recurrence/anomaly/association/enterprise-risk-v1)
- Signal-to-candidate-finding generation
- The Risk Assessment workflow (findings, controls, control
  effectiveness, closure governance) — **this is SIE's own governed
  workflow, not an integration boundary**, and correctly so: risk
  assessment is intelligence-adjacent judgment, not a generic operational
  ticketing system.
- The knowledge corpus, embeddings, retrieval, and evidence-grounded RAG
- The predictive-model governance lifecycle
- Organizational safety memory (§8) and, once built, Field State (§6)
- Explanation and provenance/evidence chains for everything above

**SIE integrates with** (confirmed, via `INTEGRATION_GUIDE.md` and the
machine-client architecture):
- Incident/inspection/permit systems, HR/training systems, ERP, CMMS,
  contractor systems, IoT, other HSE platforms, and field-reporting
  apps — all as **data sources** (pushing structured events/documents in
  via a scoped `ApiClient` credential) and/or **consumers** (pulling
  intelligence/predictions/RAG answers out the same way). Safelytic is
  explicitly documented as "one consumer... any other authorized
  application integrates the exact same way" — there is no
  Safelytic-specific code anywhere in `app/predictions`, `app/intelligence`,
  or `app/rag`.

**One area worth flagging rather than assuming settled**: `SafetyAction`
today is a first-class, fully-owned SIE workflow (its own state machine,
history, permissions). This is defensible where an action originates
*from* SIE's own intelligence (a finding, an anomaly) — SIE is the
natural owner of "what did we decide to do about what we found." It is
less obviously correct if a customer's existing CMMS/work-order system
is meant to be the system of record for *execution* of that action (who
actually did the physical work, when, with what parts). The repository
already anticipates this partially — `SafetyAction.external_reference`
is explicitly "never interpreted or validated by SIE," a deliberate,
narrow escape hatch for exactly this case — but there is no first-class
"this action's execution is owned externally, SIE only tracks the
decision and the eventual verification" mode. This is worth an explicit
product decision before Intervention Intelligence (§10-11) is built:
does SIE own action *execution* state, or only the decision + outcome
verification around it? This document does not resolve it (§19, Open
Question 1) but flags it because §17's milestones depend on the answer.

### G. SIE vs connected operational systems

```
   Incident systems   Inspection systems   Permit systems   ERP / CMMS
   HR / training       Contractor systems    IoT              Other HSE platforms
         |                    |                  |                  |
         +--------------------+------- push -----+------------------+
                               v
                        [ ApiClient credential, scoped, org-pinned ]
                               v
                    +---------------------+
                    |         SIE          |  <- owns: intelligence, memory,
                    | (this architecture)   |     ontology, risk assessment,
                    +---------------------+     evidence, predictions
                               ^
                               | pull (advisory only, never autonomous)
         +--------------------+------------------+------------------+
         |                    |                  |                  |
   Safelytic UI       Third-party HSE UI    SIE's own frontend   Any future consumer
```

---

## 6. Field State

**Recommendation: Field State should begin as a derived, on-demand
intelligence *view* — not a persisted table, not a new source of
truth.** The reasoning:

1. The repository already has the exact precedent to build this on:
   `compute_enterprise_intelligence()` and
   `app/risk_assessment/reporting.py`'s report both compute a rich,
   multi-section, point-in-time-correct summary **live, from existing
   tables, with no snapshot mechanism** — and both explicitly document
   why that is correct ("historical integrity is free, not engineered").
   A persisted `FieldState` table would be a second, competing source of
   truth the moment any of its inputs changes, and would immediately
   reintroduce the exact staleness problem `events_as_of()` was built to
   prevent.
2. Nothing about "the state of a site right now" is naturally
   append-only or slowly-changing in the way a table wants to be — open
   findings close, actions complete, new events arrive continuously.
   Recomputing it on read (as every other intelligence surface in this
   codebase already does) is the only way to guarantee it is never
   stale.
3. If read performance eventually requires it, the correct evolution is
   a *cache* of a Field State computation (keyed on site + as_of,
   invalidated on write) — not a redesign into a mutable table. That is
   an implementation detail for a later milestone (§17, M32), not an
   architectural decision this document needs to make now.

**What Field State must answer before SIE can credibly claim to
understand a site "right now":**

| Dimension | Exists today? | Source |
|---|---|---|
| Organization / site identity | Yes | `Organization`, `Site` |
| Recent events (what has been observed) | Yes | `SafetyEvent` via `events_as_of()` |
| Deterministic risk picture | Yes | `enterprise-risk-v1` (§3.5) |
| Emerging signals (anomalies, patterns) | Yes | `enterprise_anomaly.py`, `recurrence.py` |
| Open findings / current risk assessment | Yes | Risk Assessment domain |
| Open actions, overdue actions | Yes | Actions domain, `ActionResponseSummary` |
| Control effectiveness picture | Yes | M29/29A control effectiveness summary |
| Relevant knowledge (procedures, standards) | Yes, but not automatically joined | RAG/retrieval, callable but not currently invoked *for* a site as part of any summary |
| Work activity / current operations | **No** | No first-class "what work is happening right now" entity |
| Workforce / contractor presence | **No** | No first-class workforce/contractor-on-site entity |
| Equipment state | **No** | No equipment entity at all |
| Permits in effect | **No** | No permit entity |
| Hazard/topic classification (e.g. "lifting is active here") | **No** (Gap G2 — `observation_topic` has no storage location) | — |
| Historical context / trend | Yes | `enterprise_trend.py` |

The honest answer: SIE can already credibly describe a site's **safety
signal picture** (events, risk, findings, actions, controls) — the
right-hand column of the loop. It cannot yet describe the **operational
context** those signals occurred within (who was there, what work, what
equipment, what permits) — because none of those entities exist in the
data model yet. Field State's v1 (§17, M31/M32) should be scoped
honestly to what SIE can already assemble (a "safety-signal Field
State"), with operational-context dimensions added only as real
ingestion sources for them appear — never fabricated to fill a
dashboard.

### C. Field State

```
                         FIELD STATE (as of a moment, per site)
        +----------------------------------------------------------+
        |  SAFETY SIGNAL PICTURE          (buildable today)         |
        |    - recent events (events_as_of)                          |
        |    - deterministic risk score + classification              |
        |    - active anomalies / recurring patterns                  |
        |    - open findings, current risk assessment                 |
        |    - open / overdue actions                                 |
        |    - control effectiveness summary                          |
        +----------------------------------------------------------+
        |  OPERATIONAL CONTEXT             (not yet modeled)          |
        |    - active work / permits          [Gap]                   |
        |    - workforce / contractors on site [Gap]                  |
        |    - equipment state                [Gap]                   |
        |    - hazard/topic classification    [Gap — ontology exists, |
        |      (e.g. "lifting active")          storage doesn't]      |
        +----------------------------------------------------------+
        |  RELEVANT MEMORY                 (buildable today, not      |
        |    - similar past findings          yet joined into one view)|
        |    - relevant procedures (RAG)                               |
        +----------------------------------------------------------+
```

---

## 7. Past / Present / Future

| Temporal dimension | What answers it today | Point-in-time correctness |
|---|---|---|
| **Past** — what happened? | `SafetyEvent` history, `RiskAssessmentHistory`, `SafetyActionHistory`, `AuditLog` | Strong for events (`events_as_of`); weak for "what did this specific row look like before its last update" (Gap G1) |
| **Present** — what is happening now? | Live recomputation of §3.5's seven lenses, current `RiskAssessment`/`SafetyAction` state | Strong — nothing is cached or stale by construction, since nothing is persisted |
| **Future** — what may happen next? | `app/predictions/` (fully built, governed) | Strong in principle (the entire pipeline is temporal-leakage-tested) — **but structurally unreachable today** because nothing consumes it (§3.10) |

**The one genuine risk this document identifies and must state plainly**:
`events_as_of()`'s dual guard (`event_time <= as_of AND ingestion_time
<= as_of`) is exactly correct for the intelligence layer's own
computations, and it is followed with real discipline everywhere it was
checked. The risk is not that this guard is wrong — it is that **any
future capability that queries `SafetyEvent` (or any new table) without
routing through it would silently reintroduce leakage**, and nothing in
the current architecture *enforces* that every new query goes through
this one function beyond convention plus the existing regression-test
suite. §17's milestones should explicitly require new temporal queries
to either call `events_as_of()`/`window_bounds()` directly or add an
equivalent regression test — never a bespoke `event_time <= as_of`
filter written inline.

A second, smaller point: predictive risk (Future) is currently the only
one of the three temporal dimensions with a fully built capability that
is *invisible* to a user. Closing that gap (§17, M32/M34) is not "adding
AI" — the AI-adjacent part (the trained model) already exists,
governed; what's missing is a presentation layer for an already-approved,
already-deployed model's output, gated exactly the way the backend
already gates it (`require_deployed=True`).

### D. Past / Present / Future

```
   PAST                          PRESENT                        FUTURE
   ---------------------------   ----------------------------   ---------------------------
   SafetyEvent history           events_as_of(as_of=now)        predict_as_of(as_of=now,
   RiskAssessmentHistory         live 7-lens intelligence          require_deployed=True)
   SafetyActionHistory           current RiskAssessment/Action   governed, abstains when
   AuditLog (write-only, Gap G3) state                            insufficient data/staleness
                                                                  NOT SURFACED ANYWHERE (Gap G0)
        |                              |                                |
        +-------- events_as_of() enforces event_time<=as_of AND --------+
                   ingestion_time<=as_of everywhere it is used
```

---

## 8. Organizational Safety Memory

The repository does not use this term, but it already builds most of
its substance:

```
   historical events (SafetyEvent, immutable-in-place, provenance-tracked)
        |
   risk assessments (approved = permanently frozen, per §3.7)
        |-- findings -- controls -- control effectiveness assessments
        |-- evidence (event / knowledge / intelligence-signal references)
        |-- actions (response, not evidence — distinct relationship)
        |
   knowledge corpus (procedures, standards, lessons — versioned, sourced,
                      verification-status-tracked)
        |
   terminology + ontology (how the organization's own vocabulary maps
                            to canonical meaning, versioned, never silently
                            rewritten)
```

Two principles keep this from corrupting provenance or temporal
correctness, both already enforced by the code rather than merely
intended:

1. **Approval freezes, it doesn't erase.** An approved risk assessment's
   findings/controls become permanently unmutatable
   (`require_editable()`); a decided terminology mapping's history is
   never rewritten, only superseded by a new version. Memory accumulates,
   it does not get corrected in place.
2. **Reading memory never means recomputing it with today's rules.**
   Reporting (§3.7) reuses the exact persisted values a finding was
   rated with; the `RiskAssessmentReportRead` explicitly states that
   `methodology_version`/`ontology_version` snapshots are recorded at
   the time, never re-validated against current governance state on
   read.

The one missing piece, consistent with §4/§10: memory currently has no
mechanism to record *whether an intervention worked*. "Lessons learned"
exists conceptually (a knowledge document *could* narratively describe
one), but there is no structured link from "we tried X, and Y happened"
back into memory a future signal-generation pass could consult. This is
exactly the Intervention → Outcome → Learning gap (§10), described here
from memory's side rather than the loop's side: organizational memory
today accumulates *what happened*, but not yet *what we learned from
what we did about it*.

---

## 9. Intelligence Object Model

The repository does not use most of these terms explicitly, but its
actual type boundaries already draw nearly this exact distinction —
this section names it so future milestones stop inventing new words for
concepts that already exist under a different name, and stop reusing
one word for two different things.

| Term | Meaning in SIE | Authority | Source | Lifecycle | Persisted or derived | AI may contribute? | Human approval required? |
|---|---|---|---|---|---|---|---|
| **Data** | A raw captured payload | The submitting system | Ingestion adapters | Captured once, never reinterpreted | Persisted (`source_value`) | No | No |
| **Event** | A canonicalized, governed record of something that happened | SIE (ingestion pipeline) | `SafetyEvent` | Created, occasionally updated in place (Gap G1) | Persisted | No (terminology mapping is deterministic/human-governed, never AI-inferred) | No (governance is at the mapping-decision level, not per-event) |
| **Observation** | *Not a distinct type in this codebase* — an "observation" is an `event_type` value, i.e. a kind of Event, not a separate object class. Using the word loosely elsewhere in this document (e.g. "field observation") means Event. | — | — | — | — | — | — |
| **Signal** | A statistically-computed deviation or pattern worth attention | SIE (deterministic computation) | `enterprise_anomaly.py`, `recurrence.py`, `association.py`, etc. | Computed fresh every read, never persisted independently | **Derived**, not persisted | No | No (a signal is informational, not a decision) |
| **Insight** | *Used loosely today for "an explanation attached to a signal."* This document recommends treating Insight as **Signal + Explanation**, not a fourth object — introducing a separate persisted "Insight" type would duplicate `explanations.py`'s existing evidence-linked output for no architectural benefit. | SIE | `explanations.py` | Derived alongside its signal | Derived | No (template-based) | No |
| **Finding** | A human-reviewable (or human-authored) statement that a specific risk exists in a specific assessment | SIE, but requires human review before it carries any rating | `RiskAssessmentFinding` | `IDENTIFIED → (UNDER_REVIEW) → ACCEPTED/REJECTED`, then `OPEN → ADDRESSED → CLOSED` | **Persisted** | No (candidate generation is a deterministic mapping, never AI) | Yes — rating requires human likelihood/consequence; closure requires `risk_assessment:approve` |
| **Risk** | Three structurally distinct meanings that must never be conflated (§3.10): (a) `enterprise-risk-v1` score, (b) a finding's inherent/residual rating, (c) a predictive-model output | Depends on which — (a)/(c) SIE-computed, (b) human-rated | `risk_score.py` / `RiskAssessmentFinding` / `Prediction` | Each has its own lifecycle, listed elsewhere in this table | (a)/(c) derived, (b) persisted | (c) only, fully governed | (b) yes; (a)/(c) no (but (c) requires approval *before it may be served at all*, a stronger gate than per-instance approval) |
| **Recommendation** | *Does not exist as a first-class object in this codebase today.* The closest analog is a governance validation report's `APPROVE/REJECT/REVIEW` string — explicitly a recommendation to a human reviewer, never self-executing. | SIE (where it exists) | `governance.py` (model governance only) | Ephemeral, computed per review | Derived | No | Yes, by definition (a recommendation that executes itself is a decision) |
| **Decision** | A human's explicit choice to accept, act on, or dismiss a signal/finding | The human | Attributed fields throughout (`assessed_by_user_id`, `approved_by_user_id`, `created_by_user_id`) | One event in time | Persisted, as an attribute of whatever it decided | No | By definition, yes — a Decision *is* a human act |
| **Intervention** | The action taken as a result of a Decision | The human (execution), SIE (tracking) | `SafetyAction` | `OPEN → IN_PROGRESS/BLOCKED → COMPLETED/CANCELLED` | Persisted | No | No (creation may be permission-gated, but is not "approved" the way a finding closure is) |
| **Outcome** | Whether the field state actually changed after an Intervention | **Does not exist as a first-class object today** (Gap G9) | — | — | Would need to be derived (statistical, `events_as_of`-based), never a stored causal claim | Statistical only if built (correlation, never causal) | Would need explicit design (§17, M33) |

**Conflicts found in existing terminology worth naming explicitly**:
"Risk" is used for three genuinely different things across the codebase
(§3.10) — every module that uses the word is careful to qualify which
one, but a reader skimming code without that context could easily
conflate them. This document's recommendation is not to rename
anything (the existing qualification discipline is sufficient and
already tested) but to require every future document/UI surface to
qualify "risk" the same way the code already does, never bare.

---

## 10. Intervention → Outcome → Learning

This is the loop's real gap, and it is worth being precise about
exactly what exists versus what does not, because the temptation is to
either overstate the gap (claim nothing exists) or understate it (treat
"action completed" as good enough).

**What already exists**, mapped onto the spec's own chain:

```
SIGNAL              -> exists (§3.5/3.6)
HUMAN DECISION       -> exists (Risk Assessment / Actions workspaces)
INTERVENTION          -> exists (SafetyAction creation/assignment)
IMPLEMENTATION         -> partially exists, and only for controls: control
                         effectiveness assessment (M29A) is the ONE place
                         in the codebase that asks "did this actually work,"
                         and it is explicitly attributed, rationale-required,
                         and never inferred from an action's status
VERIFICATION            -> exists for controls (as above); does NOT exist
                          for actions generally, or for findings
CONTROL EFFECTIVENESS    -> exists (M29A), explicitly NOT inferred from
                            action completion
OUTCOME                   -> does not exist as a computed object anywhere
NEW EVIDENCE                -> the mechanism exists (RiskAssessmentFindingEvidence
                              can cite anything, including presumably a
                              later event) but nothing today automatically
                              asks "should this finding's evidence be
                              re-examined given what happened since"
UPDATED INTELLIGENCE          -> `enterprise_intelligence_service` already
                                recomputes fresh on every read, so in the
                                narrowest sense "intelligence updates
                                automatically" — but nothing connects a
                                specific past intervention to a specific
                                later change in the numbers
```

The codebase already states, twice, independently, at two different
levels of the domain, the exact principle this section must not
violate:

> "A completed action never automatically closes a finding." (M27)
>
> "Control existence is not proof of effectiveness... nothing in this
> codebase ever infers effectiveness from a linked SafetyAction's
> status." (M29)

**Explicit distinctions this document requires any future milestone to
preserve**:

- **Action completion** — a status flag set by a human ("I did the
  thing"). Says nothing about whether the thing worked.
- **Implementation** — whether the control/change described by the
  action physically exists now (today, only assessed for controls, via
  M29A; not tracked for actions generally).
- **Verification** — a human's attributed check that implementation
  actually happened (today, `assessed_by_user_id`/`assessed_at` on a
  control; no equivalent for a bare action).
- **Control effectiveness** — a human's judgment, with required
  rationale, of whether an implemented control actually reduces risk
  (M29A, exists, correctly gated).
- **Outcome** — whether the underlying field condition measurably
  changed (does not exist; would need to be a statistical, `events_as_of`-
  anchored comparison of the relevant metric/recurrence pattern before
  vs. after the intervention, over a defined follow-up window).
- **Observed change** — the raw, uninterpreted metric movement an
  Outcome computation would be built from (partially exists — the same
  event/metric data `enterprise_trend.py` already reads — just never
  assembled into a before/after comparison keyed to a specific
  intervention).

**Correlation-not-causation, extended one stage further.** The existing
discipline in §3.5/3.9 (associations are correlation, never causation;
RAG citations ground claims in evidence, never assert unstated
conclusions) must extend unchanged into Outcome: "recurrence dropped
after this action" is a *correlation* SIE may compute and surface — it
must never be phrased or stored as "this action caused the improvement."
The architecture for this (§11, §17 M33) should reuse `association.py`'s
existing Pearson-correlation-with-explicit-INSUFFICIENT_DATA pattern
almost verbatim, applied to a before/after window around one
intervention's own timestamp, rather than inventing a new statistical
method.

### E. Intervention → Outcome → Learning

```
 SIGNAL -> HUMAN DECISION -> INTERVENTION -> [IMPLEMENTATION] -> [VERIFICATION]
                                                    |                  |
                                          (controls: M29A exists)  (controls: M29A exists)
                                          (actions: does not exist)  (actions: does not exist)
                                                    v
                                          [ OUTCOME ]  <-- GAP: does not exist.
                                                            Would compare events_as_of()
                                                            metrics before vs. after the
                                                            intervention's own timestamp,
                                                            correlation only, never causal.
                                                    v
                                          NEW EVIDENCE  (mechanism exists, not auto-triggered)
                                                    v
                                          UPDATED INTELLIGENCE (recomputes live, but not
                                                                  attributed back to the
                                                                  specific intervention)
                                                    v
                                                 LEARN  <-- feeds organizational memory (§8);
                                                             for predictive models only, this
                                                             already exists (outcome_tracking.py)
```

---

## 11. Contextual Reasoning

The worked example in the milestone's own instructions — repeated
lifting observations, a prior lifting event, an open lifting-related
action, a partially-effective control, increased contractor activity, a
recent risk assessment, relevant lifting procedure documents — is a
genuinely fair test of what SIE can and cannot do today.

**What SIE can already do, mechanically, toward this example**:
- Find the events (`events_as_of`, filterable by `event_type`/`event_subtype`)
- Find the finding/risk assessment (governed `risk_area_concept_id`
  join)
- Find the control and its effectiveness (M29A)
- Find the linked action (M27)
- Retrieve the relevant procedure documents (RAG, if asked a question
  naming the topic)

**What SIE cannot do today**: assemble these into one *contextually
relevant set* without a human separately querying each domain. There is
no cross-domain "these all relate to the same hazard topic" join —
because, as §3.3/§6 already noted, the `observation_topic` ontology
layer that would name "lifting" as a first-class, queryable hazard
category has no `SafetyEvent` storage location yet.

**Architecture recommendation — deterministic joins over a shared
vocabulary key, not a reasoning agent.** The correct next step is not
an LLM that "figures out" these records are related. It is:

1. Wire `observation_topic` (or an equivalent hazard-topic field) onto
   `SafetyEvent`/`RiskAssessmentFinding` (closes Gap G2).
2. Build one read-only query that, given a topic (or a
   `risk_area_concept_id`), returns every object across every domain
   that shares it — events, findings, controls, actions, and (via a
   scoped RAG/retrieval call using the topic as a filter, which
   `app/retrieval/filters.py` already supports) knowledge documents.
3. Present that as a **grouped, evidence-labeled list** — never a
   synthesized narrative claiming a relationship the query didn't
   establish.

This is exactly the same discipline `association.py` already applies to
two metrics, generalized to N records sharing a governed key. It never
needs to become an autonomous reasoning agent, because the "reasoning"
is a deterministic join over already-governed vocabulary — the
governance work (§3.3) is what makes the join meaningful, not any
inference step. An LLM may *summarize* the resulting grouped list in
prose later (§12, category D) — it must never be the thing that decided
the records were related in the first place.

---

## 12. AI Participation Model

The repository's own AI footprint is small, well-isolated, and already
follows almost exactly the categorization this section requires. This
is not a plan to build an AI system — it is a classification of the one
AI seam that exists (`app/llm/`, used only inside `app/rag/`) plus where
future, still-hypothetical AI participation would and would not be
appropriate, based on where the existing deterministic/governed
boundary already sits.

| Category | Meaning | Exists today? | Where it would sit |
|---|---|---|---|
| A. AI-assisted interpretation | Helping a human read/understand something already computed | Partially — RAG answers interpret retrieved evidence into prose | RAG only |
| B. AI-assisted retrieval | Finding relevant material | Yes — semantic embedding search (§3.9), never AI-*decided* relevance (thresholded, deterministic) | Retrieval layer |
| C. AI-assisted classification | Assigning a category | **No** — explicitly refused everywhere checked (terminology mapping, risk-area resolution, candidate generation all state "never fuzzy/LLM guessing") | Should remain refused; classification stays deterministic-mapping-table-or-human-governed |
| D. AI-assisted synthesis | Combining multiple sources into a summary | Yes, narrowly — RAG's grounded-context generation, always evidence-gated | RAG only; could extend to a future §11 contextual-reasoning summary, still evidence-gated |
| E. AI-assisted investigation | Helping a human dig into a question | Not built; RAG's query interface is the closest primitive | A future "ask a question about this site" surface, still routed through the same deterministic gates |
| F. AI-assisted explanation | Explaining *why* | Statistical explanations are template-based, never AI (§3.5); RAG citations are evidence-based, never AI-invented | Statistical explanation stays deterministic, permanently; RAG explanation stays evidence-gated |
| G. AI-assisted prioritization | Helping decide what to look at first | **No** — "Needs attention" today is deterministic counts (open/overdue/anomalous/recurring), never an AI ranking | Should remain deterministic; if ever AI-assisted, must remain a *suggestion a human can see the inputs for*, never a hidden score |

**What must remain deterministic, permanently, regardless of any future
AI investment** (already true today, and this document recommends never
changing it): terminology/ontology resolution, risk-area classification,
candidate-finding generation, the seven statistical intelligence lenses,
control-effectiveness bookkeeping (the *assessment itself* is human
judgment; the *bookkeeping* of it is deterministic), and any future
Outcome computation (§10). None of these should ever become "AI decides"
— they are the parts of the system a regulator or an auditor needs to
be able to fully explain without reference to a model.

**Human-only decisions — investigated against the spec's own candidate
list, all confirmed as already-enforced in code**:

| Decision | Enforced today? | Mechanism |
|---|---|---|
| Risk acceptance | Yes | Human sets likelihood/consequence; nothing infers a rating |
| Risk assessment approval | Yes | `risk_assessment:approve` permission, dedicated endpoint |
| Finding closure | Yes | Dedicated endpoint, `closure_reason` required, `risk_assessment:approve` |
| Control effectiveness declaration | Yes | M29A dedicated endpoint, rationale required, `NOT_ASSESSED` may never masquerade as a conclusion |
| Investigation completion | N/A today — no formal "investigation" object exists yet distinct from a finding/risk assessment | — |
| Corrective action approval | Partially — action *creation* is permission-gated (`intervention:manage`), but there is no distinct "approve this action plan" step today, only creation and status transitions | Worth a product decision if a formal approval step is ever wanted (§19) |
| Ontology governance | Yes | `GOVERNANCE_MANAGE`, `PLATFORM_ADMIN`-only for GLOBAL |
| Authoritative compliance conclusions | Yes, by omission — SIE has no compliance-conclusion object at all; nothing outputs "this organization is compliant/non-compliant" | Correct: this should stay a human/legal determination entirely outside SIE |
| Attribution/blame | Yes, by omission — no "who is at fault" field exists anywhere in the schema | Correct: should stay absent, permanently |

---

## 13. Human Decision Boundary

Refined from the spec's own draft list, checked against what the code
actually does (not merely says):

**SIE MAY:**
- Surface signals (anomalies, patterns, recurring counts)
- Explain evidence (template-based statistical explanations,
  evidence-cited RAG answers)
- Retrieve knowledge (RAG, filtered, scoped, sufficiency-gated)
- Identify patterns (recurrence detection)
- Highlight anomalies (z-score scan)
- Provide contextual analysis (association/concentration — always
  correlation-labeled)
- Support investigation (evidence retrieval, cross-domain joins per §11)
- Suggest areas for review (candidate findings — `IDENTIFIED`, never
  auto-accepted)
- Summarize evidence (RAG synthesis, always cited)
- Help prioritize human attention (deterministic counts today — open/
  overdue/anomalous — never an opaque AI ranking)

**SIE MUST NOT, silently or otherwise (confirmed enforced, not aspirational):**
- Declare root cause — no such field/output exists anywhere
- Declare compliance — no such object exists
- Approve risk assessments — human-only, permission-gated
- Close findings — human-only, dedicated endpoint, reason required
- Approve controls — no "approve a control" concept exists; effectiveness
  is *assessed*, with rationale, by a named human
- Declare controls effective — same as above; `NOT_ASSESSED` cannot
  masquerade as a conclusion
- Accept residual risk — residual risk is *computed* from a human-supplied
  residual likelihood/consequence; nothing accepts it on the
  organization's behalf
- Assign blame — no such field exists
- Override governed ontology — every mutation path is
  `GOVERNANCE_MANAGE`-gated; no code path bypasses it
- Fabricate evidence — RAG explicitly rejects any answer with zero valid
  citations (`UNSUPPORTED_CLAIM_REJECTED`)
- Convert correlation into causation — no causal vocabulary exists
  anywhere in the association/trend/outcome-adjacent code

The only addition this investigation recommends to the spec's own list:
**SIE must not silently promote a predictive model into a serving
path.** This is already true (`ModelApproval` requires a named human
reviewer at every lifecycle transition, and `predict_as_of()` requires
`require_deployed=True` for live traffic) — worth stating explicitly
here since §3.10/§17 recommend finally connecting this capability to a
real consumer, and the connection must not weaken this existing gate.

---

## 14. Evidence & Provenance

**A common provenance principle, synthesized from what already exists
in three different, currently-unreconciled places**:

```
deterministic intelligence:  calculation_versions (per lens) + evidence_reference
                              (points at the exact source object: an event id,
                              a risk-score component key, a recurrence pattern_key)

risk assessment:             RiskAssessmentFindingEvidence (evidence_type +
                              reference_id/reference_label) + RiskAssessmentHistory
                              (who changed what, when, attributed)

RAG / AI interpretation:     Citation (chunk_id -> document_version_id -> source_id)
                              + reproducibility payload (query, filters, prompt_version,
                              embedding model identity, per-citation ids) logged via
                              AuditService
```

All three already answer "why is SIE telling me this" for their own
domain — but they are three separate mechanisms with three separate
shapes, not one shared provenance object. **This document recommends
against unifying them into one generic "Provenance" table** (that would
be exactly the kind of "speculative schema merely for demonstration"
this milestone is instructed not to create) — each domain's provenance
answers a genuinely different question with a genuinely different
shape, and forcing them into one polymorphic table would make each
domain's own, already-correct answer harder to query, not easier.

**What is missing is not a new provenance mechanism — it is a
consistent minimum contract every future intelligence surface must
satisfy**, stated once here so it doesn't need re-deriving per
milestone:

> Any object SIE presents as intelligence (a signal, an explanation, a
> RAG answer, a future Outcome computation) must be traceable, without
> guessing, through: **output → the specific computation/evidence that
> produced it → the specific source record(s) → the source system →
> a timestamp → the organization/site it belongs to.** If any link in
> that chain cannot be produced, the object must say so explicitly
> (`INSUFFICIENT_DATA`, `NO_RELEVANT_EVIDENCE`, `UNSUPPORTED_CLAIM_REJECTED`
> — the existing vocabulary already has this instinct; extend it, don't
> replace it) rather than presenting an ungrounded conclusion.

**Confidence scores — explicit recommendation against inventing one.**
No component of this system today outputs a numeric "confidence" for a
statistical or AI-derived result (a risk score's *magnitude* is not a
confidence value; `similarity` on a retrieval result is a distance
metric, not calibrated confidence). This document recommends this stay
true: an unvalidated confidence number is worse than no number,
per the milestone's own explicit instruction not to invent unsupported
confidence scores. Where genuine calibration exists (predictive models'
own calibration validation, §3.10), it may eventually be surfaced — but
only attached to the one object type it was actually validated for,
never generalized into a system-wide "confidence" concept.

### F. AI participation boundary

```
                     +-----------------------------------------------+
                     |  DETERMINISTIC CORE (permanent, non-negotiable) |
                     |  ingestion, terminology/ontology governance,    |
                     |  7 statistical lenses, candidate generation,    |
                     |  risk assessment workflow, control-effectiveness|
                     |  bookkeeping, retrieval ranking/thresholds       |
                     +-----------------------------------------------+
                                        |
                                        | evidence flows in, gated
                                        v
                     +-----------------------------------------------+
                     |         DETERMINISTIC GATE (RAG today)          |
                     |  insufficient evidence -> abstain                |
                     |  conflicting sources -> SOURCE_CONFLICT           |
                     |  privacy rule violated -> PRIVACY_BLOCKED          |
                     +-----------------------------------------------+
                                        |
                                        | only past all three gates
                                        v
                     +-----------------------------------------------+
                     |     AI PARTICIPATION (narrow, swappable)         |
                     |  categories A/B/D/F today (interpretation,       |
                     |  retrieval, synthesis, explanation) — RAG only    |
                     +-----------------------------------------------+
                                        |
                                        | citation validation, after generation
                                        v
                     +-----------------------------------------------+
                     |  no valid citation -> UNSUPPORTED_CLAIM_REJECTED |
                     |  every surfaced claim traces to a real source    |
                     +-----------------------------------------------+
```

---

## 15. Temporal Integrity

Restated precisely, because it is the architectural property every
future milestone in this document depends on most:

- **The guarantee**: `events_as_of(organization_id, as_of, window_days,
  ...)` filters on `event_time <= as_of AND ingestion_time <= as_of` —
  a record that *happened* before `as_of` but was only *reported/
  ingested* after it is correctly excluded. This is the concrete
  mechanism behind "never use future information to explain what was
  knowable at an earlier time."
- **Where it is enforced**: every statistical lens in
  `enterprise_intelligence_service.py`, candidate generation, and (via
  `temporal_split.py`) predictive-model training/backtesting.
- **Where it is *not yet* structurally enforced**: nothing prevents a
  future developer from writing a new query against `SafetyEvent` that
  filters only on `event_time`, forgetting `ingestion_time` — the
  guarantee is convention-plus-tests today, not a database constraint
  or a query-builder that makes the mistake impossible. §17
  (M31/M32/M33) should require every new temporal query to route
  through `events_as_of()`/`window_bounds()` or add an equivalent,
  named regression test — stated as a standing rule here so it does not
  need re-justifying per milestone.
- **Current vs. historical state are already correctly treated as
  different problems** in exactly the place that matters most: M28's
  `ActionResponseSummary` is the one deliberately-current (not
  historical) section of an otherwise fully historical risk-assessment
  report, and it carries its own `computed_at` timestamp specifically
  so a reader can tell the two apart. This is the correct pattern to
  reuse for Field State (§6, always current) versus organizational
  memory (§8, always historical-as-of).
- **The one real gap**: `SafetyEvent`'s own in-place mutation (§3.2, Gap
  G1) means that while *queries* are temporally correct (they correctly
  exclude a not-yet-known future), the *row itself* cannot answer "what
  did this look like as of an earlier as_of" once it has been updated —
  only that it existed. This is a narrower problem than it sounds
  (most `SafetyEvent` fields are set once at ingestion and never
  updated in practice), but it should be named honestly rather than
  assumed away.

---

## 16. Current Gaps

**P0 — architectural blocker** (the loop cannot close, or a core
guarantee is at risk, without addressing these):

- **G0 — Predictive risk is fully built and governed but has zero real
  consumer.** Not a "missing capability" in the traditional sense — a
  *complete, tested, correctly-gated* capability that the frontend does
  not even declare a type for. This is the fastest, lowest-risk way to
  materially advance "the brain for the field," because it requires no
  new backend capability, only connecting one that already exists,
  through the exact gate it already enforces (`require_deployed=True`).
- **G9 — No Intervention → Outcome → Learning mechanism exists** beyond
  the control-effectiveness/finding-closure governance (§3.7) and
  predictive-model outcome tracking (§3.10, models only). This is the
  loop's one truly missing joint (§10) and the reason the loop cannot
  yet claim to "learn."

**P1 — important capability** (materially limits what SIE can honestly
claim, but the system remains internally consistent without them):

- **G1 — `SafetyEvent` has no row-level version history.** Historical
  reconstruction of "what did this record look like before" is not
  supported (§3.2, §15).
- **G2 — The `observation_topic` ontology layer has no `SafetyEvent`
  storage location.** Blocks Field State's hazard-topic dimension (§6)
  and Contextual Reasoning's cross-domain join (§11).
- **G3 — `AuditLog` is write-only; no read/query API exists.** A rich
  ~50-action-type trail with no way to answer "show me what happened"
  without a direct database query.
- **G5 — No first-class work-activity/workforce/contractor/equipment/
  permit entities.** Blocks Field State's operational-context dimension
  (§6) entirely; these are genuinely new domains, not gaps in existing
  ones.
- **G6 — Statistical explanation and RAG citation are two separate
  mechanisms** with no unified "explain any intelligence object"
  surface (§4, stage 8). Not urgent to unify structurally, but worth
  tracking so a future UI doesn't need two different explanation
  components per object type.
- **G8 — No implementation/verification concept for Actions generally**
  (only controls have one, via M29A). Needed before Intervention
  Intelligence (§11) can respect the action-completion-≠-effectiveness
  distinction the codebase already insists on one level down.

**P2 — future enhancement** (real, worth tracking, not blocking
anything in §17's proposed sequence):

- **G4 — `caller_kind` capture in `AuditLog.event_metadata` is a
  per-call-site convention, not structurally guaranteed.**
- **G7 — No persistence/caching of statistical intelligence results.**
  An accepted, documented v0.1 tradeoff; only becomes a real problem at
  a scale this document has no evidence the system has reached.
- Two coexisting auth-dependency idioms (`RequestContext`-adopting vs.
  `deps_auth`-only administrative routers) — documented as deliberate,
  a maintainability note rather than a defect.
- Retrieval has no keyword/BM25 fusion or reranking yet — explicitly
  flagged as a documented future architecture in `retrieval_service.py`
  itself, not something this investigation is newly discovering.
- No background re-embedding worker — `reembedding_service.py` is
  explicitly built as "the seam a future worker would call into,"
  already correctly shaped for this.
- Evidence-linking is fragmented across three domains (RAG's transient
  `Citation`, Risk Assessment's persisted `RiskAssessmentFindingEvidence`,
  and Actions' complete absence of one). Not urgent to unify — each
  domain's shape fits its own job — but worth a future milestone
  deciding whether Actions ever needs one, rather than each future
  domain reinventing its own.

---

## 17. Proposed Future Milestones

The instructions explicitly permit replacing the spec's own six-name
draft. This investigation's own findings argue for a different shape:
**connect what exists (M31) before building what's missing (M32-M33)**,
and treat the AI layer (M34) as strictly the last thing to touch, once
the deterministic loop actually closes — because an AI layer built on
top of a loop that doesn't yet produce Outcomes has nothing honest to
synthesize about intervention effectiveness.

### M31 — Field State & Predictive Connection v0.1

**Purpose**: close Gap G0 (connect predictive risk to a real consumer)
and stand up Field State v1 (§6) scoped honestly to what already
exists — the safety-signal picture, not the not-yet-modeled operational
context.

**Why needed**: the single highest-leverage, lowest-risk step available
— no new backend capability, only wiring already-governed capabilities
into one read model and one UI surface.

**Dependency**: none beyond the current baseline.

**Should NOT build**: any new statistical/predictive capability; any
persisted Field State table (must remain a derived view, §6); the
`observation_topic` storage wiring (that's a real schema change,
belongs in whichever milestone actually needs the hazard-topic
dimension — likely M32).

**Expected architectural outcome**: one backend read model
(`GET /field-state?site_id=...&as_of=...` or equivalent) composing the
seven-lens intelligence, open findings/actions/controls, and — gated
exactly as `predict_as_of()` already requires — an already-approved
prediction where one exists; one frontend surface presenting it,
following the existing "no fixture fallback, honest empty state"
principle from Intelligence/Risk Assessments.

### M32 — Operational Context Foundation v0.1

**Purpose**: begin closing Gap G5 (work activity, contractor presence,
equipment, permits) and Gap G2 (`observation_topic` storage), starting
with whichever one or two dimensions have a real, available data source
today — never inventing an entity merely to complete a diagram.

**Why needed**: without at least one operational-context dimension,
Field State (M31) remains a safety-signal picture, not a field
picture — and Contextual Reasoning (§11) has nothing concrete to join
events/findings against beyond the hazard-topic key.

**Dependency**: M31 (Field State's read model needs to exist before
it's worth extending).

**Should NOT build**: a generic "any entity" framework speculatively
covering all five candidate dimensions at once. Pick the one with real
data available (this investigation did not find evidence of which
that is — a product/data-availability question, §19) and build that
one dimension's ingestion + Field State integration completely, rather
than five half-built ones.

**Expected architectural outcome**: one new first-class operational
entity (e.g. permits, or contractor presence — whichever has a real
source), `observation_topic` wired onto `SafetyEvent`, and the
Contextual Reasoning join (§11) built as one new deterministic query
joining events/findings/actions/knowledge by shared topic — not an
agent, a query.

### M33 — Intervention & Outcome Intelligence v0.1

**Purpose**: close Gap G9 and Gap G8 — the loop's real missing joint.
Build the Outcome computation (before/after correlation around an
intervention's own timestamp, `events_as_of`-anchored, never causal)
and extend implementation/verification to Actions generally, following
the exact discipline M29A already established for controls.

**Why needed**: this is the step that turns SIE from "explains the past
and present" into "learns from what was decided" — the architectural
core of the product thesis's own closing loop (§2).

**Dependency**: M31 (Field State gives Outcome something concrete to
compare "before" and "after" against); does not strictly depend on M32,
though richer operational context would make Outcome's before/after
comparison more precise.

**Should NOT build**: any causal claim, any automatic finding-closure or
control-effectiveness inference from an Outcome result (Outcome informs
a human's later effectiveness assessment; it must never set one
itself — the exact discipline §10 already requires), any autonomous
re-triggering of a new risk assessment.

**Expected architectural outcome**: a new, `association.py`-styled
deterministic Outcome computation; an Action-level implementation/
verification concept mirroring M29A's control-effectiveness pattern
(dedicated endpoint, required rationale, never inferred from status);
Outcome results feeding into organizational memory (§8) as a new,
explicitly-labeled evidence type future signal generation may cite.

### M34 — Embedded AI Intelligence Layer v0.2

**Purpose**: extend the existing, narrow RAG-only AI participation
(§12) to the additional categories §12 identifies as appropriate
(A/D/F beyond RAG — interpretation/synthesis/explanation of the
now-richer Field State and Contextual Reasoning outputs from M31-M33),
strictly through the same deterministic-gate-then-citation-validation
architecture §3.9/§14 already enforces. Explicitly *not* a new AI
capability category — the same one, applied to more inputs.

**Why needed**: only once Field State, Contextual Reasoning, and
Outcome exist (M31-M33) is there anything honest for an AI layer to
synthesize — an AI summarizer built before them would have nothing
grounded to summarize beyond what RAG already covers.

**Dependency**: M31, M32, M33.

**Should NOT build**: any new AI participation category beyond A/B/D/F
(§12); any classification, prioritization-by-AI, or causal-language
capability; any change to the existing deterministic gates in
`app/rag/` — extend the *inputs* available to the existing gate/
citation-validation machinery, never weaken the machinery itself.

**Expected architectural outcome**: the existing RAG pipeline (§3.9)
accepts Field State/Contextual-Reasoning-joined evidence as an
additional evidence source alongside the knowledge corpus, subject to
the identical sufficiency/conflict/privacy gates and citation
validation already built — no parallel AI pathway.

### M35 — Continuous Safety Intelligence v0.1

**Purpose**: revisit performance/persistence tradeoffs deferred
throughout this document (Gap G7 — cached Field State/intelligence
results; Gap G3 — a real `AuditLog` read API; Gap G1 — event version
history, if by then still needed) once real usage patterns from
M31-M34 make the actual bottlenecks knowable, rather than guessing now.

**Why needed**: this document explicitly declines to solve performance
problems that haven't been observed yet (per its own "do not inflate
minor technical debt into architectural blockers" instruction) — this
milestone exists as the deliberate, honest placeholder for "come back
once M31-M34 tell us what actually needs caching."

**Dependency**: M31-M34.

**Should NOT build**: speculative caching/indexing infrastructure
ahead of measured need; a background worker system merely because one
was mentioned as a future seam (`reembedding_service.py`) — only build
one once a real queue of work exists to justify it.

**Expected architectural outcome**: whatever the actual, measured
bottlenecks from M31-M34 turn out to be, addressed narrowly — this
milestone's own scope should be written at the time, from evidence, not
predicted here.

---

## 18. Architectural Principles

All fourteen of the spec's own candidate principles were checked
against the actual repository. All fourteen hold, without exception —
this is a genuinely disciplined codebase, not merely a well-intentioned
one:

1. **SIE is the intelligence layer, not the entire HSE operating
   system.** Confirmed (§5) — Actions is the one domain worth watching
   (§5's open question), everything else is unambiguous.
2. **Evidence before assertion.** RAG rejects unsupported claims
   outright (§3.9); statistical explanations always carry
   `evidence_reference` (§3.5).
3. **Provenance before interpretation.** RAG's deterministic gate runs
   entirely before the one LLM call (§3.9); candidate findings carry
   their originating calculation version before any human interprets
   them (§3.6).
4. **Time matters.** `events_as_of()` is the single, tested choke point
   (§3.4, §15).
5. **Current state and historical state are different problems.**
   `ActionResponseSummary.computed_at` vs. the rest of an assessment
   report is the clearest existing example (§15); Field State (§6)
   should be built on the same distinction.
6. **Deterministic facts must remain authoritative.** No AI touches
   ingestion, terminology, ontology, or the seven statistical lenses
   (§3.5, §12).
7. **Statistical intelligence must remain distinguishable from
   causation.** Association is Pearson correlation, explicitly
   non-causal by construction (§3.5); this document extends the same
   discipline to the proposed Outcome computation (§10, §17 M33).
8. **AI interpretation must remain distinguishable from authoritative
   organizational decisions.** RAG answers are advisory, never
   self-executing (§12); no code path lets an AI output close a
   finding, approve a control, or accept risk.
9. **Human governance remains authoritative for consequential safety
   decisions.** Verified item by item in §12/§13, all enforced in code,
   not merely documented.
10. **Interventions must eventually produce measurable feedback.** Not
    yet true (§10, Gap G9) — this is the one principle the current
    architecture does not yet satisfy, and §17's M33 exists
    specifically to close it.
11. **Organizational memory must improve future field understanding.**
    Partially true — memory accumulates correctly (§8), but nothing yet
    feeds a verified outcome back into future signal generation (same
    gap as #10).
12. **Intelligence should be explainable and traceable.** Confirmed
    throughout §3.5/§3.9/§14, with a genuinely enforced (not aspirational)
    citation-rejection mechanism in RAG.
13. **Tenant isolation and governance remain foundational.** Confirmed
    defense-in-depth (§3.11) — schema, query, and authorization layers
    all independently enforce it.
14. **Existing capabilities should be composed before new parallel
    systems are invented.** This is this document's own governing
    method (§17's M31 is entirely composition, zero new capability) and
    the reason no new backend capability is proposed until M32.

---

## 19. Open Questions

These are genuine product/architecture decisions this investigation
surfaced but cannot resolve from the repository alone — each is named
here rather than silently decided:

1. **Does SIE own Action *execution* state, or only the decision and
   outcome verification around it** (§5)? The current model (SIE fully
   owns the Action state machine) is defensible for SIE-originated
   actions but untested against a customer whose CMMS/work-order system
   is meant to be the system of record for physical execution.
   `external_reference`'s existing "never interpreted by SIE" design
   is a hint toward the second answer, but no product decision was
   found settling it.
2. **Which operational-context dimension (§6, §17 M32) has a real,
   available data source first** — permits, contractor presence,
   equipment, or something else? This determines M32's actual scope and
   cannot be answered from the codebase; it depends on what a real
   deploying organization can actually feed SIE.
3. **Should "corrective action approval" become a formal, distinct
   governance step** (§12), the way risk-assessment approval and
   control-effectiveness assessment already are — or is action
   creation's existing `intervention:manage` gate sufficient? The
   current system has no formal approval step for an action plan
   itself, only for creating/assigning it.
4. **How should Outcome computations (§10, §17 M33) be windowed** — a
   fixed follow-up period, a configurable one per action type, or tied
   to the next risk assessment cycle? `association.py`'s existing
   fixed-window pattern is a reasonable default but this is a genuine
   methodology decision, not an engineering one, and likely deserves
   the same "provisional/initial default, not scientifically validated"
   honesty the existing statistical thresholds already carry.
5. **Should `AuditLog` (Gap G3) gain a read API, or should per-resource
   history (`RiskAssessmentHistory`/`SafetyActionHistory`) remain the
   only queryable trail, with `AuditLog` staying a write-only security
   sink by design?** Both are legitimate architectures; the current
   state (no read API) may be intentional rather than an oversight —
   this investigation could not determine which from the code alone.

---

## 20. Final Recommended Architecture

SIE's existing capabilities, composed rather than replaced, already
implement most of the operational intelligence loop this document
formalizes (§4). The recommended path forward is deliberately
conservative, in the same spirit the codebase itself already applies to
every one of its own milestones:

1. **Connect before you build (M31).** The predictive-risk lifecycle
   (§3.10) is the clearest example in the entire codebase of a fully
   governed, fully tested capability sitting unused — closing that gap
   costs no new architecture at all.
2. **Name Field State as a derived view, never a new source of truth
   (§6).** Every existing precedent in this codebase (reporting,
   enterprise intelligence) already computes rich, point-in-time-correct
   summaries live; Field State should be the same pattern, generalized,
   not a new persistence model.
3. **Close the loop's one real gap deliberately, not incidentally
   (§10, M33).** Intervention → Outcome → Learning is the single
   architectural piece that does not yet exist anywhere in the
   repository. It should be built with the same correlation-not-
   causation discipline `association.py` already enforces, and the
   same never-infer-from-status discipline M27/M29A already enforce one
   level down — never as a shortcut that lets "action completed" stand
   in for "risk actually reduced."
4. **Let AI extend reach, never authority (§12, M34).** The existing
   RAG architecture is the template for every future AI participation
   this document anticipates: evidence-gated before generation,
   citation-validated after it, and never the thing that makes a
   consequential decision. This should remain true even as AI touches
   more of the loop (Field State summaries, contextual-reasoning
   synthesis) — the gate architecture generalizes; the governance
   boundary does not move.
5. **Defer what hasn't been proven necessary (M35).** This document
   deliberately does not propose caching, background workers, or a
   unified provenance table ahead of evidence that any of them are
   actually needed — consistent with the milestone's own instruction
   not to inflate technical debt into architectural blockers, and with
   the codebase's own consistent preference for the smallest
   correct architecture over the most impressive one.

None of this requires SIE to become anything the product thesis (§2)
warns against. Every recommendation in this document is a composition
of capabilities the repository already built correctly, aimed at the
one place the loop does not yet close.
