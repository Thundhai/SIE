# SIE Actions / Intervention Domain

**SIE Milestone 17: Actions & Intervention Foundation v0.1.** The first
governed backend domain for organizations to create, assign, track,
update, progress, and close safety-related actions. This document
covers the data model, status lifecycle, permissions, tenant isolation,
provenance, audit/history, idempotency, and API surface this milestone
built. It does not cover the Events/auth/CORS surface built the previous
milestone — see `docs/ENTERPRISE_API.md` for that.

## 1. Scope and intent

The intended, longer-term lifecycle this milestone is the foundation
for:

```
Safety Event -> Human Review/Decision -> Action -> Progress -> Closure
                                                              -> Evidence/Effectiveness Verification
```

This milestone builds the **Action** stage and its governance —
persistence, lifecycle, permissions, tenant isolation, audit/history,
idempotency, and a REST API. It deliberately does **not** build:

- An AI remediation feature. SIE never autonomously creates, assigns,
  escalates, closes, or claims completion of an action. Every write in
  `app/api/v1/actions.py` is a deliberate, separately authorized call by
  a human or an already-authorized machine integration — see §12 "No
  autonomous AI" below.
- Effectiveness verification, notifications, escalation scheduling, a
  workflow/approval engine, attachments/evidence upload, recurring
  actions, or action templates. See §13 "Non-goals" below — every one of
  these was explicitly out of scope for this milestone and nothing here
  simulates them.
- An Actions frontend. The `Actions` navigation item remains disabled;
  no frontend code was touched beyond what already existed. The frontend
  is deliberately left for a future milestone, after this backend API is
  independently audited.

## 2. Data model

### `SafetyAction` (`app/models/safety_action.py`)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `organization_id` | UUID, required | Every action belongs to exactly one organization — no GLOBAL action. |
| `site_id` | UUID, nullable | FK to `sites.id`, `ON DELETE SET NULL`. Validated at write time to belong to the same organization (see §5). |
| `source_event_id` | UUID, nullable | FK to `safety_events.id`, `ON DELETE SET NULL`. The optional `SafetyEvent` this action originated from. Validated at write time (§5). |
| `title` | string, required, ≤255 chars | |
| `description` | text, nullable, ≤5000 chars | |
| `action_type` | governed enum, required | `CORRECTIVE` / `PREVENTIVE` / `INVESTIGATION` / `FOLLOW_UP` / `CONTROL_IMPROVEMENT` / `OTHER` |
| `priority` | governed enum, required | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` (default `MEDIUM`) |
| `status` | governed enum, required | `OPEN` / `IN_PROGRESS` / `BLOCKED` / `COMPLETED` / `CANCELLED` (default `OPEN`) — see §3. |
| `owner_user_id` | UUID, nullable | FK to `users.id`, `ON DELETE SET NULL`. Validated at write time to be an *active* member of the same organization (§5). |
| `due_date` | timestamp, nullable | |
| `created_by_user_id` / `created_by_api_client_id` | UUID, nullable | Exactly one is set, mirroring which kind of caller (human/machine) created the row. |
| `created_at` / `updated_at` | timestamp | |
| `completed_at` / `cancelled_at` | timestamp, nullable | Set only by the status-transition endpoint, never accepted as client input (§3, §11). |
| `external_reference` | string, nullable, ≤255 chars | Caller-supplied external system reference (e.g. a CMMS work order id) — a pass-through provenance field, like `SafetyEvent.correlation_id`. |
| `attributes` | JSON/JSONB, required (default `{}`) | Bounded to 8KB serialized (`app/schemas/actions.py`) — domain-specific structured data without forcing a migration for every new field. |

### `SafetyActionHistory` (`app/models/safety_action_history.py`)

An immutable, append-only, tenant-scoped record of what happened to one
action. `id`, `action_id`, `organization_id`, `change_type`
(`CREATED`/`UPDATED`/`ASSIGNED`/`STATUS_CHANGED`), `from_status` /
`to_status` (nullable, plain strings), `changed_by_user_id` /
`changed_by_api_client_id`, `request_id`, `comment`, `created_at`. No
route ever issues an `UPDATE`/`DELETE` against this table —
`app/services/safety_action_service.py::record_history()` is the one
write path, called once per material change.

**Distinct from, and complementary to, `AuditLog`.** `SafetyActionHistory`
answers "what happened to *this action*" (domain-scoped, one action's
own trail); `AuditLog` is the platform-wide security/administrative log
every other milestone already writes to. Both are written from the same
data, in the same call — see `app/services/safety_action_service.py`'s
own docstring.

**No history read endpoint in this milestone.** The milestone's own API
list (§11) names five endpoints, none a history reader. History is fully
implemented, written, and tenant-scoped — verified directly at the
service/database layer in this milestone's own tests
(`tests/test_actions_api.py`'s HISTORY section,
`tests/test_actions_tenant_isolation.py`'s item 9) — but exposing it over
HTTP is left to a future milestone rather than invented here.

## 3. Status lifecycle

```
        ┌────────────┐
   ┌───▶│ IN_PROGRESS│──┐
   │    └────────────┘  │
   │        ▲   │        │
┌────┐      │   ▼        ▼
│OPEN│──────┘ ┌────────┐  ┌───────────┐   ┌───────────┐
│    │───────▶│ BLOCKED│─▶│ COMPLETED │   │ CANCELLED │
└────┘        └────────┘  └───────────┘   └───────────┘
   │                              ▲             ▲
   └──────────────────────────────┴─────────────┘
```

Allowed transitions (`app/models/safety_action_enums.py::
_ALLOWED_TRANSITIONS`), verbatim from the milestone spec:

| From \ To | IN_PROGRESS | BLOCKED | COMPLETED | CANCELLED |
|---|---|---|---|---|
| **OPEN** | ✅ | ✅ | ✅ | ✅ |
| **IN_PROGRESS** | — | ✅ | ✅ | ✅ |
| **BLOCKED** | ✅ | — | ✅ | ✅ |
| **COMPLETED** | ❌ | ❌ | ❌ | ❌ (terminal) |
| **CANCELLED** | ❌ | ❌ | ❌ | ❌ (terminal) |

`COMPLETED` and `CANCELLED` are terminal — nothing transitions out of
either. An invalid transition (including any transition attempted from
a terminal state) returns `422` with a clear message; the row is left
completely unchanged. `completed_at`/`cancelled_at` are set by the
server, only on the matching valid transition — never accepted as
client input on create or `PATCH` (see `app/schemas/actions.py`'s own
docstring — neither field exists on either write schema).

## 4. Permissions

Extends the existing `Permission` vocabulary
(`app/services/permissions.py`) rather than inventing a parallel one.
`INTERVENTION_READ`/`INTERVENTION_MANAGE` already existed in that file
— reserved, but unused by any route until this milestone — so they are
reused as `SAFETY_ACTIONS_READ`/`SAFETY_ACTIONS_WRITE` rather than added
a second time under a new name. Only the two genuinely new capabilities
get new enum members:

| Milestone capability | `Permission` | Required for |
|---|---|---|
| `SAFETY_ACTIONS_READ` | `INTERVENTION_READ` (existing) | `GET /actions`, `GET /actions/{id}` |
| `SAFETY_ACTIONS_WRITE` | `INTERVENTION_MANAGE` (existing) | `POST /actions`, `PATCH /actions/{id}`, and any status transition that is *not* into a terminal state |
| `SAFETY_ACTIONS_ASSIGN` | `INTERVENTION_ASSIGN` (**new**) | Setting or changing `owner_user_id`, at create or via `PATCH` — required *in addition to* WRITE |
| `SAFETY_ACTIONS_CLOSE` | `INTERVENTION_CLOSE` (**new**) | A status transition *into* `COMPLETED` or `CANCELLED` — required *instead of* WRITE for that one call |

Default role grants (`ROLE_PERMISSIONS`): `ORG_ADMIN` gets everything
(as it does for every permission). `HSE_MANAGER` gets all four —
`INTERVENTION_READ`/`_MANAGE` already assigned to that role from before
this milestone, `_ASSIGN`/`_CLOSE` added alongside them (same role,
same reasoning). `HSE_ANALYST`, `HSE_USER`, and `VIEWER` keep the
`INTERVENTION_READ` they already had (unchanged) and get none of the
write/assign/close capabilities — a deliberately conservative default
this milestone did not have grounds to widen on its own judgment. A
machine client gets exactly the scopes granted to its credential
(`app/api/v1/api_clients.py`), same as every other permission.

**Authorization uses the existing `RequestContext`/`authorize_context()`
pipeline unchanged** — no new authorization logic, no role-to-permission
matching duplicated in `app/api/v1/actions.py` (that file only ever
calls the shared `authorize_context()`, the same function every other
route in this codebase calls). Machine clients remain pinned to their
authenticated organization (`app/api/deps_context.py`'s existing
"machine-organization-pinning" rule) — a Bearer-credentialed caller can
never reach a different organization's actions, however broad its
scopes.

## 5. Tenant isolation

The milestone's own primary hard acceptance requirement
(`tests/test_actions_tenant_isolation.py` walks its numbered checklist
directly). Every query in `app/api/v1/actions.py` filters on
`SafetyAction.organization_id == organization_id` — the value
`authorize_context()` already authorized the caller for, never a
path/body-supplied value trusted on its own. `GET`/`PATCH`/status
additionally fold `organization_id` into the *same* `WHERE` clause as
`action_id`: a valid id belonging to a different organization is
indistinguishable from a nonexistent one — always `404`, never a
distinguishing `403` that would leak existence.

**Three more reference kinds get the identical treatment**
(`app/services/safety_action_service.py`):

- `site_id` — must belong to the same organization, or `404
  "site_id not found in this organization."`
- `source_event_id` — must belong to the same organization, or `404
  "source_event_id not found in this organization."`
- `owner_user_id` — must have an *active* `OrganizationMembership` in
  the same organization (`membership_service.get_active_membership()`,
  the exact check `authorization_service`/`tenant_context` already rely
  on), or `404 "owner_user_id not found in this organization."`

None of these ever returns a `403` that would disclose a foreign
record's existence — always the same `404` as "doesn't exist at all."

## 6. Provenance

`source_event_id` is optional; when supplied, it is verified to exist
and belong to the caller's organization before the action is created
(§5). The relationship is preserved explicitly (a real foreign key,
returned as `source_event_id` on every read) — never fabricated, and
never silently dropped. An action with no `source_event_id` simply has
none; nothing invents one.

## 7. Audit and history

Every material operation writes **both** an `AuditLog` row
(`app/services/audit_service.py` — `SAFETY_ACTION_CREATED` /
`_UPDATED` / `_ASSIGNED` / `_STATUS_CHANGED`) and a
`SafetyActionHistory` row (§2 above). Neither ever logs a secret or an
API client secret — the same guarantee `AuditLog` already provides
platform-wide, unchanged. `PATCH` writes exactly one history/audit
entry per call: `ASSIGNED` if `owner_user_id` was among the changed
fields (even if other fields changed too — assignment is treated as the
most significant change when both occur together), `UPDATED` otherwise;
an empty/no-op `PATCH` (nothing actually different from the stored row)
writes neither.

## 8. Idempotency

`POST /actions` accepts the existing `Idempotency-Key` header
mechanism (`app/core/idempotency.py`) unchanged — no second idempotency
system. Same authenticated caller + same key + same request body
replays the original `201` response without creating a duplicate row;
same key with a materially different body is rejected `409
IDEMPOTENCY_CONFLICT`. `PATCH`/status-transition do not accept an
`Idempotency-Key` — the milestone spec's own idempotency requirement
(§14) is scoped to "machine-created actions," i.e. creation.

## 9. API

All under `/api/v1/actions`, organization identity always from
`organization_id` (a required query parameter resolved through
`require_context_permission`/`authorize_context`) — **never** trusted
from the request body.

### `POST /actions`
Body: `title` (required), `description`, `action_type` (required),
`priority` (default `MEDIUM`), `owner_user_id`, `site_id`, `due_date`,
`source_event_id`, `external_reference`, `attributes`. `201` with the
created action. `Idempotency-Key` header supported (§8).

### `GET /actions`
Deterministic pagination (`page`/`page_size`, `created_at DESC, id DESC`).
Filters: `status`, `priority`, `owner_user_id`, `site_id`,
`source_event_id`, `action_type`, `due_date_from`/`due_date_to`,
`search` (title/description/external_reference, parameterized `ILIKE`).
Response: `{ items, total, page, page_size }`.

### `GET /actions/{action_id}`
`404` for a nonexistent action or one belonging to another organization
(§5) — identically.

### `PATCH /actions/{action_id}`
Body (all optional; `extra="forbid"` — any other field is a `422`):
`title`, `description`, `action_type`, `priority`, `owner_user_id`,
`site_id`, `due_date`, `external_reference`, `attributes`. **Never**
`organization_id`, `status`, `created_at`/`completed_at`/`cancelled_at`,
creator ids, or `source_event_id` (provenance is set once, at creation,
and not rewritten by `PATCH`). A field omitted from the body is left
unchanged; a field explicitly sent `null` clears it (every field here
is nullable except `title`, which rejects an explicit `null`).

### `POST /actions/{action_id}/status`
Body: `status` (required, a real `ActionStatus`), `comment` (optional).
Validates the transition matrix (§3) server-side; `422` on an invalid
transition, with the row left unchanged.

## 10. Machine integration

Identical to every other machine-capable route in this codebase: `POST
/actions` with `Authorization: Bearer <client_id>:<secret>` and scopes
including `intervention:manage` (and `intervention:assign` if the
request sets `owner_user_id`) creates an action attributed to
`created_by_api_client_id`. A machine client is pinned to its own
`organization_id` at authentication time — it can never reach, or even
learn whether an action exists in, a different organization (§5).

## 11. Closure semantics — read this before assuming more than it says

**`COMPLETED` means:** "the action has been marked completed by an
authorized actor." It does **not** mean, and must never be represented
as meaning: "SIE has independently verified that the hazard has been
eliminated." There is no effectiveness-verification mechanism in this
milestone — `completed_at` records when an authorized actor said "done,"
nothing more. A future milestone (per the intended longer-term lifecycle
in §1) may add real evidence/effectiveness verification on top of this;
this one does not claim it.

## 12. No autonomous AI

Nothing in this milestone: generates an action and persists it
automatically; creates a corrective action from a prediction
automatically; assigns an owner automatically; escalates an action
automatically; closes an action automatically; claims risk mitigation
or hazard elimination; makes a causal claim; or wires a predictive
signal directly to action creation. Every `SafetyAction` row, every
status transition, and every assignment in this milestone is the direct
result of one explicit, authorized API call — traceable to exactly one
human or machine caller via `created_by_*`/`changed_by_*` and the
`AuditLog`/`SafetyActionHistory` rows it produced. A future milestone
may let intelligence *suggest* an action; a human (or an already-
authorized integration acting on a human's behalf) remains the
governance boundary that actually creates one.

## 13. Non-goals (this milestone)

Deliberately not built, per the milestone's own "do not over-engineer"
instruction: a workflow/approval engine, an event bus, notification
infrastructure, background workers, AI agents, complex action templates,
CAPA workflow, effectiveness scoring, attachments/evidence upload,
recurring actions, or an escalation scheduler. None of these is
simulated, stubbed, or partially implemented — they simply do not exist
in this codebase yet.

## 14. Known limitations

- No HTTP read endpoint for `SafetyActionHistory` (§2) — implemented and
  tested at the service/database layer only.
- No Actions frontend — the `Actions` navigation item remains disabled;
  this is deliberate (§1), not an oversight.
- `PATCH` cannot change `source_event_id` after creation — provenance is
  set once. If a future milestone needs to correct a mis-attributed
  source event, that is new, explicit scope, not implied by this one.
- The default role grants for `SAFETY_ACTIONS_ASSIGN`/`_CLOSE` (§4) are
  a conservative starting point (`HSE_MANAGER`/`ORG_ADMIN` only) — a
  future milestone may widen them with real product input; this
  milestone did not invent a broader policy on its own judgment.
