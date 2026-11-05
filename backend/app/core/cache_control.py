"""`Cache-Control: no-store` for the invitation and identity-link routes.

These responses carry one-time codes, invited email addresses, lifecycle
details and refusal reasons. A browser or intermediary must never keep
them, including after sign-out. The header is set here, at the ASGI
layer, rather than in each handler, so it also covers every error
response (422 validation, 401/403 from the auth dependencies, 404, 409,
429 and the error handler's own JSON), which never pass through a
handler's `Response`.
"""

from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# <prefix>/invitations/...                      public inspect / start
# <prefix>/auth/invitations/...                 acceptance
# <prefix>/organizations/{id}/invitations...    administration
# <prefix>/identity-links, /auth/identity-links  account-link grants
# <prefix> is the configured API_V1_PREFIX the router is mounted at.


def _matcher(prefix: str) -> re.Pattern[str]:
    p = re.escape(prefix.rstrip("/"))
    return re.compile(
        rf"^{p}/(?:auth/)?(?:invitations|identity-links)(?:/|$)" rf"|^{p}/organizations/[^/]+/invitations(?:/|$)"
    )


def is_no_store_path(path: str, prefix: str | None = None) -> bool:
    return _matcher(settings.API_V1_PREFIX if prefix is None else prefix).match(path) is not None


class NoStoreMiddleware:
    def __init__(self, app: ASGIApp, prefix: str | None = None) -> None:
        self.app = app
        self._pattern = _matcher(settings.API_V1_PREFIX if prefix is None else prefix)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._pattern.match(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_no_store)
