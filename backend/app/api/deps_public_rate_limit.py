"""Per-client-IP rate limit for the invitation endpoints, including the
public ones a caller reaches before signing in.

Always on (`INVITATION_RATE_LIMIT_PER_MINUTE`), independent of the
identity-keyed `RATE_LIMIT_ENABLED` limiter, because these routes run
before, or without, an identity. It uses the same process-local limiter
(app/core/rate_limit.py): exact on today's single instance, but each
instance counts on its own if the service is scaled out.

The client address is the socket peer unless `TRUSTED_PROXY_HOPS` says
how many proxies append to X-Forwarded-For (3 on Render: Cloudflare's
edge, then Render's internal proxy, append after the client). The value
`TRUSTED_PROXY_HOPS` entries from the right is used, so a client cannot
spoof its address by sending its own X-Forwarded-For.
"""

from __future__ import annotations

import math

from fastapi import Request

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.core.rate_limit import get_rate_limiter


def client_ip(request: Request) -> str:
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        chain = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "unknown"


def require_invitation_rate_limit(bucket: str):
    def _dependency(request: Request) -> None:
        limit = settings.INVITATION_RATE_LIMIT_PER_MINUTE
        if limit <= 0:
            return
        result = get_rate_limiter().check(f"invitation:{bucket}:{client_ip(request)}", limit=limit, window_seconds=60.0)
        if not result.allowed:
            error = ApiError(
                status_code=429,
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message="Too many invitation requests. Try again shortly.",
                details={"reset_seconds": round(result.reset_seconds, 1)},
            )
            error.headers = {"Retry-After": str(max(1, math.ceil(result.reset_seconds)))}
            raise error

    return _dependency
