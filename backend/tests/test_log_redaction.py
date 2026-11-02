"""Credentials never reach a log line or an error response.

Covers the access log (`app/core/observability.py`), the process-wide
record redaction (`app/core/log_redaction.py`) that backs every other
logger and every traceback, and the error bodies a caller gets back.

Token-shaped values are built at runtime so no credential-shaped literal
sits in the source (gitleaks).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import secrets
import uuid

import pytest

from app.core import log_redaction, observability
from app.core.log_redaction import REDACTED, install_log_redaction, redact


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _jwt() -> str:
    return ".".join(
        (_b64(b'{"alg":"RS256","typ":"JWT"}'), _b64(b'{"sub":"person","iss":"https://idp"}'), _b64(secrets.token_bytes(32)))
    )


def _machine_credential() -> tuple[str, str]:
    return f"sie_{secrets.token_hex(12)}", secrets.token_urlsafe(32)


def _fragments(jwt: str) -> tuple[str, ...]:
    return tuple(jwt.split("."))


# --- the access log --------------------------------------------------------


@pytest.fixture
def access_lines(monkeypatch) -> list[dict]:
    """The access logger's calls, captured directly. Alembic's fileConfig
    (run by the migration tests) disables existing loggers, so caplog
    can't be relied on in a full run."""
    lines: list[str] = []
    monkeypatch.setattr(observability.access_logger, "info", lambda message, *a, **k: lines.append(message))

    class _Parsed(list):
        @property
        def raw(self) -> str:
            return "\n".join(lines)

    parsed = _Parsed()

    def snapshot() -> _Parsed:
        parsed[:] = [json.loads(line) for line in lines]
        return parsed

    parsed.snapshot = snapshot  # type: ignore[attr-defined]
    return parsed


def test_access_log_never_contains_a_bearer_token_and_keeps_its_metadata(client, access_lines):
    jwt = _jwt()
    client_id, secret = _machine_credential()

    first = client.get("/api/v1/me", headers={"Authorization": f"Bearer {jwt}"})
    second = client.get(
        f"/api/v1/intelligence/analytics/summary?organization_id={uuid.uuid4()}",
        headers={"Authorization": f"Bearer {client_id}:{secret}"},
    )

    entries = access_lines.snapshot()
    raw = access_lines.raw
    for fragment in (*_fragments(jwt), secret):
        assert fragment not in raw
    assert "authorization" not in raw.lower()

    by_path = {entry["path"]: entry for entry in entries}
    person = by_path["/api/v1/me"]
    machine = by_path["/api/v1/intelligence/analytics/summary"]
    assert person["client"] == "user_token"
    assert machine["client"] == f"api_client:{client_id}"

    # Operational metadata survives: method, path, status, latency, and the
    # request id the caller was given.
    for entry, response in ((person, first), (machine, second)):
        assert entry["method"] == "GET"
        assert entry["status_code"] == response.status_code
        assert isinstance(entry["latency_ms"], float)
        assert entry["request_id"] == response.headers["X-Request-Id"]
    # The query string (which could carry anything) is not part of the line.
    assert "organization_id" not in raw


def test_caller_identity_labels_without_secrets():
    from starlette.requests import Request

    from app.core.observability import _caller_identity

    def req(authorization: str | None) -> Request:
        headers = [] if authorization is None else [(b"authorization", authorization.encode())]
        return Request({"type": "http", "headers": headers})

    assert _caller_identity(req("Bearer eyJ.abc.def")) == "user_token"
    assert _caller_identity(req("Bearer cid:secret")) == "api_client:cid"
    assert _caller_identity(req("Bearer :secret")) == "user_token"
    assert _caller_identity(req("Bearer ")) is None
    assert _caller_identity(req("Basic abc")) is None
    assert _caller_identity(req(None)) is None


# --- error responses -------------------------------------------------------


def test_error_responses_never_echo_the_credential(client):
    jwt = _jwt()
    client_id, secret = _machine_credential()

    responses = [
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {jwt}"}),
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {jwt[:-4]}"}),  # broken signature
        client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt-but-secret-ish"}),
        client.get(
            f"/api/v1/intelligence/analytics/summary?organization_id={uuid.uuid4()}",
            headers={"Authorization": f"Bearer {client_id}:{secret}"},
        ),
    ]
    for response in responses:
        assert response.status_code >= 400
        body = response.text
        for fragment in (*_fragments(jwt), secret, "not-a-jwt-but-secret-ish"):
            assert fragment not in body
        assert response.json()["error"]["request_id"] == response.headers["X-Request-Id"]


# --- redact() --------------------------------------------------------------


def test_redact_covers_every_common_rendering():
    jwt = _jwt()
    client_id, secret = _machine_credential()
    code = "sie_link_" + secrets.token_urlsafe(32)
    cases = [
        f"Authorization: Bearer {jwt}",
        f"authorization={jwt}",
        f'{{"authorization": "Bearer {jwt}", "x-request-id": "abc"}}',
        f"{{'Authorization': 'Bearer {client_id}:{secret}'}}",
        f"[(b'host', b'api'), (b'authorization', b'Bearer {jwt}')]",
        f"upstream said: bearer {client_id}:{secret}",
        f"Basic {_b64(b'user:' + secret.encode())}",
        f"verification failed for {jwt}",
        f"redeeming {code}",
        f"GET /callback?state=x&code={secret}&next=/ HTTP/1.1",
        f"GET /x?access_token={jwt} HTTP/1.1",
    ]
    for case in cases:
        scrubbed = redact(case)
        assert REDACTED in scrubbed, case
        for fragment in (*_fragments(jwt), secret, code[len("sie_link_") :]):
            assert fragment not in scrubbed, (case, scrubbed)


def test_redact_keeps_ordinary_operational_text():
    request_id = uuid.uuid4().hex
    for text in (
        f"request_id={request_id} GET /api/v1/organizations 200 12.5ms",
        "Missing or malformed Authorization header (expected 'Bearer <client_id>:<secret>').",
        "commercial_core.summary.authorization_failed",
        "Token signature is invalid.",
        "GET /api/v1/knowledge/sources?organization_id=5 HTTP/1.1",
    ):
        assert redact(text) == text


# --- every logger, every traceback ----------------------------------------


@pytest.fixture
def captured_logger():
    """A fresh logger (never disabled by a fileConfig) writing to a buffer
    through an ordinary formatter."""
    install_log_redaction()
    logger = logging.getLogger(f"sie.test.redaction.{uuid.uuid4().hex}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    yield logger, buffer
    logger.removeHandler(handler)


def test_every_log_record_is_scrubbed_at_creation(captured_logger):
    logger, buffer = captured_logger
    jwt = _jwt()
    client_id, secret = _machine_credential()
    request_id = uuid.uuid4().hex

    logger.info(f"request {request_id} Authorization: Bearer {jwt}")
    logger.warning("headers were %s", {"authorization": f"Bearer {client_id}:{secret}", "x-request-id": request_id})
    logger.error("status=%d id=%s token=%s", 401, request_id, jwt)
    logger.error("%(who)s sent %(what)s", {"who": "caller", "what": f"Bearer {jwt}"})
    logger.debug("stack check %s", jwt, stack_info=True)

    out = buffer.getvalue()
    for fragment in (*_fragments(jwt), secret):
        assert fragment not in out
    # Useful context is untouched.
    assert out.count(request_id) == 3
    assert "status=401" in out
    assert "caller sent Bearer [REDACTED]" in out


def test_a_traceback_never_carries_a_token(captured_logger):
    logger, buffer = captured_logger
    jwt = _jwt()
    client_id, secret = _machine_credential()

    try:
        try:
            raise ValueError(f"upstream rejected Bearer {client_id}:{secret}")
        except ValueError as inner:
            raise RuntimeError(f"could not verify {jwt}") from inner
    except RuntimeError as exc:
        # Exactly how Uvicorn reports an unhandled exception from the app.
        logger.error("Exception in ASGI application\n", exc_info=exc)
        logger.exception("and once more via exception()")

    out = buffer.getvalue()
    assert "Traceback (most recent call last)" in out
    assert "RuntimeError: could not verify [REDACTED]" in out
    assert "ValueError: upstream rejected Bearer [REDACTED]" in out
    for fragment in (*_fragments(jwt), secret):
        assert fragment not in out


def test_uvicorn_access_lines_are_scrubbed_and_still_format():
    """Uvicorn's access formatter unpacks the record's args and needs the
    status code as an int; redaction must leave both usable."""
    from uvicorn.logging import AccessFormatter

    install_log_redaction()
    jwt = _jwt()
    logger = logging.getLogger(f"uvicorn.access.test.{uuid.uuid4().hex}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False))
    logger.addHandler(handler)
    try:
        logger.info(
            '%s - "%s %s HTTP/%s" %d', "203.0.113.9:5000", "GET", f"/api/v1/me?access_token={jwt}", "1.1", 401
        )
    finally:
        logger.removeHandler(handler)

    out = buffer.getvalue()
    assert f'"GET /api/v1/me?access_token={REDACTED} HTTP/1.1" 401' in out
    for fragment in _fragments(jwt):
        assert fragment not in out


def test_install_is_idempotent_and_keeps_the_previous_factory(monkeypatch):
    seen: list[str] = []
    base = logging.getLogRecordFactory()

    def previous(*args, **kwargs):
        record = base(*args, **kwargs)
        seen.append(record.name)
        return record

    monkeypatch.setattr(logging, "_logRecordFactory", previous)  # restored after the test
    install_log_redaction()
    once = logging.getLogRecordFactory()
    install_log_redaction()
    assert logging.getLogRecordFactory() is once

    record = logging.getLogRecordFactory()("n", logging.INFO, __file__, 1, f"Bearer {_jwt()}", None, None)
    assert record.getMessage() == f"Bearer {REDACTED}"
    assert seen == ["n"]


def test_the_application_installs_redaction(monkeypatch):
    """Loading the entrypoint, starting from a plain factory (other tests in
    this module install redaction themselves), must install it."""
    import importlib

    import app.main

    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)  # restored after the test
    assert not getattr(logging.getLogRecordFactory(), log_redaction._MARKER, False)
    importlib.reload(app.main)
    assert getattr(logging.getLogRecordFactory(), log_redaction._MARKER, False) is True
