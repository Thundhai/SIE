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
