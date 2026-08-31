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

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)

# Unversioned liveness check.
app.include_router(health_router)

# Versioned application API.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
