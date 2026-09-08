# SIE Operational Scope Foundation v0.1 (SIE Milestone 35, corrected by SIE Milestone 35A)

Establishes a durable organizational and operational scope foundation
so SIE's intelligence layer can distinguish between organization-wide
context, physical/operational sites, and projects operating within or
across sites — **identity and relationships only**. SIE remains an
intelligence layer, not a project-management system: this milestone
introduces no task list, schedule, budget, contractor, document,
permit, or workflow functionality, and no new ML/predictive/LLM
functionality.

**This document records both milestones as they actually happened,
including M35's own mistaken claim and M35A's correction of it** — see
§9 for the full account. The short version: §3 point 1 below claims
project membership of a site is "fully recoverable" via `ProjectSite`.
That claim is **false** whenever a site hosts more than one project (a
case M35 itself explicitly allows — §2), because `ProjectSite` proves
only "this project operates at this site," never "this specific record
belongs to this project." §9 explains the fix: a new, narrow,
explicit `SafetyEvent.attributed_project_id` relationship — read §9
before relying on anything §3–§4 say about project attribution.

## 1. Canonical scope hierarchy

```
Organization
   |
   +-- Sites            (existing, unchanged -- app/models/site.py)
   |
   +-- Projects          (new, this milestone -- app/models/project.py)
          |
          +-- ProjectSite  (new -- many-to-many with Site;
                             app/models/project_site.py)
```

| Scope level | Meaning | Identity |
|---|---|---|
| **Organization-level** | Every fact scoped to the whole tenant, unfiltered by site or project. | `organization_id` |
| **Site-level** | Facts scoped to one physical/operational location. | `Site.id` |
| **Project-level** | Facts identified as concerning one `Project`, whose own operational footprint is the set of sites it is currently linked to via `ProjectSite`. | `Project.id` |
| **Multi-site project-level** | The general case of project-level scope: a project spanning more than one site. **Named here for completeness; not implemented as a computation scope in M35** — see §4. | `Project.id` + its current `ProjectSite.site_id` set |

`Site` already is this codebase's physical/operational location entity
— every event/action/risk-assessment/prediction in this codebase already
scopes against `Site.id` (`SafetyEvent.site_id`, `SafetyAction.site_id`,
`RiskAssessment.site_id`, `Prediction.entity_id`, ...). No repository
evidence demonstrates `Site` cannot serve that role for `Project` too,
so this milestone introduces **no second, competing `Location` entity**.

## 2. Why a many-to-many `Project` <-> `Site` relationship

A project may span multiple sites (a regional maintenance program
touching several facilities), and a site may host multiple concurrent
projects. A single `site_id` foreign key on `Project` cannot represent
either direction, so `ProjectSite` (`app/models/project_site.py`) is an
explicit join table: `(organization_id, project_id, site_id)` unique,
`ON DELETE CASCADE` on both `project_id` and `site_id` (the row's whole
meaning is the relationship itself — unlike, say, `SafetyAction.site_id`,
which is `SET NULL` because the action must survive its site being
removed).

**Tenant integrity is enforced at the service layer**
(`app/services/project_site_service.py::link_project_site()`): both
`project_id` and `site_id` are resolved scoped to the caller's own
authorized `organization_id` *before* any row is created — a project
belonging to Organization A can never be linked to a site belonging to
Organization B; either reference is a `404`, never a `403`, mirroring
every other cross-tenant reference check in this codebase.

## 3. The guardrail: why no `project_id` was added to any other table

**Explicit decision, per the milestone's own guardrail** ("do not accept
the simplistic solution of adding a `project_id` column to Events,
Actions, Findings, Assessments and Decisions"): none of `SafetyEvent`,
`SafetyAction`, `RiskAssessment`, `RiskAssessmentFinding`, or
`IntelligenceDecision` gained a new column in this milestone.

Reasoning (as originally written in M35 — **point 1 is corrected by
M35A; see §9**):

1. ~~**Every one of those already carries (or resolves through) a
   `site_id`.** `SafetyEvent`/`SafetyAction`/`RiskAssessment` all have
   their own `site_id`; `IntelligenceDecision` denormalizes an
   `AttentionItem`, which itself derives from the same site-scoped
   computation. Project membership of a site is fully recoverable at
   query time by joining through `ProjectSite` — there is nothing a
   direct `project_id` column would let a caller compute that a
   `site_id` -> `ProjectSite` join cannot already answer.**~~ **This is
   false whenever a site hosts more than one project.** `site_id` ->
   `ProjectSite` answers "which projects operate at this site" (a
   *candidate set*), never "which one of them this specific record
   belongs to" (an *attribution*) — the two are only the same thing
   when a site hosts exactly one project, which §2 explicitly does not
   guarantee. See §9 for the correction: `SafetyEvent` gained a narrow,
   explicit, nullable `attributed_project_id` relationship for exactly
   this reason. `SafetyAction`/`RiskAssessment`/`RiskAssessmentFinding`/
   `IntelligenceDecision` were re-evaluated under M35A and still gained
   no column — §9 documents that decision for each individually, not
   merely by extension of this (incorrect) blanket reasoning.
2. **No concrete, existing intelligence computation needs `project_id`
   directly.** Every M22–M34 computation (indicators, trend, anomaly,
   recurrence, risk score, Field Intelligence Context, Attention,
   Intelligence Decisions) is already organization- or site-scoped.
   Adding a column nothing reads is exactly the "unnecessary coupling"
   the milestone's own guardrail warns against.
3. **Point-in-time integrity (item 7).** A row's `project_id`, once
   written, would either need its own temporal snapshot to stay
   historically correct as project/site membership changes over time,
   or would silently misrepresent history the moment that membership
   changed. `ProjectSite` itself carries no such snapshot (see §5) —
   duplicating an even-less-historically-safe pointer onto five more
   tables is a cost this milestone's own minimum-coupling instruction
   does not justify paying.
4. **A second, easily-inconsistent source of truth.** If both a
   `project_id` column and `ProjectSite` existed, a caller could
   observe the two disagree (an event's `project_id` pointing at a
   project no longer linked to that event's own site). One source of
   truth — `ProjectSite`, resolved through `site_id` at query time — is
   the only architecture this milestone introduces.

`SafetyEvent.project` (a free-text field from the Operational Context
domain, predating this milestone) is explicitly **not** reinterpreted as
an authoritative `Project` reference by this milestone — it remains
exactly what it always was: an unvalidated, unlinked string captured
from the source system. No migration/backfill maps it onto the new
`Project` entity (see §6).

## 4. What *is* connected to intelligence: `operational_scope` (item 10)

The one place this milestone touches intelligence output is
`FieldIntelligenceContextRead.operational_scope`
(`app/schemas/field_intelligence_context.py`,
`app/api/v1/intelligence.py`) — a purely additive, opt-in **label**:

- `GET /intelligence/context` and `GET /intelligence/sites/{site_id}/context`
  gained an optional `project_id` query parameter. Omitted (the default,
  and every pre-M35 caller's behavior): `operational_scope` is `null`,
  and the response is byte-for-byte identical to before this milestone.
- Supplied: the project is resolved (tenant-owned, or `404`); for the
  site-scoped endpoint, the given site must currently be one of the
  project's linked sites, or the request is rejected with `400` (an
  honesty check — a project label attached to an unrelated site would
  be actively misleading). The response's `operational_scope.level` is
  always exactly what `Observed`/`Deterministic`/`Predictive` actually
  computed over (`"ORGANIZATION"` or `"SITE"`) — **never `"PROJECT"`**.

**This milestone deliberately does not implement multi-site project-level
intelligence aggregation** — there is no code path that filters
events/actions/findings/predictions by "any site belonging to this
project." Implementing that correctly would mean extending
`compute_enterprise_intelligence()` (and every function it calls:
`events_as_of()`, `_actions_context()`, `_predictive_context()`, the
full M22/M23 indicator/trend/anomaly/recurrence/risk-score stack) to
accept a *list* of site ids instead of one — a change to the core
computation engine well beyond "identity and relationships only," and
explicitly not required by item 10's own instruction to "update Field
Intelligence Context only where necessary to expose operational scope."
A project is therefore always a **label** on an Organization- or
Site-scoped call, never a third computation mode, and never a new,
competing intelligence engine or source of truth. A caller that needs
per-project analytics today can call `GET /intelligence/sites/{site_id}/context`
once per site the project is linked to (via `GET /projects/{project_id}/sites`)
and combine the results client-side; true server-side multi-site
aggregation is left to a future milestone if a concrete need for it
emerges.

`Attention` (`GET /intelligence/attention`) was assessed against the
same question and deliberately left unchanged in this milestone: it
already reuses the identical site-scoping Field Intelligence Context
does, so the identical `operational_scope` label could be added the
same way — but item 10 only names Field Intelligence Context, and
extending the identical, low-risk pattern to a second endpoint is left
as a natural, minimal follow-up rather than done speculatively here.
`IntelligenceDecision` was also assessed (item 6): it already resolves
through `AttentionItem`'s own site scope at decision time, so no
additional relationship was needed there either.

## 5. Point-in-time integrity — explicit limitation (item 7)

`ProjectSite` carries **no temporal versioning** in this milestone: no
history table, no valid-from/valid-to columns, no soft-delete. Unlinking
a site is a hard delete (mirrors `RiskAssessmentFindingAction`'s own
established "unlink is a hard delete" precedent — `AuditLog` still
records the unlink event itself via `PROJECT_SITE_UNLINKED`, just not a
queryable "what was true as of instant X" reconstruction).

Concretely: `operational_scope.project.site_ids` in a Field Intelligence
Context response always reflects the project's **current** `ProjectSite`
membership at the moment of that API call — never reconstructed as of
the request's own `as_of`. A caller replaying `as_of=<six months ago>`
with `project_id` set sees *today's* site associations for that
project, not whatever they were six months ago. This is documented
directly on the response schema
(`OperationalScopeProjectRead.site_ids`'s own field description) and
exercised by
`tests/test_projects_api.py::test_operational_scope_project_site_ids_reflects_current_not_historical_membership`,
which links a second site *after* an initial historical-`as_of` context
call and confirms a repeat of that same call immediately reflects the
new membership.

If a future milestone needs true point-in-time project/site
reconstruction, it requires a dedicated history mechanism (mirroring
`RiskAssessmentHistory`'s own precedent) — deliberately not built
speculatively here, since nothing in this milestone's own requirements
demonstrates a concrete need for it yet.

`Project.name`/`code`/`status`/`description` are likewise
mutable-by-replacement with no history table — no code anywhere yet
reads a project's own field values "as of" a past instant the way
`RiskAssessment.as_of` does, so none is built speculatively.

## 6. Backward compatibility (item 11)

- Every existing `SafetyEvent`/`SafetyAction`/`RiskAssessment`/
  `RiskAssessmentFinding`/`IntelligenceDecision`/`AttentionItem` row or
  computation continues to work completely unmodified — none of those
  models or computations changed in this migration.
- `GET /intelligence/context` / `GET /intelligence/sites/{site_id}/context`
  responses are unchanged for every caller that omits the new
  `project_id` parameter (`operational_scope` is `null`).
- `SafetyEvent.project` (free text) is explicitly **not** migrated,
  backfilled, or silently reinterpreted as a `Project` reference. No
  migration in this milestone touches `safety_events` at all.

## 7. Database discipline (item 12)

Migration `0022` (`migrations/versions/0022_sie_milestone_35_organizational_operational_scope.py`)
is purely additive: two new tables (`projects`, `project_sites`) and one
new native enum type (`project_status`), introduced via
`op.create_table()` (which auto-creates the enum type as part of the
table DDL — the same established pattern migrations `0015`/`0021` use).
No existing table, column, row, or type is altered or removed. Both new
tables are reversible: `downgrade()` drops `project_sites` before
`projects` (FK order), then the `project_status` enum type.

## 8. API surface (item 9)

```
POST   /api/v1/projects                                create a project
GET    /api/v1/projects                                list projects (paginated)
GET    /api/v1/projects/{project_id}                    retrieve one project
GET    /api/v1/projects/by-site/{site_id}                reverse lookup: a site's projects
POST   /api/v1/projects/{project_id}/sites               link a site to a project
GET    /api/v1/projects/{project_id}/sites                list a project's sites
DELETE /api/v1/projects/{project_id}/sites/{site_id}      unlink a site
PUT    /api/v1/projects/{project_id}/events/{event_id}     attribute an event to a project (M35A)
DELETE /api/v1/projects/{project_id}/events/{event_id}     clear an event's project attribution (M35A)
GET    /api/v1/projects/{project_id}/events                list a project's explicitly attributed events (M35A)
```

No project-management UI, no task/schedule/budget endpoints. Every
route reuses the existing `RequestContext`/`require_context_permission()`
authorization dependency, the authorize-then-trust `organization_id`
query-parameter convention, and the existing 404-not-403 tenant-isolation
rule — no new authorization mechanism. `Permission.PROJECT_READ`/
`PROJECT_MANAGE` (new) are granted to the same roles as their existing
`SITE_READ`/`SITE_MANAGE` counterparts, since `Project` is an
operational-scope entity of the same shape as `Site`.

## 9. SIE Milestone 35A: Canonical Project Attribution Correction

### 9.1 The problem M35 missed

M35 (§3 point 1, struck through above) assumed a `SafetyEvent`'s
project membership could always be recovered from `SafetyEvent.site_id`
joined through `ProjectSite`. That assumption breaks the moment a site
hosts more than one project — a case §2 explicitly designs for:

```
Site X
  +-- Project Alpha  (linked via ProjectSite)
  +-- Project Beta   (linked via ProjectSite)

SafetyEvent E occurs at Site X.
```

From `E.site_id` + `ProjectSite` alone, SIE can only conclude "Site X
hosts Alpha and Beta" — never whether `E` itself belongs to Alpha, to
Beta, to both, or to neither. `ProjectSite` is a **candidate-set
relation** ("these projects operate here"); it is not, and was never
designed to be, an **attribution relation** ("this record belongs to
that project"). M35's own `operational_scope.project` label
inherited this flaw silently: supplying `project_id` to
`GET /intelligence/context` never filtered anything — it validated the
project/site pair and then re-labeled an unfiltered Organization- or
Site-scope result, which is not the same claim as "this is Project
Alpha's intelligence."

### 9.2 The fix: an explicit, governed attribution — not a wider guess

`SafetyEvent` gained one new nullable column,
`attributed_project_id` (migration `0023`,
`app/models/safety_event.py`), set **only** by an explicit act — never
inferred from `site_id`/`ProjectSite`:

```
PUT    /api/v1/projects/{project_id}/events/{event_id}     set the attribution (idempotent: sets the exact target state)
DELETE /api/v1/projects/{project_id}/events/{event_id}     clear it back to NULL (idempotent)
GET    /api/v1/projects/{project_id}/events                list every event explicitly attributed to this project
```

(`app/services/safety_event_project_service.py`, gated by
`Permission.PROJECT_MANAGE` for the writes, `PROJECT_READ` for the
list.) Nothing in this service, the migration, or the API layer ever
reads `ProjectSite` to *guess* an event's project — the column is
`NULL` (unattributed — the default and fully valid state) until a
caller sets it explicitly.

**Validation rule, unconditional, no historical/ingestion exception.**
When the event has a `site_id`, the project being attributed must
*currently* be one of that site's `ProjectSite` rows, or the request is
rejected `422` — attributing "Project Beta" to an event whose site only
"Project Alpha" operates at is refused, not silently accepted. An event
with no `site_id` at all has nothing to cross-check, so any project in
the same organization may be attributed. Re-attributing an
already-attributed event to a different project is a **correction**
(overwrite), not an error — an event is never attributed to two
projects at once (proven by
`tests/test_project_service.py::test_two_projects_at_the_same_site_do_not_both_claim_an_events_attribution`
and its HTTP-layer twin in `tests/test_projects_api.py`).

**No automatic reconciliation.** Unlinking a site from a project
(`DELETE .../sites/{site_id}`) does **not** retroactively clear any
event already attributed to that project — the attribution is a fact
established at a point in time
(`tests/test_project_service.py::test_unlinking_a_site_from_a_project_does_not_retroactively_clear_an_already_attributed_event`),
mirroring `ProjectSite`'s own "no point-in-time reconstruction"
limitation (§5) rather than inventing a second, inconsistent temporal
model. SIE makes no claim to reconstruct historical project/site
membership anywhere in this correction.

**`SafetyEvent.project` (free text) is untouched and stays untouched.**
The pre-existing free-text field is never read, migrated, or treated as
authoritative by `attributed_project_id` — the two remain permanently
distinct: one is unvalidated source-system text, the other is a
governed, tenant-checked, site-consistency-validated relationship.

### 9.3 SafetyAction and RiskAssessment: evaluated, neither gained a column

**`SafetyAction`** — no new column. Where an action's project context
is needed, it is derived via a real join through its own
`source_event_id -> SafetyEvent.attributed_project_id` (an
authoritative upstream relationship), proven directly by
`tests/test_project_service.py::test_safety_action_can_derive_project_context_via_its_source_event`.
Not every `SafetyAction` has a `source_event_id`, so this derivation is
partial by nature — an action with no source event has no derivable
project context, and none is fabricated for it. This correction does
not wire that derivation into any production query path (no
`SafetyAction`-listing endpoint filters by project) — it is
demonstrated only, kept narrow per this milestone's own instruction to
avoid new project-management/analytics surface area beyond the minimum
`SafetyEvent` fix.

**`RiskAssessment`** — no new column, and no derivation path was added
either. Unlike `SafetyAction`, `RiskAssessment` has no `source_event_id`
or equivalent single upstream `SafetyEvent` to derive through; its own
`site_id` remains its only geographic scope. Concluded: introducing
project attribution for `RiskAssessment` would require either a new
direct column (rejected — no concrete computation reads it, identical
reasoning to §3) or a new relationship this correction's scope does not
call for. Left for a future milestone if a concrete need emerges.

### 9.4 Field Intelligence Context: genuine filtering, not a wider label

`project_id` on `GET /intelligence/context` /
`GET /intelligence/sites/{site_id}/context` now genuinely filters —
`events_as_of()` (`app/intelligence/temporal.py`) gained an equally
optional `project_id` parameter (`SafetyEvent.attributed_project_id ==
project_id`), threaded through both of
`compute_enterprise_intelligence()`'s internal event fetches
(`app/intelligence/enterprise_intelligence_service.py`). Because
indicators, trend, concentration, recurrence, risk score, and
explanations are all pure functions computed over that same fetched
event list, filtering at that one boundary correctly cascades through
all of them with no further change. Proven by
`tests/test_projects_api.py::test_project_scoped_context_genuinely_filters_event_count_not_merely_labels_it`
(two projects at one site, disjoint attributed events, `event_count`
and `evidence_sample_event_ids` differ per `project_id` and both differ
from the unfiltered site-wide total).

**What remains unfiltered by project, and why — the response's own
`operational_scope.project.filtered` field documents this list
verbatim:**

| Not filtered | Why |
|---|---|
| `deterministic.anomalies`/`associations` | Each runs its own separate multi-period baseline query (`_available_baseline_periods`/`_bucketed_events`) independent of the shared `events_as_of()` list this correction threads `project_id` through — narrowing those too is a materially larger change than this correction's own "keep it narrow" instruction allows. |
| `predictive` | `Prediction.entity_type` is Organization/Site only — no project dimension exists in the prediction architecture at all. |
| `observed.actions`/`open_action_sample` | `SafetyAction` gained no project attribution (§9.3) — only a documented, unwired derivation path. |
| `observed.open_finding_sample` | `RiskAssessmentFinding` gained no project attribution (§9.3 — `RiskAssessment` itself has none). |

`operational_scope.level` still never becomes `"PROJECT"` — geographic
scope (`"ORGANIZATION"`/`"SITE"`, what the computation ran *over*
geographically) and project filtering (what subset of that scope's
events were counted) remain two independent, orthogonal response
dimensions, exactly as §4 originally established; §4's own claim that
a project is "always a label, never a third computation mode" is
superseded only insofar as the label now also drives genuine
event-level filtering for the fields listed above — it is still never
a third *geographic* scope.

### 9.5 Database tenant integrity for `project_sites`

M35's own §2 described a cross-tenant `ProjectSite` row as impossible
in the sense that the one write path (`link_project_site()`) validates
both ends — true, but the schema itself only had independent
single-column foreign keys, so a direct database write or a future
code path bypassing that service could still create an inconsistent
row. Migration `0023` closes that gap **at the schema level**:
`projects`/`sites` each gained `UNIQUE(id, organization_id)`, and
`project_sites.project_id`/`site_id` are now referenced via *composite*
foreign keys — `(project_id, organization_id) -> projects(id,
organization_id)` and `(site_id, organization_id) -> sites(id,
organization_id)`. Postgres itself now rejects any `project_sites` row
whose `organization_id` does not match both referenced rows' own
`organization_id` — proven against real PostgreSQL, via a raw-SQL
insert that deliberately bypasses the service layer, by
`tests/test_migrations.py::test_project_sites_composite_foreign_keys_reject_cross_tenant_rows_at_the_database_level`.

**The identical technique is deliberately not used for
`SafetyEvent.attributed_project_id`.** A composite `ON DELETE SET NULL`
foreign key nulls *every* column in the constraint together, including
`organization_id` — which is `NOT NULL` on every tenant-owned table in
this codebase. Applying the same composite technique there would make
deleting a `Project` attempt to null a referencing event's
`organization_id` too, violating that `NOT NULL` constraint and making
the `Project` undeletable instead of cleanly clearing the event's
attribution. `project_sites` avoids that conflict because both of its
foreign keys use `ON DELETE CASCADE` (the whole row is removed, never
partially nulled); `SafetyEvent.attributed_project_id` therefore keeps
a plain single-column foreign key (`ON DELETE SET NULL`) and relies on
the validated write path
(`attribute_event_to_project()`/`clear_event_project_attribution()`)
for tenant consistency instead — the one deliberate, documented
exception to this correction's database-level hardening. See
`app/models/project_site.py`'s own docstring for the complete
reasoning.

### 9.6 Tests added by this correction

- `tests/test_project_service.py`: `attribute_event_to_project()`/
  `clear_event_project_attribution()` direct service-layer coverage —
  tenant isolation, the site-consistency `422`, idempotent clearing,
  the two-projects-one-site non-attribution scenario, no-automatic-
  reconciliation-on-unlink, and the `SafetyAction` derivation proof.
- `tests/test_projects_api.py`: the same scenarios over HTTP (`403` for
  a viewer, `404` for cross-tenant event/project, `422`, idempotent
  `204` clear, `GET .../events` returning only that project's
  attributed events), plus the genuine Field Intelligence Context
  filtering test (§9.4).
- `tests/test_migrations.py`: a migration `0023` downgrade/re-upgrade
  round-trip, and the cross-tenant composite-FK rejection proof (§9.5).

### 9.7 Explicitly out of scope for this correction

No project-management features, no new ML, no outcome/learning
implementation, no `RiskAssessment`/`SafetyAction` schema change, no
`anomalies`/`associations`/`predictive` project filtering, and no
point-in-time project/site reconstruction — all unchanged from M35's
own non-goals (§6) and this correction's own explicit instruction to
stay narrow. **This last one — point-in-time reconstruction — is
exactly what SIE Milestone 35B (§10) adds, but only for `SafetyEvent`'s
own project *attribution*, never for `ProjectSite`'s site *membership***
— §5's own limitation (a project's `site_ids` always reflects today's
`ProjectSite` rows, never a historical `as_of`) is untouched by M35B
and remains true after it. See §10.5 for the precise boundary between
what is, and still is not, point-in-time correct after this milestone.

## 10. SIE Milestone 35B: Project Attribution Temporal Integrity

### 10.1 The problem M35A missed

M35A gave `SafetyEvent.attributed_project_id` — a single current-state
column — and filtered `events_as_of(project_id=...)` on that column
directly. Correct for "as of right now," silently wrong for any
historical `as_of`: an event attributed to Project Alpha on June 20,
reassigned to Project Beta on June 25, asked about ("Alpha's
intelligence as of June 23") would incorrectly read as "always Beta" —
even though the event genuinely was Alpha's as of that instant. A
single current-state column cannot answer a question about the past
once the present has changed.

### 10.2 Two options considered, and why a small history table was chosen

**Option A — a single `project_attributed_at` timestamp alongside
`attributed_project_id`.** Rejected: insufficient on its own. The
worked example above is the proof — after the June 25 reassignment,
`attributed_project_id` reads Beta and a single timestamp cannot
recover "it was Alpha before that instant, for whichever earlier
instants the caller might ask about." A single timestamp can express
*when the current value became current*, never a sequence of past
values.

**Option B — an append-only attribution history table.** Chosen. A
`SafetyEventProjectAttributionHistory` row per state transition
(`ATTRIBUTED`/`CLEARED`, `event_id`, `project_id`, `created_at`) is the
minimum structure that can answer "what was true as of instant T" for
any T, by finding the most recent qualifying row at or before T. See
`app/models/safety_event_project_attribution_history.py`'s own
docstring for the full schema and reconstruction-query rationale, and
`app/intelligence/temporal.py::events_as_of()`'s own docstring for the
SQL that does the reconstruction.

**Option C — prohibit project-filtered historical intelligence
outright.** Considered and rejected as unnecessarily regressive: M35A
had already shipped a `project_id` parameter callers could combine with
a historical `as_of`, and simply refusing that combination (rather than
answering it correctly) would be a worse outcome than the small,
narrow mechanism Option B actually required. Given where this system's
own trajectory is heading (eventual outcome/learning work that will
itself need to reason about "what did we know, attributed to which
project, at a given point in time"), building the correct mechanism now
— while it is still small — was judged preferable to deferring it.

**Why not a full bitemporal model, or a dedicated ordering/sequence
column.** Neither `RiskAssessmentHistory` nor `SafetyActionHistory` —
the two existing history tables inspected before building this one, per
this milestone's own instruction to inspect the existing architecture
first — carries a business-time column distinct from `created_at`, or
an ordering tiebreaker beyond `created_at` itself; both accept the same
microsecond-resolution-only ordering this table now also accepts (see
`app/models/safety_event_project_attribution_history.py`'s own
docstring for the full reasoning). Matching that established precedent
was judged more consistent than inventing new machinery — an
autoincrement/sequence column would be the first of its kind anywhere
in this schema (every table uses a UUID primary key).

### 10.3 Deterministic re-attribution and clearing semantics

- A history row is written only on an actual state transition.
  Attributing an event to the project it is already attributed to, or
  clearing an already-unattributed event, is a true no-op: no history
  row, no audit log entry (`attribute_event_to_project()` now returns
  `(event, changed)`, mirroring `link_project_site()`'s own
  `(link, created)` precedent).
- Re-attributing an already-attributed event to a *different* project
  is a real transition: a new `ATTRIBUTED` row, naming the new project.
  The event is never attributed to two projects "at once" — proven by
  `tests/test_project_attribution_temporal.py::test_two_projects_never_simultaneously_claim_the_same_event_at_any_instant`.
- `SafetyEvent.attributed_project_id` remains the fast, current-state
  answer every non-temporal read uses (event detail, `GET
  /projects/{id}/events`, the `DELETE` target-match check below) — this
  milestone does not remove or bypass it, it adds the one place
  (`events_as_of()`) that needs point-in-time correctness instead.

### 10.4 `DELETE` now requires the target project to match

M35A's `DELETE /projects/{project_id}/events/{event_id}` accepted any
tenant-owned `project_id` in the URL and cleared whatever was currently
attributed, regardless of whether it matched — `DELETE
/projects/{beta_id}/events/{event_id}` would silently clear an
attribution to Alpha. SIE Milestone 35B fixes this:
`clear_event_project_attribution()` now requires `project_id` to equal
`event.attributed_project_id` at the moment of the call, or raises
`404` (mirroring `unlink_project_site()`'s own "not currently
associated" 404) — including when the event is already unattributed
(there is nothing for any `project_id` to match). This is a deliberate
narrowing from M35A's "always idempotent, never an error" framing: a
second `DELETE` call now `404`s rather than silently re-succeeding. See
`app/services/safety_event_project_service.py`'s own docstring and
`tests/test_project_service.py::test_clear_event_project_attribution_requires_the_target_project_to_match_current_attribution`
/ `tests/test_projects_api.py::test_clear_event_project_attribution_over_http_rejects_a_mismatched_project`.

### 10.5 Exactly what is, and is not, point-in-time correct after this milestone

| Point-in-time correct after M35B | Still current-state only |
|---|---|
| `SafetyEvent`'s own project attribution, via `events_as_of(project_id=...)` and everything built on it (`compute_enterprise_intelligence()`'s indicators/trend/concentration/recurrence/risk/explanations, Field Intelligence Context's `observed.event_count`/`evidence_sample_event_ids`) | `ProjectSite` — a project's `site_ids` (§5) always reflects *today's* membership, never reconstructed as of `as_of`; unchanged by this milestone |
| | `deterministic.anomalies`/`associations` — separate baseline queries, not threaded with `project_id` at all (§9.4, unchanged) |
| | `observed.actions`/`open_action_sample`, `observed.open_finding_sample`, `predictive` — no project attribution mechanism exists for these at all (§9.3/§9.4, unchanged) |

### 10.6 Backfill

Migration `0024` synthesizes one `ATTRIBUTED` history row for every
`safety_events` row that already had `attributed_project_id` set before
this history table existed (necessarily written by M35A-era code), so
such a row does not silently disappear from every project-filtered
query the moment this migration lands. The synthesized row's
`created_at` uses that event's own `updated_at` — the closest available
signal, though not exact if the row was touched by something unrelated
afterward. This runs only against whatever M35A-era data exists in this
development branch; there is no real production data behind it. See
`tests/test_migrations.py::test_project_attribution_history_migration_backfills_existing_current_state_attributions`.

### 10.7 Tests added by this milestone

- `tests/test_project_attribution_temporal.py`: direct `events_as_of()`
  query-level tests, including the user's own full worked example
  (attribute Alpha June 20 → as_of June 10 excluded, June 21 included;
  reassign to Beta June 25 → Alpha as_of June 23 still included, June 26
  excluded; Beta as_of June 26 included), a cleared-attribution case, the
  live "as of now" regression check, the no-attribution-at-all
  preservation check, and the two-projects-never-simultaneous check.
- `tests/test_projects_api.py`: an end-to-end HTTP test through the real
  `GET /intelligence/context` pipeline proving the same point-in-time
  correctness (not just `events_as_of()` in isolation), plus the two new
  `DELETE`-fix tests (§10.4).
- `tests/test_project_service.py`: the no-op-attribution (`changed=False`)
  test and the two `clear_event_project_attribution()` correctness tests
  (second-call `404`, mismatched-project `404`).
- `tests/test_migrations.py`: a migration `0024` downgrade/re-upgrade
  round-trip, and the backfill proof (§10.6).

### 10.8 Explicitly out of scope for this milestone

No project-management features, no new ML, no outcome/learning
implementation, no `SafetyAction`/`RiskAssessment` schema change (§9.3
unchanged), no `anomalies`/`associations`/`predictive` project
filtering (§9.4/§10.5 unchanged), and no `ProjectSite` point-in-time
history (§5/§10.5 unchanged) — all consistent with this milestone's own
explicit instruction to keep the correction narrow.
