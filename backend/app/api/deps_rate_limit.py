"""Rate-limit FastAPI dependency — wires `app/core/rate_limit.py`'s
abstraction into a route. Distinguishes read/write (item 13), keys on
the calling identity from `app/api/deps_context.py`'s `RequestContext`
(a machine client's own `client_id`, a human's own `user_id`) so one
noisy caller's budget never affects another's, and is itself tenant-
aware only in the sense that a client already can't act outside its own
organization (`RequestContext`/`deps_machine_auth.py` already enforce
that) — the limiter doesn't need to know about organizations at all.

    Depends(require_rate_limit(RateLimitClass.READ))
        -> RequestContext (human or machine, whichever already authenticated)
        -> LocalRateLimiter.check(f"{identity}:{class}", limit=..., window=60s)
        -> allowed -> continue, response gets X-RateLimit-* headers
        -> not allowed -> 429 RATE_LIMIT_EXCEEDED (app/core/errors.py::ApiError)

Off by default (`settings.RATE_LIMIT_ENABLED`) — see
`app/core/rate_limit.py`'s own docstring for why the in-memory
implementation is explicitly not multi-instance production-safe.
"""

from __future__ import annotations

import enum

from fastapi import Depends, Request

from app.api.deps_context import RequestContext, get_request_context
from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import get_rate_limiter


class RateLimitClass(str, enum.Enum):
    READ = "read"
    WRITE = "write"


def _limit_for(rate_limit_class: RateLimitClass) -> int:
    return (
        settings.RATE_LIMIT_READ_REQUESTS_PER_MINUTE
        if rate_limit_class == RateLimitClass.READ
        else settings.RATE_LIMIT_WRITE_REQUESTS_PER_MINUTE
    )


def require_rate_limit(rate_limit_class: RateLimitClass):
    """Dependency factory. Composable with, and independent of, any
    permission/scope dependency on the same route — rate limiting is a
    request-volume control, not an authorization decision, so it never
    replaces one."""

    def _dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        identity = context.identity_label
        key = f"{identity}:{rate_limit_class.value}"
        limit = _limit_for(rate_limit_class)

        result = get_rate_limiter().check(key, limit=limit, window_seconds=60.0)
        request.state.rate_limit_result = result  # surfaced as headers by AccessLogMiddleware-adjacent response, see below

        if not result.allowed:
            raise ApiError(
                status_code=429,
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message=f"Rate limit exceeded for {rate_limit_class.value} requests. Try again later.",
                details={"limit": result.limit, "reset_seconds": round(result.reset_seconds, 1)},
            )

    return _dependency
