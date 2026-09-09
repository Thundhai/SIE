"""OpenAPI documentation customization — Intelligence Platform
Integration & Enterprise API v0.1, item 27.

FastAPI generates an accurate schema for every route, request/response
model, and validation constraint on its own from the code — nothing
here duplicates or overrides that. What FastAPI does *not* infer on its
own is documented explicitly:

  * **Authentication** — this codebase has two, and only two, real
    mechanisms (see `app/api/deps_machine_auth.py`/`app/api/deps_auth.py`'s
    own docstrings); FastAPI has no way to discover either from a plain
    `Header`/custom-header dependency, so both are declared here as
    named OpenAPI `securitySchemes` with a description of their actual
    format and scope, for a reader of `/docs`/`/openapi.json` to
    understand without reading this codebase's source.
  * **Tags** — a one-line description per router tag, so the generated
    docs group routes under a heading a human can understand instead of
    a bare identifier.

`ALL_SCOPES` is generated directly from `app.services.permissions.Permission`
— never hand-maintained, so it can never drift out of sync with the one
real scope vocabulary machine clients and human roles both draw from.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.services.permissions import Permission

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness — no authentication required."},
    {"name": "organizations", "description": "Tenant (organization) administration."},
    {"name": "sites", "description": "Sites belonging to an organization."},
    {
        "name": "data-sources",
        "description": (
            "Registered ingestion sources for an organization (human or machine, "
            "`safety_data:read`/`safety_data:write`)."
        ),
    },
    {
        "name": "knowledge",
        "description": "Knowledge sources, documents, versions, and chunks (GLOBAL or ORGANIZATION-scoped).",
    },
    {"name": "memberships", "description": "Human user membership and role administration."},
    {
        "name": "ingestion",
        "description": "File upload into the knowledge base (human-authenticated, `knowledge:manage`).",
    },
    {"name": "retrieval", "description": "Semantic evidence search over ingested knowledge."},
    {"name": "rag", "description": "Evidence-grounded, citation-validated question answering."},
    {
        "name": "intelligence",
        "description": (
            "Safety-event ingestion (machine-client authenticated) and safety analytics/features "
            "(human or machine, `intelligence:read`)."
        ),
    },
    {
        "name": "predictions",
        "description": "Predictive risk scoring for a site — request, latest, and history (human or machine, `prediction:read`).",
    },
    {
        "name": "model-governance",
        "description": (
            "Predictive-model dataset validation, training, human approval, deployment, and monitoring "
            "— administrative, human-authenticated only (`governance:read`/`governance:manage`)."
        ),
    },
    {
        "name": "api-clients",
        "description": "Machine-client (API key) credential management — administrative, human-authenticated only.",
    },
    {
        "name": "enterprise-ingestion",
        "description": (
            "Enterprise structured-data ingestion (JSON, batched, machine-client authenticated, "
            "`safety_data:write`) with full source/batch/record traceability; batch status is "
            "readable by human or machine (`safety_data:read`)."
        ),
    },
    {
        "name": "events",
        "description": (
            "Human-facing, tenant-isolated read access to the enterprise `SafetyEvent` population "
            "— list (filtered, searched, paginated) and single-event detail with provenance "
            "(human or machine, `safety_data:read`). See `docs/ENTERPRISE_API.md`."
        ),
    },
    {
        "name": "auth",
        "description": (
            "The authenticated caller's own identity, organization, role, and effective permission "
            "set — human-only, backend-authoritative (no client-side permission matrix). "
            "See `docs/ENTERPRISE_API.md`."
        ),
    },
    {
        "name": "actions",
        "description": (
            "Governed safety actions — create, list, read, update, and transition status "
            "(OPEN/IN_PROGRESS/BLOCKED/COMPLETED/CANCELLED) with an enforced transition matrix, "
            "tenant-safe event/site/owner provenance, immutable per-action history, and "
            "idempotent creation (human or machine, `intervention:read`/`:manage`/`:assign`/`:close`). "
            "See `docs/ACTIONS_DOMAIN.md`."
        ),
    },
    {
        "name": "risk-assessments",
        "description": (
            "Structured enterprise risk assessments sitting above (never replacing) the "
            "deterministic `enterprise-risk-v1` score — governed risk areas, findings with "
            "evidence, an explicit likelihood x consequence risk matrix (`risk-assessment-v1`), "
            "controls and their effectiveness, an independently-assessed residual risk, and a "
            "versioned DRAFT -> IN_REVIEW -> APPROVED -> SUPERSEDED lifecycle "
            "(`risk_assessment:read`/`:write`/`:approve`). See "
            "`docs/RISK_ASSESSMENT_FOUNDATION_V0_1.md`."
        ),
    },
    {
        "name": "projects",
        "description": (
            "Organizational & operational scope — SIE Milestone 35. A `Project` is an organization-owned "
            "identity (name, code, lifecycle status) that may span multiple `Site`s, and a `Site` may host "
            "multiple `Project`s, via an explicit, tenant-safe Project/Site relationship. Identity and "
            "relationships only — no task/schedule/budget management "
            "(`project:read` to read, `project:manage` to create projects and manage relationships)."
        ),
    },
    {
        "name": "intelligence-decisions",
        "description": (
            "Human decision provenance for an intelligence/attention signal — SIE Milestone 34. "
            "Records a typed decision (ACT/DO_NOT_ACT/DEFER/ALREADY_ADDRESSED/NOT_RELEVANT) and "
            "free-text rationale against an `GET /intelligence/attention` item, with SIE's own "
            "category/priority/evidence snapshot re-derived and preserved server-side, never "
            "recalculated or overwritten by the human decision. May reference an existing "
            "`SafetyAction` (never created automatically). The one intentional write path in the "
            "otherwise read-only intelligence/attention/context workflow "
            "(`intelligence:decision_write` to create, `intelligence:read` to read)."
        ),
    },
    {
        "name": "intelligence-outcomes",
        "description": (
            "Ground-truth field outcome capture for a human decision/intervention — SIE Milestone 37 — "
            "plus the outcome-verification/evidence-evaluation layer built on top of it in SIE Milestone "
            "38. Records what actually happened afterward (EFFECTIVE/PARTIALLY_EFFECTIVE/INEFFECTIVE/"
            "NO_OUTCOME_RECORDED) against an existing `IntelligenceDecision`, with an optional reference "
            "to a `SafetyAction` intervention — never inferred automatically from action closure or "
            "event absence — and a subsequent human judgment (VERIFIED/INSUFFICIENT_EVIDENCE/DISPUTED) "
            "of whether that recorded outcome is trustworthy, gated by a deterministic evidence-validity "
            "check. Both layers are append-only: no update endpoint, a correction is a new row. A "
            "ground-truth capture and verification layer, not the SIE learning engine "
            "(`intelligence:decision_write` to create, `intelligence:read` to read)."
        ),
    },
    {
        "name": "intelligence-learning-candidates",
        "description": (
            "The governed entry boundary into `LEARN` — SIE Milestone 39. Creates a durable "
            "`IntelligenceLearningCandidate` from an outcome whose resolved current verification is "
            "`VERIFIED` with independently valid evidence (reuses SIE Milestone 38's own eligibility "
            "gate verbatim), and records separate, later human governance decisions "
            "(ACCEPTED/REJECTED) about whether a candidate is actually admitted into future learning. "
            "Eligibility (a deterministic system check) and acceptance (a human governance judgment) "
            "are never conflated. Append-only on both tables: no update endpoint, a correction is a new "
            "governance-decision row. Still not the SIE learning engine — nothing here trains, retrains, "
            "or adjusts a model, threshold, risk score, or intelligence rule "
            "(`intelligence:decision_write` to create/govern, `intelligence:read` to read)."
        ),
    },
]

_MACHINE_BEARER_DESCRIPTION = (
    "Machine-client (system-to-system) authentication for external application integration.\n\n"
    "    Authorization: Bearer <client_id>:<secret>\n\n"
    "`client_id` and `secret` are returned once, at credential creation "
    "(`POST /api/v1/organizations/{organization_id}/api-clients`) or rotation "
    "(`.../rotate`) — the secret is never shown again afterward. Not a standard "
    "OAuth2 bearer token; the literal string `client_id:secret` is the credential. "
    "The organization a client belongs to is fixed at creation time and can never "
    "be overridden by a request — every organization-scoped route independently "
    "verifies the requested `organization_id` matches the authenticated client's own. "
    "A client is granted an explicit, minimal list of scopes at creation time (see "
    "`x-sie-scopes` below) — it can access only what those scopes name, nothing "
    "inherited from any role."
)

_DEV_HEADER_DESCRIPTION = (
    "Development-only human identity header — **never valid in a production "
    "deployment** (disabled unless the server has `DEV_MODE=true`, which must "
    "never be set in production). Names an existing user by id; the request is "
    "then authorized exactly as that user's own real, stored role/permissions "
    "allow. Stands in for a real OIDC/OAuth2 human login, which is not yet wired "
    "into this codebase — see the README's \"Identity architecture\" section."
)


def custom_openapi(app: FastAPI):
    """Installed as `app.openapi = lambda: custom_openapi(app)` in
    `app/main.py`. Cached on `app.openapi_schema` exactly the way
    FastAPI's own default implementation caches it, so this only runs
    once per process."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=(
            "SIE (Safety Intelligence Engine) is an independent, multi-tenant safety "
            "intelligence platform — not one client application's backend. Any authorized "
            "system integrates the same way, through this versioned REST API. See the "
            "Developer Integration Guide (`docs/INTEGRATION_GUIDE.md`) for a full walkthrough."
        ),
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )

    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["MachineClientBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "client_id:secret",
        "description": _MACHINE_BEARER_DESCRIPTION,
    }
    schema["components"]["securitySchemes"]["DevModeHumanHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-SIE-Dev-User-Id",
        "description": _DEV_HEADER_DESCRIPTION,
    }
    # The full scope vocabulary, generated from the one real source of
    # truth (never hand-duplicated) -- a vendor extension since OpenAPI
    # itself has no first-class "list of possible scope strings" outside
    # of an oauth2 flow, which this bearer scheme deliberately isn't.
    schema["components"]["x-sie-scopes"] = sorted(p.value for p in Permission)

    app.openapi_schema = schema
    return app.openapi_schema
