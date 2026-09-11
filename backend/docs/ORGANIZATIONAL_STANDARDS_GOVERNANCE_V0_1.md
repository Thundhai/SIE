# SIE Organizational Standards & Governance Foundation v0.1 (SIE Milestone 43A)

## 1. What this milestone is

SIE Milestone 43A is the governance foundation that lets SIE distinguish
three separate concepts, per its own "Core principle":

> Available does not mean selected. Selected does not automatically mean
> applicable.

```
SIE KNOWLEDGE UNIVERSE           -- AVAILABLE: GoverningStandard catalogue
        |                           (GLOBAL or ORGANIZATION-scoped)
        v
ORGANIZATION GOVERNANCE          -- SELECTED: OrganizationGoverningStandard
        |                           (append-only selection/retirement log)
        v
ACTIVE GOVERNING SET             -- the resolved, current set of standards
        |                           this organization has explicitly adopted
        v
FIELD INTELLIGENCE               -- (not built here: a later milestone's
        v                           applicability reasoning consumes this)
     ATTENTION
        v
   [NEXT: M43B]
```

This milestone stops at the **Active Governing Set**. It does not
implement applicability reasoning, recommendations, or any change to
`FieldIntelligenceContext`/`Attention` — see §2 and §9.

## 2. What this milestone is not

- **Not a recommendation engine.** No AI recommendation, recommendation
  scoring, alternative recommendation, or "what should you do?" logic
  exists anywhere in this milestone.
- **Not an automatic compliance determination.** SIE never concludes an
  organization *is* compliant with a selected standard, and never infers
  that a standard governs an organization merely because SIE has that
  standard in its knowledge universe (Rule 1) or because it is regionally
  available (Rule 2).
- **Not a full regulatory compliance management system, audit management
  system, permit management system, incident management system, or
  training management system.**
- **Not a document-management replacement.** Organization-specific
  standards integrate with the *existing* `KnowledgeSource`/
  `KnowledgeDocument` ingestion architecture (§5) rather than creating a
  second document system.
- **Not a new intelligence category, predictive model, or RAG pipeline.**
  `GoverningStandard`/`OrganizationGoverningStandard` are governance
  metadata tables, not knowledge-retrieval or prediction infrastructure.
- **Not autonomous.** The LLM does not decide what standard governs an
  organization (Rule 7); every selection is the direct, explicit result
  of one `POST /organization-governing-standards` call by an authorized
  actor (Rule 8).

## 3. Available / Selected / Applicable

| Concept | Meaning | Built in M43A? |
|---|---|---|
| **Available** | SIE possesses or knows about the standard in its knowledge universe. | Yes — `GoverningStandard` catalogue. |
| **Selected** | The organization explicitly says "this is one of the standards governing our operations." | Yes — `OrganizationGoverningStandard` append-only event log. |
| **Applicable** | The selected standard is relevant to a specific region/industry/site/activity/hazard/operational question. | **No** — this milestone establishes the data (regions/industry_sectors on the catalogue entry, organization profile fields already on `Organization`/`Site`) a later milestone's applicability-reasoning layer will consume. No applicability claim is made anywhere in this milestone. |

## 4. Catalogue: `GoverningStandard`

Mirrors `KnowledgeSource`'s own GLOBAL/ORGANIZATION scoping exactly (same
`ScopeType` enum, reused verbatim — not a parallel vocabulary), with a
database `CHECK` constraint making the GLOBAL/ORGANIZATION <->
`organization_id` relationship structurally impossible to get wrong:

- **GLOBAL** (`organization_id IS NULL`) — SIE's own knowledge of ISO
  45001, OSHA requirements, IOGP guidance, ICMM frameworks, API
  standards, applicable national/regional requirements, etc. These are
  examples, not an exhaustive or hardcoded list — new GLOBAL entries are
  added via `app/services/governing_standard_service.py::
  seed_global_catalogue()`, an idempotent (matched by name) loader
  invoked directly by whoever operates the platform's own knowledge
  universe. There is no public API write path for a GLOBAL entry (§8).
- **ORGANIZATION** (`organization_id` set) — an organization's own
  standard (e.g. "ABC Energy HSE Standard 2026"), created via
  `POST /governing-standards`.

Fields (per spec §1): `name`, `short_description`, `issuing_organization`,
`standard_type` (a `GoverningStandardType` enum — `REGULATORY`,
`INTERNATIONAL_STANDARD`, `INDUSTRY_GUIDANCE`, `MANAGEMENT_FRAMEWORK`,
`CLIENT_STANDARD`, `ORGANIZATION_SPECIFIC`, `OTHER` — `OTHER` exists so
the catalogue is never blocked on a taxonomy gap), `regions`/
`industry_sectors` (JSON lists — an honestly empty list is never treated
as "applies everywhere," Rule 2), `version`, `publication_date`,
`effective_date`, `verification_status` (reuses `KnowledgeSource`'s own
`VerificationStatus` vocabulary — `PENDING`/`UNDER_REVIEW`/`VERIFIED`/
`REJECTED`/`EXPIRED`/`SUPERSEDED`), `knowledge_source_id` (optional
reference to the underlying `KnowledgeSource`, §5), and `is_active`.

## 5. Organization-specific standards integrate with existing knowledge architecture

```
Organization Standard (GoverningStandard, scope_type=ORGANIZATION)
        |  knowledge_source_id
        v
Knowledge Source (KnowledgeSource, scope_type=ORGANIZATION)
        |
        v
Document (KnowledgeDocument, via POST /knowledge/sources/{id}/documents)
        |
        v
Knowledge Processing / Retrieval  -- unchanged, existing M4/M21 architecture
```

`create_organization_standard()` validates that `knowledge_source_id`,
when supplied, already exists and belongs to the *same* organization
(422 otherwise) — an organization's own standard can never point at
another organization's knowledge, and never at a GLOBAL source (that
would blur GLOBAL/ORGANIZATION knowledge, which Rule 6 forbids). No new
ingestion pipeline, chunking logic, or retrieval mechanism was built —
the existing `POST /knowledge/sources` + `POST /knowledge/sources/{id}/
documents` path is the *only* way an organization's standard document
enters the system.

## 6. Selection: `OrganizationGoverningStandard` (many-to-many, append-only)

**Not** `organization.selected_standard_id` (spec's own explicit
prohibition) — a real many-to-many relationship:

```
Organization
     |
     +-- Governing Standard A (SELECTED)
     +-- Governing Standard B (SELECTED)
     +-- Governing Standard C (RETIRED)
     +-- Organization-specific Standard (SELECTED)
```

Modeled as an **append-only event log**, mirroring
`OrganizationalMemoryGovernanceDecision`'s (SIE Milestone 40) established
shape exactly: one row per SELECTED or RETIRED *event*, never an
in-place status flip. This is what makes full auditability (§8) a
property of the schema itself:

> Organization X selected Standard Y at time Z through actor A — and
> similarly when retired.

The *current* governing state for one (organization, standard) pair is
always **resolved live** — the most recent row by `decided_at DESC, id
DESC` — via `resolve_current_selection()`, never stored as a mutable
column. The **Active Governing Set** (§7) is every standard whose
resolved current state is `SELECTED`.

Each event carries: `organization_id`, `standard_id`, `status`
(`SELECTED`/`RETIRED`), `effective_date` (optional), `retirement_date`
(optional, only meaningful on a `RETIRED` row), `rationale` (optional),
`decided_at` (server-derived), and the actor (`configured_by_user_id`/
`configured_by_api_client_id`, exactly one set) + `request_id`.

**Duplicate selection is prevented, without violating append-only.**
`select_governing_standard()` checks the resolved current state first:
if already `SELECTED`, the existing event is returned unchanged
(`created=False`) rather than inserting a redundant row. Re-selecting a
*previously retired* standard **does** create a new event — that is a
genuine, distinct governance action (re-adoption), not a duplicate.

**Retiring** is `POST /organization-governing-standards/{standard_id}/
retire` — a new append-only `RETIRED` event, never a literal row
deletion (mirrors every other governance-decision write path in this
codebase: there is no `PUT`/`PATCH`/`DELETE` on this table).

## 7. The Active Governing Set

`list_active_governing_standards()` is the one function a later
milestone calls to answer:

> What governing standards are active for this organization?

An organization with no selections at all returns an empty list — a
**valid, non-error state** (Rule 5: no selected standard does not
disable SIE intelligence). Nothing defaults to a fabricated "baseline"
standard set; the absence is explicit, never silently inferred.

## 8. Authorization and tenancy

Two new permissions (`app/services/permissions.py`), checked against the
existing vocabulary first: `GOVERNANCE_READ`/`GOVERNANCE_MANAGE` already
exist but are specifically the ML *model* governance permissions
(`app/api/v1/model_governance.py`'s approval/registry workflow) —
reusing them here would silently conflate two unrelated trust
boundaries. `STANDARDS_READ` (granted to every role, mirroring
`ORGANIZATION_READ`) and `STANDARDS_MANAGE` (granted to `ORG_ADMIN`/
`HSE_MANAGER`, mirroring `SITE_MANAGE`/`PROJECT_MANAGE`) are genuinely
new capabilities instead.

Tenant resolution reuses the existing M38/M39/M40 architecture verbatim
— every handler resolves its operative `organization_id` through
`app.api.deps_context.resolve_authorized_organization_id()`. An
organization may select a `GLOBAL` standard or its own `ORGANIZATION`-
scoped standard — **never** another organization's own standard
(`resolve_governing_standard_reference()` 404s otherwise, enforced at
the service layer since a `GLOBAL` standard has no `organization_id` to
compose a cross-table database constraint against — the identical
discipline `KnowledgeDocument`'s own tenant safety already uses). Every
selection/retirement is audited (`AuditAction.GOVERNING_STANDARD_
SELECTED`/`GOVERNING_STANDARD_RETIRED`) via the existing `audit_service`
— no parallel audit system.

## 9. API

```
GET    /governing-standards                                   -- available
POST   /governing-standards                                   -- add an org-specific standard
GET    /governing-standards/{standard_id}
GET    /organization-governing-standards                       -- the Active Governing Set
POST   /organization-governing-standards                       -- select
POST   /organization-governing-standards/{standard_id}/retire  -- retire
GET    /organization-governing-standards/history                -- the raw audit trail
```

Filtering on the catalogue GET is limited to `region`/`industry`/
`standard_type`/`is_active` — no speculative filtering beyond what the
onboarding flow (§10) actually needs.

## 10. Onboarding / configuration experience

```
Organization Setup -> Country/Regions -> Industry/Sector
    -> Available Standards -> Select Governing Standards
        -> Add Organization Standard (optional) -> Review -> Complete
```

Not a hard blocker: an organization may complete setup with zero
selected standards (§7, Rule 5). `Organization.country`/`.industry` and
`Site` already carry the organization-profile context this milestone
needs — no duplicate organization/site model was introduced (spec §5's
own "do not create unnecessary duplication").

## 11. Frontend boundary

This milestone is backend-only. No onboarding/configuration wizard
exists yet in the mounted SIE frontend to extend (confirmed by
inspection: the router has no `/onboarding` or `/settings` route), so
building one here would be net-new product surface beyond "the minimum
UX necessary" the spec's own §14 asks for — deferred to a milestone that
can design it deliberately, rather than bolted on as a side effect of
this governance foundation. No new top-level navigation section
("Standards"/"Compliance"/"Regulations") was added, per the spec's own
explicit instruction.

## 12. Relationship to M43B (next)

```
SIE KNOWLEDGE UNIVERSE -> ORGANIZATION GOVERNANCE -> ACTIVE GOVERNING SET
    -> FIELD INTELLIGENCE -> ATTENTION -> [NEXT: M43B]
        -> EVIDENCE + SUFFICIENCY -> GOVERNED REASONING -> RECOMMENDATION
```

M43A stops at the Active Governing Set. It does **not** wire
`GoverningStandard`/`OrganizationGoverningStandard` into
`FieldIntelligenceContext`, `Attention`, or any recommendation. It does
**not** reuse `evaluate_sufficiency()` (the RAG question-answering
evidence-sufficiency function) as a recommendation-sufficiency mechanism
— that remains a distinct concept for a future milestone to build,
consuming the governed context this milestone establishes.
