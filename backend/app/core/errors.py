"""Standardized API error contract — Intelligence Platform Integration &
Enterprise API v0.1, item 15.

**Additive, never replacing** (item 35's "do not break existing v1
consumers"): every error response keeps FastAPI's own `detail` field
byte-for-byte what today's client already sees — a plain string for most
routes, or whatever structured shape a specific route already returns
(e.g. `app/api/v1/model_governance.py`'s `{"message": ..., "failed_checks": [...]}`
on `INSUFFICIENT_DATA`) — and gains a second, parallel `error` object
carrying this item's small, closed vocabulary of `code`s plus the
request's own `request_id` (item 11). No existing route's `detail`
shape or `status_code` changes.

    {
      "detail": "<unchanged from today -- string or a route's own structured detail>",
      "error": {"code": "AUTHORIZATION_DENIED", "message": "<string>", "request_id": "..."}
    }

No database error, stack trace, credential, storage path, or other
internal-infrastructure detail is ever placed in either field —
`unhandled_exception_handler()` below is the one path that could
otherwise leak one, and it never does.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode:
    """The closed vocabulary milestone item 15 names. Not a Python enum —
    see `app.services.audit_service.AuditAction`'s own docstring for the
    identical reasoning (a plain-string convenience/typo-guard, checked
    by exact-value tests, not an enforced closed type)."""

    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PRIVACY_BLOCKED = "PRIVACY_BLOCKED"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# A reasonable default `code` inferred purely from an ordinary
# `HTTPException`'s `status_code`, for the many existing (and future)
# call sites across this codebase that raise a plain `HTTPException` and
# were never written with this vocabulary in mind — see `ApiError` below
# for how a route opts into a *specific* code instead.
_STATUS_CODE_DEFAULTS: dict[int, str] = {
    401: ErrorCode.AUTHENTICATION_REQUIRED,
    403: ErrorCode.AUTHORIZATION_DENIED,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    409: ErrorCode.IDEMPOTENCY_CONFLICT,
    413: ErrorCode.VALIDATION_ERROR,
    415: ErrorCode.VALIDATION_ERROR,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMIT_EXCEEDED,
}


class ApiError(StarletteHTTPException):
    """Raise this instead of a plain `HTTPException` when a route needs a
    *specific* error `code` the status-code-only mapping above can't
    infer (a 422 that means `INSUFFICIENT_DATA` rather than a generic
    `VALIDATION_ERROR`, a 403 that means `TENANT_ACCESS_DENIED` rather
    than `AUTHORIZATION_DENIED`, a 403 that means `PRIVACY_BLOCKED`, a
    503 that means `MODEL_NOT_AVAILABLE`). Still a real `HTTPException`
    underneath — FastAPI's routing and any existing
    `except HTTPException` call site treats it identically; this only
    attaches `code`/`details` for `http_exception_handler()` below to
    surface."""

    def __init__(self, status_code: int, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.details = details


def _error_object(*, code: str, detail: Any, request_id: str | None, details: dict[str, Any] | None) -> dict:
    message = detail if isinstance(detail, str) else "Request failed."
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return error


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    code = getattr(exc, "code", None) or _STATUS_CODE_DEFAULTS.get(exc.status_code, "ERROR")
    details = getattr(exc, "details", None)
    body = {
        # Verbatim, whatever type it already is (str, dict, list) --
        # never re-typed to a string. This is the one field every
        # existing consumer of this codebase's API already reads.
        "detail": exc.detail,
        "error": _error_object(code=code, detail=exc.detail, request_id=request_id, details=details),
    }
    headers = getattr(exc, "headers", None)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    # Preserves FastAPI's own default `detail` shape (a list of per-field
    # errors) exactly -- existing consumers already parse this; `error`
    # is the additive part. `jsonable_encoder` matters here: when a
    # Pydantic model validator raises a plain `ValueError`, `exc.errors()`
    # embeds that raw exception object in each entry's `ctx.error` --
    # not JSON-serializable on its own (plain `json.dumps` raises
    # `TypeError`) -- exactly the encoding step FastAPI's own default
    # handler for this same exception type already applies.
    body = {
        "detail": jsonable_encoder(exc.errors()),
        "error": {
            "code": ErrorCode.VALIDATION_ERROR,
            "message": "Request validation failed.",
            "request_id": request_id,
        },
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last line of defense against ever leaking a stack trace, a
    database error message, a file path, or any other internal detail to
    a caller (item 15's own instruction) — every genuinely unexpected
    exception becomes exactly this one fixed, generic body, regardless of
    what the real exception actually was. The real exception still
    propagates to the ASGI server's own logging/observability
    (`app/core/observability.py` logs the request outcome either way) —
    this handler only controls what the *client* sees.
    """
    request_id = getattr(request.state, "request_id", None)
    body = {
        "detail": "An internal error occurred.",
        "error": {"code": ErrorCode.INTERNAL_ERROR, "message": "An internal error occurred.", "request_id": request_id},
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)


def register_exception_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
