"""Auth0 Management API client for administrator-added users
(app/services/user_provisioning_service.py).

Only what that flow needs:

* look a database-connection user up by email, or by id
* create a database-connection user, tagged `app_metadata.sie_provisioned`
* ask Auth0 to email that person a set-password link

Authentication is the client-credentials grant of a machine-to-machine
application (`AUTH0_MANAGEMENT_CLIENT_ID`/`_SECRET`, scopes `read:users`
and `create:users`). Its token is cached until shortly before it expires.
The client secret, the token and email addresses are never logged.

Every failure, whether network, timeout, non-2xx or an unexpected body,
raises `Auth0ManagementError`. Callers treat it as "Auth0 is unavailable"
and fail closed.
"""

from __future__ import annotations

import re
import secrets
import string
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import settings

_TIMEOUT_SECONDS = 10.0
# Refresh the cached token this long before Auth0 says it expires.
_TOKEN_EXPIRY_MARGIN_SECONDS = 60.0


class Auth0ManagementError(Exception):
    """Auth0 could not be reached or gave an unusable answer. The message
    is safe to log: it never contains a secret, a token or an email."""


@dataclass(frozen=True)
class Auth0User:
    user_id: str
    email: str | None
    email_verified: bool
    # True only for accounts SIE itself created (`app_metadata` is not
    # writable by the user, only through the Management API).
    sie_provisioned: bool


def _user_from(body: dict) -> Auth0User:
    user_id = body.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise Auth0ManagementError("Auth0 returned a user without a user_id.")
    email = body.get("email")
    app_metadata = body.get("app_metadata") if isinstance(body.get("app_metadata"), dict) else {}
    return Auth0User(
        user_id=user_id,
        email=email.strip().lower() if isinstance(email, str) and email.strip() else None,
        email_verified=body.get("email_verified") is True,
        sie_provisioned=app_metadata.get("sie_provisioned") is True,
    )


def random_initial_password() -> str:
    """A long random password nobody is told. The person sets their own
    through the emailed link. It satisfies Auth0's strictest built-in
    policy: all four character classes, and no character three times in a row."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(40))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in "!@#$%^&*-_=+" for c in candidate)
            and not re.search(r"(.)\1\1", candidate)
        ):
            return candidate


class Auth0ManagementClient:
    def __init__(
        self,
        *,
        domain: str,
        client_id: str,
        client_secret: str,
        connection: str,
        password_email_client_id: str,
        http: httpx.Client | None = None,
    ) -> None:
        self._base = f"https://{domain.strip()}"
        self._client_id = client_id
        self._client_secret = client_secret
        self._connection = connection
        self._password_email_client_id = password_email_client_id
        self._http = http or httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=False)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    # --- transport ---------------------------------------------------------------------

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token
            body = self._send(
                "POST",
                "/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "audience": f"{self._base}/api/v2/",
                },
                authenticated=False,
            )
            token = body.get("access_token") if isinstance(body, dict) else None
            if not isinstance(token, str) or not token:
                raise Auth0ManagementError("Auth0 returned no Management API token.")
            expires_in = body.get("expires_in")
            lifetime = float(expires_in) if isinstance(expires_in, int | float) and expires_in > 0 else 300.0
            self._token = token
            self._token_expires_at = time.monotonic() + max(lifetime - _TOKEN_EXPIRY_MARGIN_SECONDS, 30.0)
            return token

    def _send(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        authenticated: bool = True,
        expect: tuple[int, ...] = (200, 201),
        allow: tuple[int, ...] = (),
    ):
        headers = {"Authorization": f"Bearer {self._access_token()}"} if authenticated else {}
        try:
            response = self._http.request(method, f"{self._base}{path}", json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise Auth0ManagementError(f"Auth0 request failed: {type(exc).__name__}.") from None
        if response.status_code in allow:
            return response.status_code
        if response.status_code == 401 and authenticated:
            with self._lock:
                self._token = None  # an expired or revoked token: fetch a fresh one next time
        if response.status_code not in expect:
            # The route only: never a query string (emails) or a user id.
            route = re.sub(r"^/api/v2/users/.+$", "/api/v2/users/{id}", path.split("?")[0])
            raise Auth0ManagementError(f"Auth0 answered {method} {route} with HTTP {response.status_code}.")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            # The change_password endpoint answers with a plain-text sentence.
            return {}

    # --- users -------------------------------------------------------------------------

    def find_user_by_email(self, email: str) -> Auth0User | None:
        """The database-connection user with this email, if any. Users of
        other connections (Google, enterprise SSO) are ignored: they are
        different accounts that SIE never binds by email."""
        body = self._send("GET", "/api/v2/users-by-email", params={"email": email.strip().lower()})
        if not isinstance(body, list):
            raise Auth0ManagementError("Auth0 users-by-email returned an unexpected body.")
        for item in body:
            if not isinstance(item, dict):
                continue
            identities = item.get("identities") if isinstance(item.get("identities"), list) else []
            if any(isinstance(i, dict) and i.get("connection") == self._connection for i in identities):
                return _user_from(item)
        return None

    def get_user(self, user_id: str) -> Auth0User | None:
        result = self._send("GET", f"/api/v2/users/{quote(user_id, safe='')}", allow=(404,))
        if result == 404:
            return None
        if not isinstance(result, dict):
            raise Auth0ManagementError("Auth0 get-user returned an unexpected body.")
        return _user_from(result)

    def create_user(self, email: str, name: str | None) -> Auth0User:
        payload: dict = {
            "connection": self._connection,
            "email": email.strip().lower(),
            "password": random_initial_password(),
            "email_verified": False,
            "verify_email": False,
            "app_metadata": {"sie_provisioned": True},
        }
        if name:
            payload["name"] = name[:300]
        result = self._send("POST", "/api/v2/users", json=payload, allow=(409,))
        if result == 409:
            # Created a moment ago by a concurrent request: use that account.
            existing = self.find_user_by_email(email)
            if existing is None:
                raise Auth0ManagementError("Auth0 reported the user exists but did not return it.")
            return existing
        if not isinstance(result, dict):
            raise Auth0ManagementError("Auth0 create-user returned an unexpected body.")
        return _user_from(result)

    def send_set_password_email(self, email: str) -> None:
        """Auth0 emails a link to set (reset) the account's password. The
        link also marks the email verified once used."""
        self._send(
            "POST",
            "/dbconnections/change_password",
            json={
                "client_id": self._password_email_client_id,
                "email": email.strip().lower(),
                "connection": self._connection,
            },
            authenticated=False,
            expect=(200,),
        )


_client: Auth0ManagementClient | None = None
_client_lock = threading.Lock()


def _build_from_settings() -> Auth0ManagementClient | None:
    if not settings.auth0_management_configured:
        return None
    global _client
    with _client_lock:
        if _client is None:
            _client = Auth0ManagementClient(
                domain=settings.AUTH0_MANAGEMENT_DOMAIN or "",
                client_id=settings.AUTH0_MANAGEMENT_CLIENT_ID or "",
                client_secret=settings.AUTH0_MANAGEMENT_CLIENT_SECRET or "",
                connection=settings.AUTH0_DB_CONNECTION,
                password_email_client_id=settings.AUTH0_PASSWORD_EMAIL_CLIENT_ID or "",
            )
        return _client


#: Replaced in tests with a fake. Returns None when adding users isn't configured.
get_auth0_management_client: Callable[[], Auth0ManagementClient | None] = _build_from_settings
