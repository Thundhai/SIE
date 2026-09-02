# SIE Developer Integration Guide

SIE (Safety Intelligence Engine) is an independent, multi-tenant safety
intelligence platform. It is **not** Safelytic's backend — Safelytic is
one consumer of this API, and any other authorized application
integrates the exact same way, through the same versioned REST surface
under `/api/v1`. This guide is written for a developer at a *different*
company, integrating an HSE platform, an ERP, an IoT system, or a
mobile safety app against SIE, without ever reading SIE's own source
code.

Everything below reflects the actual, running API — no endpoint is
described here that doesn't exist, and no field is described that
isn't real. The generated OpenAPI schema (`/openapi.json`, browsable at
`/docs`) is the authoritative, always-in-sync reference; this guide is
the narrative walkthrough.

## 1. Authentication

SIE has exactly two authentication mechanisms. There is no third, and
no API key format other than the one described below.

### Machine-client authentication (what your integration uses)

Every system-to-system call — ingesting events, querying analytics,
requesting predictions, searching knowledge — authenticates with a
**machine-client credential**:

```
Authorization: Bearer <client_id>:<secret>
```

`client_id` and `secret` are issued once, by an administrator of the
organization you're integrating with, via:

```
POST /api/v1/organizations/{organization_id}/api-clients
```

(This call itself requires human, administrative authentication — see
below — it's how *your* credential gets created, not something your
integration calls itself.) The response includes the raw `secret`
**exactly once**:

```json
{
  "id": "b3f6...",
  "client_id": "sie_9f2a7c1e4b8d0a3f",
  "secret_prefix": "aK3x9mPq",
  "scopes": ["intelligence:analytics", "safety_data:write"],
  "status": "ACTIVE",
  "expires_at": null
}
```

The full `secret` is only present in that one response. Store it
securely — SIE never stores or displays the raw value again; only
`secret_prefix` remains visible afterward, for identifying the
credential in an admin UI.

**Your credential belongs to exactly one organization, permanently.**
Every request you make is scoped to that organization — you cannot ask
for a different `organization_id` and have it honored, no matter what
scopes your credential holds. If you need to integrate with more than
one SIE organization, you need one credential per organization.

**Rotation.** `POST /api/v1/organizations/{organization_id}/api-clients/{client_id}/rotate`
issues a new secret for the same `client_id`, atomically — your
integration should be prepared to receive a `401` on the old secret
once you've rotated and switch to the new one from the same response
shape above.

**Revocation and expiration.** An administrator can revoke your
credential (`.../revoke`) or set an expiration at creation time; either
makes every subsequent request `401 Invalid, expired, or revoked API
client credential.`

### Human authentication (administrative UIs only)

Dashboards, model-approval workflows, and administrative configuration
are human-authenticated — not something your machine integration ever
does. In this deployment, human authentication is a development-mode
mechanism only (`X-SIE-Dev-User-Id`), explicitly not production-grade;
see the OpenAPI schema's `DevModeHumanHeader` security scheme
description. **If you are building a machine integration, ignore this
entirely — it is not your authentication path.**

## 2. Scopes — least privilege by default

A machine-client credential is granted an explicit list of **scopes**
at creation time — nothing is inherited from a human role, and nothing
beyond what's explicitly listed is ever accessible. Ask the
administrator provisioning your credential for exactly the scopes your
integration needs:

| Scope | What it grants |
|---|---|
| `safety_data:write` | `POST /intelligence/events`, `.../events/batch` |
| `safety_data:read` | (reserved for a future raw-event-read endpoint) |
| `intelligence:read` | `GET /intelligence/analytics/*`, `GET /intelligence/features` |
| `knowledge:read` | `POST /knowledge/retrieval/search`, `POST /knowledge/rag/query`, `GET /knowledge/*` reads |
| `knowledge:manage` | `POST /knowledge/sources`, `.../documents`, `.../versions` |
| `prediction:read` | `POST /intelligence/predictions`, `GET .../predictions/{id}`, `.../history` |

A credential missing a scope gets `403 API client missing required
scope: <scope>` — not a silent partial result.

## 3. Tenant context — never send `organization_id` and expect it trusted

Every organization-scoped request takes `organization_id` as an
explicit query parameter (or, for a knowledge source, a body field
naming *intent*) — but **the value is always checked against your
authenticated identity before it's trusted.** For a machine client,
that means: it must equal the organization your credential belongs to.
Naming a different organization — even a real one — gets `403`, never a
leak of whether that organization or its data exists.

```
GET /api/v1/intelligence/analytics/summary?organization_id=<your-own-org-id>
Authorization: Bearer sie_9f2a7c1e4b8d0a3f:aK3x9mPq...
```

## 4. Ingesting safety events

```
POST /api/v1/intelligence/events
Authorization: Bearer <client_id>:<secret>
Content-Type: application/json

{
  "event_type": "NEAR_MISS",
  "event_time": "2026-08-14T09:12:00Z",
  "site_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "severity": "LOW",
  "description": "Unsecured scaffold plank observed on level 3.",
  "source_system": "your-system-name",
  "source_record_id": "your-own-unique-id-for-this-record"
}
```

`source_system` + `source_record_id` together are your own idempotency
key at the domain level — submitting the same pair twice updates the
same record rather than duplicating it (`outcome: "UPDATED"` in the
response, not a new row). Every field except the four identity fields
is optional; a merely *questionable* value (an unrecognized severity
string, say) is still accepted and flagged, never a hard `422` — only a
genuinely malformed request (missing `event_type`, unparseable
`event_time`) is rejected outright.

**This is the lightweight path.** For structured enterprise operational
data with a registered source, source-record versioning, and full
batch/record traceability, see [§16, the Enterprise Data Ingestion
API](#16-enterprise-data-ingestion-api-structured-operational-data) —
both paths write into the same canonical event store and are equally
valid; §16 is simply the fuller-featured one.

For bulk loads, `POST /intelligence/events/batch` takes `{"events":
[...]}`, up to 1000 events per call, with a per-record result:

```json
{
  "batch_id": "...",
  "record_count": 3,
  "created_count": 2,
  "updated_count": 1,
  "rejected_count": 0,
  "records": [ { "outcome": "CREATED", "event_id": "...", ... }, ... ]
}
```

**Transport-level retry safety.** If your integration needs to safely
retry a request that might have already succeeded (a timeout before you
saw the response, for instance), send an `Idempotency-Key` header on
`POST /intelligence/predictions` (events already have their own
domain-level dedup via `source_record_id` above, so this header isn't
needed there). The same key + the same body replays the original
response; the same key with a *different* body is a `409
IDEMPOTENCY_CONFLICT` — a signal you're reusing a key incorrectly, not
a transient error to retry past.

## 5. Requesting analytics

```
GET /api/v1/intelligence/analytics/summary?organization_id=...&site_id=...
GET /api/v1/intelligence/analytics/trends?organization_id=...&metric=incident_count&period_days=30&num_periods=6
GET /api/v1/intelligence/analytics/signals?organization_id=...
GET /api/v1/intelligence/features?organization_id=...
```

All four require `intelligence:read`. `summary` composes feature
values, leading/lagging indicators, deterministic risk signals, and
per-source reliability into one response; `trends` computes a
period-bucketed slope for one named metric; `signals` returns
rule-based signals (surge/cluster detection, training-compliance drop,
etc.) — **never a fabricated probability**, every signal is a
deterministic threshold crossing with its own supporting event ids
attached. Every summary/feature carries a `data_quality` field
(`GOOD`/`LIMITED`/`INSUFFICIENT`) — an `INSUFFICIENT_DATA` result is
never silently presented as a normal answer; check it before acting on
a number computed from very little data.

## 6. Searching and querying knowledge

```
POST /api/v1/knowledge/retrieval/search
Authorization: Bearer <client_id>:<secret>

{"query": "What controls are required for working at height?"}
```

Omit `filters.organization_id` for GLOBAL knowledge (published
regulatory content, not owned by any one organization) — a valid
credential is enough, no scope required. Supply
`filters.organization_id` (must be your own) to search that
organization's private knowledge too, requiring `knowledge:read`.

`POST /knowledge/rag/query` is the same authorization shape, layered
with an LLM-generated, citation-validated answer:

```json
{
  "outcome": "ANSWERED",
  "answer": "Fall protection is required above 6 feet per 29 CFR 1926.501(b)(1) [E1].",
  "citations": [ { "citation_id": "E1", "source": "OSHA", "document": "29 CFR 1926", ... } ],
  "evidence_state": "SUFFICIENT"
}
```

An `outcome` of `INSUFFICIENT_EVIDENCE` means SIE found nothing
confident enough to answer — never a guess dressed up as a citation.

## 7. Requesting predictions

```
POST /api/v1/intelligence/predictions?organization_id=...
Authorization: Bearer <client_id>:<secret>

{"entity_id": "<site-id>"}
```

You supply **only** `entity_id` and, optionally, `as_of` — there is no
field for a feature value, a score, or a label; the feature snapshot is
always built server-side from your organization's own already-ingested
data. The response:

```json
{
  "outcome": "PREDICTED",
  "risk_score": 0.34,
  "probability": null,
  "risk_category": "MODERATE",
  "model_version": "v3",
  "data_quality": "GOOD",
  "explanation": { "contributing_features": [...] }
}
```

`probability` is `null` unless the serving model has passed calibration
validation — **never treat `risk_score` as a probability if
`probability` is null.** `outcome: "NO_PREDICTION"` (with an
`abstention_reason`) is itself a real, meaningful result — a model that
declines to score cold-start data or stale sources is doing exactly
what it should; never treat an abstention as an error to retry past.

`GET /intelligence/predictions/{entity_id}` returns the latest
recorded prediction; `GET .../{entity_id}/history?limit=&offset=`
returns paginated history, newest first, wrapped in the standard
response envelope (see below) — the first endpoint in this API to use
it.

**Predictions are advisory only.** SIE never automatically suspends a
worker, blocks a permit, stops equipment, or takes any other action on
a prediction's behalf — every prediction response carries a fixed
safety-language disclaimer for exactly this reason. Build your
integration's own workflow to keep a human in the loop for any action
taken on a prediction.

## 8. Provenance — tracing a response back to its source

Every intelligence response carries enough to answer "where did this
come from":

```
RAG answer -> citation -> chunk -> document version -> document -> knowledge source
Prediction -> model -> feature snapshot -> feature values -> supporting safety events -> your own source_system/source_record_id
Risk signal -> feature -> supporting safety events -> your own source_system/source_record_id
```

None of this is regenerated or approximated at the API layer — every
provenance chain is the same one the underlying intelligence service
already computed; the API surfaces it, never recreates it.

## 9. The standard response envelope (new endpoints only)

Existing endpoints keep their current, unwrapped response shape — this
integration guide never asks you to change how you parse an existing
call. A genuinely new response shape (currently: prediction history)
uses a standard envelope instead:

```json
{
  "data": [ /* the real payload */ ],
  "status": "SUCCESS",
  "request_id": "1670f72b0d4e45e7961dd61d58e083fb",
  "timestamp": "2026-08-14T09:12:00Z",
  "data_quality": null,
  "provenance": { "organization_id": "...", "entity_id": "..." }
}
```

`request_id` also appears as an `X-Request-Id` response header on
*every* endpoint, existing or new — log it; SIE's own audit trail
records it too, so it's the fastest way to correlate a support
conversation with what actually happened server-side.

## 10. Errors

Every error response keeps its existing `detail` field exactly as
before (a string, or — for a handful of endpoints — a structured
object; never re-typed), and gains an additive `error` object:

```json
{
  "detail": "Missing intelligence:read permission in the requested organization.",
  "error": {
    "code": "AUTHORIZATION_DENIED",
    "message": "Missing intelligence:read permission in the requested organization.",
    "request_id": "1670f72b0d4e45e7961dd61d58e083fb"
  }
}
```

| `error.code` | Meaning |
|---|---|
| `AUTHENTICATION_REQUIRED` | No credential presented, or it's malformed |
| `AUTHORIZATION_DENIED` | Valid credential, missing permission/scope |
| `TENANT_ACCESS_DENIED` | Attempted a different organization than your credential's own |
| `RESOURCE_NOT_FOUND` | The id doesn't exist, or doesn't belong to you (never distinguished) |
| `VALIDATION_ERROR` | Malformed request body/query |
| `RATE_LIMIT_EXCEEDED` | See below |
| `IDEMPOTENCY_CONFLICT` | Reused `Idempotency-Key` with a different body |
| `INSUFFICIENT_DATA` | A dataset/model doesn't meet minimum data requirements |
| `MODEL_NOT_AVAILABLE` | No deployed model exists for this prediction target |
| `INTERNAL_ERROR` | Something genuinely unexpected — never a leaked stack trace or database error |

## 11. Rate limits

Where enabled, SIE enforces separate read and write budgets per caller.
A `429` carries `error.code == "RATE_LIMIT_EXCEEDED"` plus
`X-RateLimit-Limit`/`X-RateLimit-Remaining`/`X-RateLimit-Reset`
response headers on every request, so you can back off proactively
rather than waiting for a rejection. Rate limiting is off by default in
this codebase's own configuration — ask your SIE administrator whether
it's enabled for your deployment and at what limits.

## 12. A minimal Python example client

```python
import httpx

SIE_BASE_URL = "https://your-sie-deployment.example.com/api/v1"
CLIENT_ID = "sie_9f2a7c1e4b8d0a3f"
CLIENT_SECRET = "aK3x9mPq..."  # from credential creation/rotation -- never hardcode in real code
ORGANIZATION_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

session = httpx.Client(
    base_url=SIE_BASE_URL,
    headers={"Authorization": f"Bearer {CLIENT_ID}:{CLIENT_SECRET}"},
    timeout=30.0,
)


def ingest_near_miss(*, site_id: str, description: str, your_own_record_id: str) -> dict:
    response = session.post(
        "/intelligence/events",
        json={
            "event_type": "NEAR_MISS",
            "event_time": "2026-08-14T09:12:00Z",
            "site_id": site_id,
            "description": description,
            "source_system": "your-system-name",
            "source_record_id": your_own_record_id,
        },
    )
    response.raise_for_status()
    return response.json()


def get_risk_signals(*, site_id: str) -> list[dict]:
    response = session.get(
        "/intelligence/analytics/signals",
        params={"organization_id": ORGANIZATION_ID, "site_id": site_id},
    )
    response.raise_for_status()
    return response.json()


def request_prediction(*, site_id: str) -> dict:
    response = session.post(
        "/intelligence/predictions",
        params={"organization_id": ORGANIZATION_ID},
        json={"entity_id": site_id},
    )
    response.raise_for_status()
    return response.json()
```

## 13. Safelytic — one consumer, no special treatment

Safelytic (the reference frontend developed alongside SIE) integrates
exactly the way this guide describes, with no logic living inside SIE's
own intelligence engine on Safelytic's behalf:

```
Safelytic frontend
    -> its own backend/BFF holds a SIE machine-client credential
    -> SIE API (Authorization: Bearer <client_id>:<secret>)
    -> authentication -> tenant context -> intelligence engine
    -> response (analytics / predictions / RAG answer)
    -> Safelytic dashboard renders it
```

Safelytic's credential is provisioned the same
`POST /organizations/{id}/api-clients` call any other integration uses,
with whatever scopes its dashboard actually needs (typically
`intelligence:read`, `prediction:read`, `knowledge:read`). Nothing in
`app/predictions`, `app/intelligence`, or `app/rag` contains a
Safelytic-specific branch, field, or code path — if it did, that would
mean SIE had stopped being an independent platform.

## 14. Third-party example — an unrelated HSE platform

To prove SIE is genuinely application-independent, here is a complete,
realistic flow for a company's *own* HSE platform — unrelated to
Safelytic, never having heard of it:

```
ThirdPartyHSE (an external, unrelated safety-management product)
    1. Its administrator creates a SIE organization for their company
       (or a SIE administrator does, on their behalf) and provisions a
       machine-client credential scoped to safety_data:write +
       intelligence:read + prediction:read.
    2. Their existing incident-reporting workflow calls
       POST /intelligence/events (and /events/batch for a nightly
       historical backfill) whenever a near-miss, observation, or
       incident is logged in their own system -- source_system:
       "thirdpartyhse", source_record_id: their own internal id.
    3. Their dashboard calls GET /intelligence/analytics/signals on a
       schedule (or on page load) and renders SIE's risk signals inside
       their own UI, styled entirely by them.
    4. Their site-manager view calls POST /intelligence/predictions for
       each site under management and shows risk_category (and
       probability, only when non-null) next to their own existing
       site data.
    5. A human at ThirdPartyHSE decides what to do about an elevated
       signal or prediction -- SIE never acts on their data or their
       workers on its own.
```

No code in this repository knows ThirdPartyHSE exists. Every one of
those five steps is exactly the same API surface, the same
authentication mechanism, and the same authorization rules this guide
already documented for Safelytic — proof that "SIE is one platform,
many consumers" is an architectural property, not a claim.

## 15. What SIE never does on its own

Regardless of caller, SIE never: automatically suspends or disciplines
a worker, blocks a permit, shuts down equipment, contacts a regulator,
closes an incident, modifies your organization's own records, retrains
a predictive model, or takes any other autonomous action. Every
response is advisory information for a human decision-maker in *your*
system — building an automated action on top of a SIE response is your
integration's own choice and responsibility, never something SIE
initiates.

## 16. Enterprise Data Ingestion API (structured operational data)

Enterprise Data Ingestion & Validation Foundation v0.1 adds a
fuller-featured, source-tracked entry point for structured operational
data — HSE/EHS platforms, ERP systems, HR/training systems,
permit-to-work systems, inspection systems, incident management,
CMMS/maintenance, construction/project systems, manufacturing systems,
IoT/telemetry, or a plain CSV/Excel export turned into JSON by your own
pipeline. **This is not built for any one named application** — the
examples below use a generic manufacturing company, not Safelytic (see
§13/§14 for why SIE is application-independent by design).

    external system -> Authorization: Bearer <client_id>:<secret>
        -> POST /api/v1/data/ingestion
        -> validation -> normalization -> data-quality classification
        -> duplicate/version-conflict handling -> canonical safety_events
        -> [same intelligence engine every other ingestion path feeds]

### Registering an ingestion source (optional, but recommended)

An "ingestion source" is a registered record of *which* external system
is sending data — useful for auditability, and required if you want
`source_record_version` conflict/staleness protection to mean something
tenant-wide. Register one per real integration:

```
POST /api/v1/organizations/{organization_id}/data-sources
Authorization: Bearer <client_id>:<secret>   (or a human admin's session)
Content-Type: application/json

{
  "name": "Acme Manufacturing — SAP EHS Module",
  "source_type": "erp",
  "system_identifier": "sap-prod-us1",
  "schema_version": "v3",
  "config_metadata": {"timezone": "America/Chicago"}
}
```

The returned `id` is what you pass as `source_id` on each ingestion
call. This step is optional — omitting `source_id` still ingests data
normally, just without a registered-source association on the resulting
events.

### Submitting data

```
POST /api/v1/data/ingestion
Authorization: Bearer <client_id>:<secret>
Content-Type: application/json
Idempotency-Key: <optional, for safe retry of the whole submission>

{
  "source_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "records": [
    {
      "event_type": "INCIDENT",
      "event_subtype": "SLIP_TRIP_FALL",
      "event_time": "2026-08-14T09:12:00Z",
      "site_id": "6e6c9f2a-1234-4a3b-9abc-1234567890ab",
      "severity": "MEDIUM",
      "description": "Worker slipped on wet floor near loading dock.",
      "attributes": {"body_part": "ankle", "days_away_from_work": 2},
      "source_system": "sap-prod-us1",
      "source_record_id": "INC-20260814-0042",
      "source_record_version": "1",
      "correlation_id": "WORKORDER-88213",
      "source_schema_version": "v3"
    }
  ]
}
```

Every field but the four identity fields (`event_type`, `event_time`,
`source_system`, `source_record_id`) is optional — a merely
*questionable* value is still accepted and flagged (see "Validation
states" below), never a hard `422`. Batches accept up to 1000 records
per call. The response reports exactly what happened:

```json
{
  "batch_id": "b1f8e3a0-...",
  "source_id": "3fa85f64-...",
  "status": "COMPLETED",
  "received_at": "2026-08-14T09:12:05Z",
  "total_records": 1,
  "accepted_records": 1,
  "partial_records": 0,
  "quarantined_records": 0,
  "rejected_records": 0,
  "duplicate_records": 0,
  "error_summary": null,
  "records": [
    {
      "outcome": "CREATED",
      "canonical_event_id": "9c3a...",
      "quality_state": "VALID",
      "issues": [],
      "duplicate_in_batch": false,
      "external_record_id": "INC-20260814-0042",
      "source_record_version": "1",
      "content_hash": "a94f..."
    }
  ]
}
```

Check on a batch later with `GET /api/v1/data/ingestion/batches/{batch_id}`
or list your organization's recent batches with `GET
/api/v1/data/ingestion/batches`.

### Validation states

Every record ends up in one of four states — the same
`DataQualityStatus` vocabulary the rest of SIE already uses, not a
second one invented for this endpoint:

| State | Meaning | Is a canonical event created? |
|---|---|---|
| `VALID` | Satisfies every canonical constraint. | Yes. |
| `PARTIAL` | Usable, but has a non-critical issue (e.g. an unrecognized severity string). | Yes. |
| `QUARANTINED` | Stored, but excluded from every analytics/feature/signal calculation until reviewed (e.g. missing/unparseable `event_time`). | Yes. |
| *(rejected)* | Missing an identity field (`event_type`, `source_system`, `source_record_id`) or a value too long to store. | **No** — `outcome: "REJECTED_INVALID"`, `canonical_event_id: null`. |

An inspection record and an incident record are not held to identical
requirements beyond those four shared identity fields — a domain-specific
field that's missing (say, an inspection's checklist score) is not, by
itself, a validation failure; it's just an absent `attributes` key.
"Structurally valid" and "partially complete" are the honest words used
throughout — nothing here claims a `VALID` record is *factually
correct*, only that it satisfies SIE's own structural checks.

### Duplicate and source-record-version semantics

Identity is `(source_system, source_record_id)` within your
organization — resending the same pair is always looked at against
whatever is already stored:

| Scenario | Outcome |
|---|---|
| Exact replay (identical content) | `SKIPPED_IDEMPOTENT` — no-op, no new row, no duplicate. |
| Same `source_record_version`, same content | `SKIPPED_IDEMPOTENT`. |
| Same `source_record_version`, **different** content | `REJECTED_VERSION_CONFLICT` — refused, not guessed; the stored row is untouched. |
| **Newer** integer `source_record_version` | `UPDATED` — applied in place. |
| **Older** integer `source_record_version` (late arrival) | `SKIPPED_STALE_VERSION` — refused; the newer stored row is untouched. |
| Different `source_record_id`s, identical payload content | Two distinct events — never collapsed into one. |

**Documented limitation.** Strict newer/older ordering only applies when
**both** the stored and incoming `source_record_version` values parse as
plain integers — by far the most common real-world convention. A
non-numeric scheme (a semantic version, an ISO timestamp used as a
version marker, ...) falls back to today's simpler behavior: different
content always overwrites in place, last write wins, with no ordering
protection. If your system versions records non-numerically and you need
ordering protection, use a plain incrementing integer as
`source_record_version` today, or contact SIE about extending this in a
future milestone.

### Terminology mapping for heterogeneous source vocabulary

Real source systems rarely use SIE's own canonical vocabulary verbatim —
one system's `"Near Miss"` is another's `"NM"` or `"Potential Incident"`.
`app/intelligence/terminology_mapping.py` (Real-World Data Validation &
Intelligence Calibration v0.1) is a small, deterministic (no LLM),
table-driven mapping layer covering incident types, observation types,
inspection types, audit findings, training status, and maintenance
status, available as an opt-in `DataSourceAdapter` — pass it as this
endpoint's `adapter` when integrating a source whose own terminology
differs from SIE's canonical values, rather than pre-mapping every
payload yourself before sending it. **It never guesses**: an ambiguous
or unrecognized term is quarantined with an explicit issue, not silently
mapped to the closest-looking canonical value. See
`docs/CALIBRATION_METHODOLOGY.md` §4 for the full mapping methodology,
and `tests/test_terminology_mapping.py` for the current alias tables per
domain — extend those tables directly if your source's own terminology
isn't yet covered.

### Provenance

Every canonical event created through this endpoint traces back to: the
organization, the ingestion source (if `source_id` was given), the
batch (`GET .../batches/{batch_id}`), the external record id and
version you supplied, the ingestion timestamp, a content hash, and
whether/how it was normalized — nothing is an untraceable "orphan" row.
`GET /api/v1/intelligence/predictions/...`, analytics, and RAG responses
elsewhere in this API all carry their own provenance chains back to the
`safety_events` this endpoint writes (see §8).

### Authentication and permissions

Machine-client only (§1) — this is system-to-system integration, not a
human dashboard action. Scopes, from the existing vocabulary (§2), no
new ones invented for this endpoint:

| Action | Scope |
|---|---|
| `POST /data/ingestion` (submit data) | `safety_data:write` |
| `GET /data/ingestion/batches[/{id}]` (batch status) | `safety_data:read` (human or machine) |
| `POST/GET/PATCH .../data-sources*` (register/manage a source) | `safety_data:write` (write) / `safety_data:read` (read) |

### Tenant isolation

Exactly §3's rule, with no exceptions: the organization for a write is
always the authenticated credential's own, pinned organization — there
is no field anywhere in the request body that names a different one. A
`source_id` you supply is verified to belong to that same organization
first (a source belonging to someone else 404s, never revealing it
exists). Every read requires an explicit, authorized `organization_id`
query parameter — there is no GLOBAL-shaped variant of an ingestion
batch at all, so the class of authorization bug closed in an earlier
milestone (a machine client bypassing scope on a GLOBAL-shaped request)
has no equivalent surface here to reappear on.

### Current limitations

* Source-record-version ordering only protects plain-integer version
  schemes (see above).
* Processing is synchronous — a very large batch is processed inline,
  within the request; there is no background/async processing yet
  (the `EnterpriseIngestionBatch.status` field's `RECEIVED` value is the
  seam a future asynchronous implementation would use).
* Structured JSON is the only wire format implemented. CSV/XLSX, a
  webhook receiver, a database connector, and an event-stream consumer
  are all documented future extension points (below), not built.
* A rejected record's raw payload is retained on its
  `EnterpriseIngestionRecord` row for traceability (the one case with no
  canonical event to hold it); a `QUARANTINED`/`PARTIAL`/`VALID`
  record's payload lives on its canonical event instead, never
  duplicated.
* **A one-time bulk historical backfill will make retrospective trend
  analytics over that backfilled period look degenerate** (collapsed
  into the single most recent period) until real-time-cadence data has
  accumulated — a direct, correct consequence of SIE's point-in-time
  leakage guarantee (`ingestion_time` is always stamped at real
  wall-clock "now"), not a defect. If you are migrating years of
  history in one ingestion run and need meaningful historical trend
  reconstruction over that period immediately, see
  `docs/CALIBRATION_METHODOLOGY.md` §5 for the full explanation and
  what such an integration would need to account for.

### Future connector extension points

The generic contract (`event_type`/`event_time`/`source_system`/
`source_record_id`/...) is deliberately format-agnostic — a future
milestone can add, without changing this contract or the validation/
normalization/upsert pipeline underneath it:

* **CSV/XLSX upload** — a thin adapter that maps spreadsheet columns
  onto the same `EnterpriseIngestionRecordCreate` shape before handing
  off to the exact same pipeline this endpoint already uses.
* **Webhooks** — an inbound receiver that authenticates a source
  system's own webhook signature and translates its payload the same
  way.
* **Database connectors** — a scheduled/triggered puller for a source
  system's own database or export table.
* **Event streams** — a consumer for a message bus (Kafka or similar),
  explicitly out of scope for this milestone (no message broker was
  introduced to support it).

### A generic example — Northbridge Manufacturing (not Safelytic)

```
Northbridge Manufacturing operates three plants and already runs a CMMS
(maintenance) system and a separate incident-reporting tool, neither of
which has ever heard of Safelytic.

1. Northbridge's IT team provisions one SIE machine-client credential
   per system (safety_data:write, safety_data:read) and registers two
   ingestion sources: "CMMS — Plant Floor" and "Incident Reporting Tool".
2. Their CMMS nightly job POSTs equipment-failure and maintenance
   records to /api/v1/data/ingestion, tagged event_type: "EQUIPMENT",
   source_system: their CMMS's own hostname, with an incrementing
   source_record_version whenever a work order is updated.
3. Their incident tool POSTs incidents/near-misses in real time as they
   are logged, each with a stable source_record_id it already has.
4. A Northbridge safety analyst calls GET /intelligence/analytics/signals
   and GET /intelligence/predictions/{site_id} from their own internal
   reporting tool -- built entirely in-house, never touching SIE's own
   source code.
```

Nothing above is Safelytic-specific, and nothing in SIE's own source
code contains a Northbridge-specific branch either — the same guarantee
§13/§14 already demonstrate, extended to this endpoint.
