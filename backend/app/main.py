"""SIE FastAPI application entrypoint.

SIE (Safety Intelligence Engine) is an independent, multi-tenant backend.
It is not architecturally coupled to any single consumer — Safelytic is one
external application that will eventually call this API, but any
authorized enterprise application can connect the same way, through the
same versioned REST surface.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.observability import AccessLogMiddleware
from app.core.openapi import custom_openapi
from app.core.request_id import RequestIdMiddleware
from app.core.request_limits import RequestSizeLimitMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)
app.openapi = lambda: custom_openapi(app)

# Outermost first: every request gets a request_id before anything else
# (including the access-log line and every error response) ever runs;
# the access log then reports on the fully-completed response, including
# its final status code. See each middleware's own module docstring.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestIdMiddleware)

# CORS (SIE Enterprise Read API & Browser Integration Foundation v0.1) —
# added LAST, so it is the OUTERMOST middleware layer (see the
# "Outermost first" note above: the last `add_middleware()` call wraps
# every other layer). That placement is deliberate, not incidental: a
# preflight `OPTIONS` request must get a correct CORS response before it
# ever reaches rate limiting/request-size/request-id/routing, and every
# real response -- including a 401/403/404/429/500 produced by any inner
# layer or by `register_exception_handlers()` below -- must still carry
# the `Access-Control-Allow-Origin` header on its way back out, or a
# browser reports a misleading "CORS error" that masks the real one.
#
# `settings.cors_allowed_origins_list` is an explicit, configured
# allowlist of exact origins -- never `["*"]` for this authenticated API
# (see that setting's own docstring in app/core/config.py). An empty
# list (nothing configured) means no browser origin is allowed at all;
# `CORSMiddleware` itself already handles that correctly (it simply never
# matches), so no special-casing is needed here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

# Standardized error contract (item 15) — additive to every existing
# route's response body, see app/core/errors.py's own docstring.
register_exception_handlers(app)

# Unversioned liveness check.
app.include_router(health_router)

# Versioned application API.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
