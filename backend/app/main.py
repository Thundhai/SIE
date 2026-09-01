"""SIE FastAPI application entrypoint.

SIE (Safety Intelligence Engine) is an independent, multi-tenant backend.
It is not architecturally coupled to any single consumer — Safelytic is one
external application that will eventually call this API, but any
authorized enterprise application can connect the same way, through the
same versioned REST surface.
"""

from fastapi import FastAPI

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

# Standardized error contract (item 15) — additive to every existing
# route's response body, see app/core/errors.py's own docstring.
register_exception_handlers(app)

# Unversioned liveness check.
app.include_router(health_router)

# Versioned application API.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
