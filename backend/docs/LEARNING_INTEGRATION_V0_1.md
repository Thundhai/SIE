# SIE Learning Integration & Intelligence Adaptation Architecture v0.1 (SIE Milestone 41)

## 1. Why M41 exists

SIE Milestone 40 established `OrganizationalMemory`: a governed,
durable knowledge statement, explicitly authored by an authorized
actor from an `ACCEPTED` learning candidate. M40 deliberately stopped
there — a memory sat in the database, correct and governed, but
consumed by nothing. Nothing in SIE's intelligence reasoning ever read
it.

This milestone answers the question M40 explicitly deferred:

> "How does SIE actually use organizational memory to improve
> intelligence?"

The answer this milestone gives is narrower than the question might
suggest: SIE does not yet *use* memory to change what its models,
thresholds, or rules compute. It uses memory to *inform the context* a
human (or downstream consumer) sees alongside existing intelligence
output — a fifth, independent lens next to Observed/Deterministic/
Predictive/Knowledge, always separately labeled, always traceable back
to its own governed source, never blended into any existing signal.

```
OrganizationalMemory (M40, ACTIVE)
    -> M41: eligibility + applicability filter
        -> a labeled, traceable list of applicable memories
            -> read alongside existing intelligence (M32/M33) or a
               specific decision's own recorded context (M34)
```

## 2-5. Relationship to M37/M38/M39/M40

The full provenance chain this milestone reads from, never rewrites:

```
IntelligenceDecision (M34)
    -> IntelligenceOutcome (M37) -- ground truth: what happened
        -> IntelligenceOutcomeVerification (M38) -- was it trustworthy?
            -> IntelligenceLearningCandidate (M39) -- eligible for learning?
                -> governance decision == ACCEPTED (M39)
                    -> OrganizationalMemory (M40) -- durable knowledge
                        -> M41 integration (this milestone)
```

M41 touches none of M37/M38/M39/M40's own write paths, tables, or
governance-resolution logic. It reuses two functions verbatim:
`app.services.organizational_memory_service.
resolve_current_memory_governance()` (M40) and
`app.intelligence.temporal.is_project_site_associated_as_of()`
(M35B/M36). No competing "latest memory status" or "latest project/site
membership" implementation exists anywhere in this codebase.

## 6. Exactly how memory enters intelligence context

`app.intelligence.memory_integration.resolve_eligible_organizational_
memories()` is the single entry point. Given `organization_id`, `scope`
(`"organization"`/`"site"`), an optional `site_id`/`project_id`, and an
`as_of` (defaulting to now), it returns a `MemoryIntegrationContext`: a
deterministic, ordered list of `IntegratedMemory` — each one a memory
judged both *eligible* (governance) and *applicable* (structural scope
match) to that context, carrying its own full provenance.

This is exposed as three new, independent, read-only endpoints:

```
GET /api/v1/intelligence/memory-context
GET /api/v1/intelligence/sites/{site_id}/memory-context
GET /api/v1/intelligence/decisions/{decision_id}/memory-context
```

Placed alongside `GET /intelligence/context`/`GET /intelligence/
attention` (M32/M33) and `GET /intelligence/decisions` (M34)
respectively — the same routers, the same authorization shape, never a
new context system. Memory integration is **not** folded into
`FieldIntelligenceContextRead`'s own four categories: it is its own,
separately-versioned, separately-tested composition
(`MEMORY_INTEGRATION_VERSION`), so M32's own already-tested response
contract is untouched by this milestone.

## 7. Applicability semantics

Not every memory is relevant to every context (spec §9). Applicability
is derived from exactly one already-existing, immutable, structured
field: `IntelligenceOutcome.site_id` — reached via a live join through
the memory's own `learning_candidate_id -> IntelligenceLearningCandidate.
outcome_id`. `OrganizationalMemory` itself carries no site/project field
of its own; M41 never denormalizes one onto it.

Four possible outcomes, each fully explainable
(`MemoryApplicabilityBasis`):

| Basis | Meaning |
|-------|---------|
| `ORGANIZATION_WIDE` | The memory's own outcome has no site at all — applicable everywhere in the organization. |
| `SITE_MATCH` | The context is site-scoped, and the memory's own outcome's site is that exact site. |
| `PROJECT_SITE_MATCH` | The context is organization-scoped with an explicit `project_id`, and the memory's own outcome's site is genuinely associated with that project as of `as_of` (via `is_project_site_associated_as_of()`). |
| `ORGANIZATION_SCOPE_ROLLUP` | The context is organization-scoped with no `project_id` narrowing — every site's memories roll up, mirroring `compute_enterprise_intelligence()`'s own identical organization-scope behavior. |

No embeddings, no similarity score, no LLM call, no numeric confidence
— every inclusion is one deterministic structural comparison, always
traceable to the exact rule that produced it.

**Known, documented limitation.** `IntelligenceOutcome` carries no
`project_id` of its own (only `SafetyEvent`-level project attribution
exists, per M35A) — so a memory can only be matched to a project
*through* its site, never through a direct project attribution of the
underlying outcome. If a future milestone gives `IntelligenceOutcome`
its own project attribution, `PROJECT_SITE_MATCH` can be extended to
use it directly; until then, this is the smallest correct mechanism the
existing architecture supports, not a fabricated one.

## 8. ACTIVE/RETRACTED semantics

Reused verbatim from M40, never forked. A memory is eligible iff its
resolved current governance decision (`resolve_current_memory_
governance(..., as_of=as_of)`) is either absent (the implicit `ACTIVE`
state) or explicitly `ACTIVE`. A `RETRACTED` resolution excludes it —
no exceptions, no override.

## 9. `as_of` semantics — a hard requirement

Two independent checks, both required, per every context evaluation:

1. `OrganizationalMemory.created_at <= as_of` — a memory that did not
   yet exist at `as_of` is never considered, regardless of governance.
2. Governance is resolved *as of that same `as_of`*, never today's
   current governance.

Worked example (identical to the spec's own): a memory created on day
0 and retracted on day 20, evaluated `as_of` day 5, is **included**
(`ACTIVE` as of day 5). Evaluated `as_of` day 25, it is **excluded**
(`RETRACTED` as of day 25). Both directions are covered by dedicated
tests (`tests/test_memory_integration_service.py::
test_memory_active_at_t_but_retracted_later_is_included_at_t`/
`test_memory_retracted_before_t_is_excluded_at_t`), plus an explicit
anti-regression test proving today's current-state governance is never
substituted for a historical `as_of`
(`test_current_reconstruction_does_not_use_todays_governance_for_
historical_context`).

## 10. Tenant isolation

Every query is filtered by `organization_id` first, at the SQL level —
a memory from a different organization is structurally unreachable, not
merely filtered after the fact. The three new endpoints use the same
authorize-then-trust `organization_id` query-parameter shape their
sibling M32/M33/M34 endpoints in the same router files already use
(`app/api/v1/intelligence.py`, `app/api/v1/intelligence_decisions.py`)
— `RequestContext`/`require_context_permission()`'s own
`authorize_context()` already guarantees a machine caller's credential-
bound organization must exactly equal the query parameter before any
handler runs. No new tenant-resolution mechanism was introduced.

## 11. Project/site scope

Reuses M35B/M36's `is_project_site_associated_as_of()` verbatim for
project-narrowed applicability (§7). Site-scope requests reuse the
same `_require_owned_site()` ownership-check shape every other site-
scoped route in `app/api/v1/intelligence.py` already uses — a site from
a different organization is a 404, never a 403. No `ProjectSite`
relationship, no new attribution mechanism, is introduced.

## 12. Provenance

Every `IntegratedMemory` carries `learning_candidate_id`, `outcome_id`,
and `verification_id` — direct references, never copies. Memory
content (`memory_content`/`rationale`/`title`) is read live off the
`OrganizationalMemory` row itself at composition time; outcome/
verification content is never duplicated onto a second table. There is
no persisted "integration" record at all (see §17).

## 13. Decision traceability

`GET /intelligence/decisions/{decision_id}/memory-context` reconstructs
which memories were eligible and applicable to the exact context a
specific `IntelligenceDecision` was made against — using only fields
that decision already stored at creation time (`scope`, `site_id`,
`intelligence_as_of`), never a new column on `IntelligenceDecision` and
never a redesign of M34. `project_id` is not part of this
reconstruction, since `IntelligenceDecision` does not itself carry one
— an honest, documented limitation, not a fabricated capability.

**A decision's own memory-context can never include a memory produced
by its own resulting outcome.** Causally, `DECIDE -> INTERVENE ->
OUTCOME -> VERIFY -> LEARNING CANDIDATE -> MEMORY` means any memory
downstream of one decision is, by construction, created *after* that
decision's own `intelligence_as_of` — so it is correctly excluded from
that same decision's reconstructed context. A *later* decision's
context can, correctly, include an earlier decision's resulting memory.
Both directions are tested.

## 14. Current vs. historical intelligence

`GET /intelligence/memory-context`/`GET /intelligence/sites/{id}/
memory-context` with no `as_of` supplied answer "what is applicable
right now" (defaults to `utcnow()`). The identical functions, given an
explicit historical `as_of`, answer "what was applicable at that
instant" — reconstructed from the same immutable rows, never a second
code path. `GET /intelligence/decisions/{id}/memory-context` is always
historical by construction (it uses the decision's own stored
`intelligence_as_of`, whatever moment that was).

## 15. What M41 does NOT change

Confirmed by static, automated tests
(`tests/test_memory_integration_service.py`):

- No ML model training or retraining.
- No model parameter or coefficient mutation.
- No threshold mutation.
- No risk-formula or prediction-rule mutation.
- No ontology mutation (`OntologyConcept` is never referenced).
- No terminology mutation (`TerminologyMappingDecision` is never
  referenced).
- No automatic learning-candidate acceptance.
- No automatic organizational-memory creation — `create_organizational_
  memory()` is never referenced by this module at all.
- No automatic memory governance (activation/retraction) — `record_
  memory_governance_decision()` is never referenced either.
- No database write of any kind — `app.intelligence.memory_
  integration` calls no `db.add()`/`db.flush()`/`db.commit()`
  anywhere (AST-verified, not merely grepped, since the module's own
  docstring legitimately discusses these calls in prose).

## 16. Why M41 is not autonomous machine learning

M41 changes what a caller can *read* — a labeled, traceable list of
applicable governed memories — never what SIE's prediction/risk/
anomaly/trend machinery *computes*. `compute_enterprise_intelligence()`,
`compose_field_intelligence_context()`, every model, every threshold,
every rule remain byte-for-byte unmodified by this milestone. A human
(or downstream automated consumer, subject to its own separate
governance) decides what to do with the memories this milestone
surfaces; SIE itself does not act on them.

## 17. Why M41 is not generic RAG

No vector store, no embeddings, no similarity search, no LLM call
exists anywhere in this milestone (spec §12, verified by the same
static import-audit test M39/M40 already established). Applicability
is a plain structural comparison over an already-existing field
(`IntelligenceOutcome.site_id`) and an already-existing temporal
resolver — never a semantic retrieval mechanism. There is also no new
persisted "integration" or "memory influence" table: everything
`resolve_eligible_organizational_memories()` returns is deterministically
reconstructable, at read time, from rows M37-M40 already made
immutable. Persisting a second copy of that same fact would itself be
exactly the duplicate source of truth the spec (§19) warns against — so
this milestone required **no migration** (head remains `0029`).

## 18. What remains for future milestones

Explicitly deferred, not started here:

- Semantic/vector memory retrieval — only introduced later if
  deterministic structured applicability proves insufficient.
- Memory effectiveness measurement (did applying this memory actually
  help?).
- Any mechanism that lets SIE *act* on a memory's applicability —
  adjusting a threshold, a risk formula, a prediction, an ontology
  term, or a control recommendation.
- Model adaptation under governance, controlled rule/policy proposals,
  human-approved intelligence calibration, learning experiments,
  organizational-knowledge-quality evaluation — all named in the M41
  spec as *possible* future directions, none implemented here.
- Direct project attribution on `IntelligenceOutcome` itself (§7's own
  documented limitation), should a future milestone need
  `PROJECT_SITE_MATCH` without going through a site.

M41 establishes the governed bridge: organizational memory can now
inform intelligence context, explicitly, traceably, and only within
deterministic, tenant-safe, temporally correct bounds. It does not yet
decide, on SIE's own initiative, what to do with that information.
