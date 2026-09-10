"""API observability foundation — Intelligence Platform Integration &
Enterprise API v0.1, item 32.

One structured log line per request: method, path, status code, latency,
and — when resolvable without adding a second identity lookup — the
calling client's public identifier (`client_id` for a machine caller,
never logged for a human request since the dev-mode header is not a
verified identity worth attributing metrics to). **Never the request or
response body** — this is latency/status/usage observability, not a
request-content log; see `app/core/config.py`'s existing
`LOG_RETRIEVAL_QUERY_TEXT`/`LOG_RAG_QUERY_TEXT` off-by-default settings
for the same principle already applied elsewhere in this codebase.

Deliberately just Python's own `logging` module, one dedicated logger
(`sie.api.access`) — no metrics backend, no Prometheus client, no new
database table. "Provide a *foundation* for request latency/status
codes/endpoint usage/error rates/client usage/rate-limit events" (item
32's own framing) is satisfied by every one of those being present on
every emitted line, in a structured (JSON) format a real log pipeline
(CloudWatch, Datadog, ELK, ...) can already ingest and aggregate without
this codebase needing to run that aggregation itself.
"""

from __future__ import annotations

import json
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

access_logger = logging.getLogger("sie.api.access")


def _caller_identity(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[len("Bearer ") :].strip()
        client_id = token.split(":", 1)[0]
        return f"api_client:{client_id}" if client_id else None
    return None  # never attribute a metric line to an unverified dev-mode header value


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        # If a rate-limit check ran for this request (app/api/deps_rate_limit.py),
        # surface it as standard-shaped response headers -- a courtesy for
        # any caller, not just one that got a 429.
        rate_limit_result = getattr(request.state, "rate_limit_result", None)
        if rate_limit_result is not None:
            response.headers["X-RateLimit-Limit"] = str(rate_limit_result.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_result.remaining)
            response.headers["X-RateLimit-Reset"] = str(round(rate_limit_result.reset_seconds, 1))

        access_logger.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "client": _caller_identity(request),
                    "request_id": getattr(request.state, "request_id", None),
                }
            )
        )
        return response
