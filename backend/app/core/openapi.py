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
    {"name": "data-sources", "description": "Registered data sources for an organization."},
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
