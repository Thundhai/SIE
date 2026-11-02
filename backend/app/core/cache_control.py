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

# /api/v1/invitations/...                      public inspect / start
# /api/v1/auth/invitations/...                 acceptance
# /api/v1/organizations/{id}/invitations...    administration
# /api/v1/identity-links, /auth/identity-links  account-link grants
_NO_STORE_PATH = re.compile(
    r"^/api/v1/(?:auth/)?(?:invitations|identity-links)(?:/|$)"
    r"|^/api/v1/organizations/[^/]+/invitations(?:/|$)"
)


def is_no_store_path(path: str) -> bool:
    return _NO_STORE_PATH.match(path) is not None


class NoStoreMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_no_store_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_no_store)
