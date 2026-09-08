# SIE Operational Scope Foundation v0.1 (SIE Milestone 35)

Establishes a durable organizational and operational scope foundation
so SIE's intelligence layer can distinguish between organization-wide
context, physical/operational sites, and projects operating within or
across sites — **identity and relationships only**. SIE remains an
intelligence layer, not a project-management system: this milestone
introduces no task list, schedule, budget, contractor, document,
permit, or workflow functionality, and no new ML/predictive/LLM
functionality.

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

Reasoning:

1. **Every one of those already carries (or resolves through) a
   `site_id`.** `SafetyEvent`/`SafetyAction`/`RiskAssessment` all have
   their own `site_id`; `IntelligenceDecision` denormalizes an
   `AttentionItem`, which itself derives from the same site-scoped
   computation. Project membership of a site is fully recoverable at
   query time by joining through `ProjectSite` — there is nothing a
   direct `project_id` column would let a caller compute that a
   `site_id` -> `ProjectSite` join cannot already answer.
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
```

No project-management UI, no task/schedule/budget endpoints. Every
route reuses the existing `RequestContext`/`require_context_permission()`
authorization dependency, the authorize-then-trust `organization_id`
query-parameter convention, and the existing 404-not-403 tenant-isolation
rule — no new authorization mechanism. `Permission.PROJECT_READ`/
`PROJECT_MANAGE` (new) are granted to the same roles as their existing
`SITE_READ`/`SITE_MANAGE` counterparts, since `Project` is an
operational-scope entity of the same shape as `Site`.
