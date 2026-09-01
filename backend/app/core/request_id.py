"""Request ID middleware — Intelligence Platform Integration & Enterprise
API v0.1, item 11.

    request -> RequestIdMiddleware -> request.state.request_id (generated, uuid4)
        -> route handler / audit_service.log(request_id=...)
        -> response gets an `X-Request-Id` header
        -> also surfaced in app/core/errors.py's error envelope

Always server-generated (never trusts a client-supplied request id as
its own identity — a client-supplied `X-Request-Id` it sent is echoed
back too, under a different header, purely as a courtesy for a caller
correlating its own logs, but it is never what gets written to the audit
trail or used anywhere as *the* request's identity). Deliberately just a
`uuid4` string, not a structured trace-context format (W3C traceparent,
etc.) — this is the foundation the milestone asks for, not a distributed
tracing system.

**One known, accepted gap.** `request.state.request_id` (and therefore
the JSON error body's `error.request_id` — see `app/core/errors.py`) is
always correct, on every response, including a genuinely unhandled
exception. The `X-Request-Id` *response header* this middleware itself
sets is not: Starlette places its outermost `ServerErrorMiddleware`
(which is what actually builds the response for a truly unhandled
exception) outside every user-added middleware, this one included, so
that one path's response never passes back through this class's own
header-setting code. Every *handled* error path (any `HTTPException`,
`ApiError`, or `RequestValidationError` — i.e. everything this codebase's
own routes ever deliberately raise) is unaffected and always carries the
header correctly.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"
CLIENT_REQUEST_ID_HEADER = "X-Client-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id

        client_supplied = request.headers.get(REQUEST_ID_HEADER)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        if client_supplied:
            response.headers[CLIENT_REQUEST_ID_HEADER] = client_supplied
        return response


def get_request_id(request: Request) -> str | None:
    """FastAPI-dependency-friendly accessor — `Depends(get_request_id)` —
    for route handlers that want to pass it into `audit_service.log()`
    without reaching into `request.state` directly."""
    return getattr(request.state, "request_id", None)
