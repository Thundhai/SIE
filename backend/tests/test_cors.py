"""CORS configuration — SIE Enterprise Read API & Browser Integration
Foundation v0.1 (§11). `CORSMiddleware` (`app/main.py`) is configured
from `settings.CORS_ALLOWED_ORIGINS` (`app/core/config.py`); this file
tests it directly through the real `TestClient`/`app` stack (not by
inspecting the middleware config), the same way
`docs/ENTERPRISE_API.md` §4 was verified against a real running server.

Note: TestClient's default host is `testserver`, so every request here
already carries a *different* Origin than `testserver` — the middleware
would 401/403 on its own auth logic regardless of CORS, which is exactly
why these tests check headers on the response rather than status codes
alone for the non-preflight cases (an unauthenticated 401 still must
carry the right CORS headers, or a browser reports a misleading "CORS
error" that masks the real one -- see app/main.py's own comment).
"""

from app.core.config import settings

_ALLOWED_ORIGIN = "http://localhost:3000"
_DISALLOWED_ORIGIN = "http://evil.example.com"


def test_allowed_origins_are_configured_and_never_a_wildcard():
    assert _ALLOWED_ORIGIN in settings.cors_allowed_origins_list
    assert "*" not in settings.cors_allowed_origins_list


def test_preflight_from_an_allowed_origin_succeeds(client):
    response = client.options(
        "/api/v1/events",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_from_a_disallowed_origin_is_refused(client):
    response = client.options(
        "/api/v1/events",
        headers={
            "Origin": _DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_a_real_response_from_an_allowed_origin_carries_cors_headers_even_on_error(client):
    """The CORS header must be present on every response an inner layer
    produces -- including a 401 -- not only on a successful 200,
    confirming CORSMiddleware is genuinely the outermost layer."""
    response = client.get("/api/v1/events", headers={"Origin": _ALLOWED_ORIGIN})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN


def test_a_real_response_from_a_disallowed_origin_carries_no_cors_header(client):
    response = client.get("/api/v1/events", headers={"Origin": _DISALLOWED_ORIGIN})

    assert "access-control-allow-origin" not in response.headers


def test_a_request_with_no_origin_header_is_unaffected(client):
    """A same-origin/non-browser request (no Origin header at all, e.g. a
    machine client or curl) is not a CORS request in the first place --
    CORSMiddleware only ever acts on requests that carry Origin."""
    response = client.get("/api/v1/events")

    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers
