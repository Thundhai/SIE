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


@pytest.fixture
def captured_records():
    """A fresh logger whose handler keeps the records themselves, plus the
    text an ordinary formatter (with `extra` and `exc_info` fields) makes
    of them."""
    install_log_redaction()
    logger = logging.getLogger(f"sie.test.records.{uuid.uuid4().hex}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Keep()
    logger.addHandler(handler)
    yield logger, records
    logger.removeHandler(handler)


def test_a_credential_split_between_template_and_argument_is_scrubbed(captured_records):
    logger, records = captured_records
    opaque = secrets.token_urlsafe(24)  # no recognisable shape on its own

    logger.info("Bearer %s", opaque)
    logger.warning("Authorization: %s", opaque)
    logger.error("sent %s %s", "Bearer", opaque)

    for record in records:
        assert opaque not in record.getMessage()
        assert REDACTED in record.getMessage()
    # Rendering never fails (a broken template would make logging print the
    # raw arguments to stderr).
    assert [r.getMessage() for r in records] == [
        f"Bearer {REDACTED}",
        f"Authorization: {REDACTED}",
        f"sent Bearer {REDACTED}",
    ]


def test_a_value_starting_with_b_is_fully_redacted():
    """The bytes-repr prefix (`b'...'`) is only a prefix before a quote."""
    for value in ("Bxyz123", "bxyz123"):
        assert redact(f"Authorization: {value}") == f"Authorization: {REDACTED}"
    assert redact("(b'authorization', b'Bearer abc')") == f"(b'authorization', b'{REDACTED}')"


def test_short_credentials_are_scrubbed_too():
    assert redact(f"Basic {_b64(b'u:p')}") == f"Basic {REDACTED}"
    assert redact("upstream said Bearer abc") == f"upstream said Bearer {REDACTED}"


def test_extra_fields_are_scrubbed_and_keep_their_shape(captured_records):
    logger, records = captured_records
    jwt = _jwt()
    client_id, secret = _machine_credential()

    logger.error(
        "embedding.failed",
        extra={
            "error": f"provider said Bearer {client_id}:{secret}",
            "details": {"headers": {"authorization": f"Bearer {jwt}"}, "attempts": [1, f"retry with {jwt}"]},
            "status_code": 401,
            "latency_ms": 12.5,
            "provider": "openai",
        },
    )

    record = records[0]
    assert record.error == f"provider said Bearer {REDACTED}"
    # A credential-named key is replaced outright (see the next test).
    assert record.details == {"headers": {"authorization": REDACTED}, "attempts": [1, f"retry with {REDACTED}"]}
    assert record.status_code == 401 and record.latency_ms == 12.5 and record.provider == "openai"
    rendered = logging.Formatter("%(message)s %(error)s %(details)s %(status_code)d").format(record)
    for fragment in (*_fragments(jwt), secret):
        assert fragment not in rendered


def test_fields_named_as_credentials_are_redacted_whatever_they_hold(captured_records):
    logger, records = captured_records
    opaque = secrets.token_urlsafe(24)  # no Bearer, JWT or query-string shape

    logger.info(
        "outbound call",
        extra={
            "token": opaque,
            "auth_token": opaque,
            "upstream": {"client_secret": opaque, "Authorization": opaque, "api_key": opaque, "Cookie": opaque},
            "password": "",  # empty stays empty
            # Not credentials, and kept as they are:
            "prompt_tokens": 120,
            "token_count": 7,
            "error_code": "UPSTREAM_TIMEOUT",
            "status_code": 504,
        },
    )
    logger.info("%(user)s used %(token)s", {"user": "svc", "token": opaque})

    extra = records[0]
    assert extra.token == REDACTED and extra.auth_token == REDACTED
    assert extra.upstream == {"client_secret": REDACTED, "Authorization": REDACTED, "api_key": REDACTED, "Cookie": REDACTED}
    assert extra.password == ""
    assert (extra.prompt_tokens, extra.token_count, extra.error_code, extra.status_code) == (120, 7, "UPSTREAM_TIMEOUT", 504)
    assert records[1].getMessage() == f"svc used {REDACTED}"
    rendered = logging.Formatter("%(message)s %(token)s %(upstream)s").format(extra)
    assert opaque not in rendered


def test_quoted_reprs_malformed_templates_camel_case_and_nesting_are_scrubbed(captured_records):
    logger, records = captured_records
    opaque = secrets.token_urlsafe(24)
    basic = base64.b64encode(b"user:" + secrets.token_bytes(12))

    logger.info("Bearer %r", opaque)  # Bearer '...'
    logger.info("Basic %s", basic)  # Basic b'...'
    logger.info("Bearer %d", opaque)  # a broken template
    logger.info("%(meta)s", {"meta": {"token": opaque}})
    logger.info("context %s", {"session": {"accessToken": opaque}})
    logger.info("outbound", extra={"accessToken": opaque, "clientSecret": opaque, "apiKey": opaque, "promptTokens": 3})

    for record in records[:5]:
        message = record.getMessage()  # never raises, so no formatting-error report
        assert opaque not in message and basic.decode() not in message, message
    extra = records[5]
    assert (extra.accessToken, extra.clientSecret, extra.apiKey, extra.promptTokens) == (REDACTED, REDACTED, REDACTED, 3)


def test_review_round_four_cases(captured_records):
    """Child loggers of uvicorn.access, deep nesting, structured messages,
    camelCase query parameters, and values that can't be compared."""
    logger, records = captured_records
    opaque = secrets.token_urlsafe(24)

    child = logging.getLogger(f"uvicorn.access.{uuid.uuid4().hex}")
    child.setLevel(logging.INFO)
    child.propagate = False
    child.handlers = logger.handlers
    child.info("Bearer %s", opaque)  # not Uvicorn's template: judged as rendered

    deep: dict = {"token": opaque}
    for _ in range(10):
        deep = {"layer": deep}
    logger.info("deep", extra={"payload": deep})
    logger.info({"token": opaque, "user": "svc"})
    logger.info(f"GET /x?api_key={opaque}&apiKey={opaque}&accessToken={opaque} HTTP/1.1")

    class Uncomparable:
        def __eq__(self, other):  # like a NumPy array: truthiness of == raises
            raise ValueError("ambiguous")

        __hash__ = object.__hash__

    logger.info("telemetry", extra={"token": Uncomparable()})

    child_record, deep_record, structured, query, uncomparable = records
    for record in (child_record, structured, query):
        assert opaque not in record.getMessage(), record.getMessage()
    assert opaque not in repr(deep_record.payload)
    assert "'user': 'svc'" in structured.getMessage()
    assert uncomparable.token == REDACTED


def test_the_raw_exception_does_not_stay_on_the_record(captured_records):
    logger, records = captured_records
    jwt = _jwt()

    try:
        raise RuntimeError(f"could not verify {jwt}")
    except RuntimeError:
        logger.exception("verification failed")

    record = records[0]
    assert record.exc_info is None
    assert "RuntimeError: could not verify [REDACTED]" in record.exc_text
    for fmt in ("%(message)s %(exc_info)s", "%(message)s"):
        rendered = logging.Formatter(fmt).format(record)
        assert "Traceback (most recent call last)" in rendered
        for fragment in _fragments(jwt):
            assert fragment not in rendered


def test_uvicorn_access_lines_are_scrubbed_and_still_format():
    """Uvicorn's access formatter unpacks the record's args and needs the
    status code as an int; redaction must leave both usable."""
    from uvicorn.logging import AccessFormatter

    install_log_redaction()
    jwt = _jwt()
    formatter = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False)
    template = '%s - "%s %s HTTP/%s" %d'

    def access_line(path: str, status: int) -> str:
        # Built through the record factory, as Uvicorn's own logger would;
        # the real "uvicorn.access" logger may be disabled by a fileConfig.
        record = logging.getLogRecordFactory()(
            "uvicorn.access", logging.INFO, __file__, 1, template, ("203.0.113.9:5000", "GET", path, "1.1", status), None
        )
        return formatter.format(record)

    out = "\n".join(
        (
            access_line(f"/api/v1/me?access_token={jwt}", 401),
            # A path that only looks like a credential once joined to the rest
            # of the line ("bearer HTTP/1.1") must not break the formatter.
            access_line("/files/bearer", 200),
        )
    )
    assert f'"GET /api/v1/me?access_token={REDACTED} HTTP/1.1" 401' in out
    assert '"GET /files/bearer HTTP/1.1" 200' in out
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
    monkeypatch.setattr(logging.Logger, "makeRecord", logging.Logger.makeRecord)  # restored after the test
    install_log_redaction()
    once, make_record_once = logging.getLogRecordFactory(), logging.Logger.makeRecord
    install_log_redaction()
    assert logging.getLogRecordFactory() is once
    assert logging.Logger.makeRecord is make_record_once

    record = logging.getLogRecordFactory()("n", logging.INFO, __file__, 1, f"Bearer {_jwt()}", None, None)
    assert record.getMessage() == f"Bearer {REDACTED}"
    assert seen == ["n"]


def test_the_application_installs_redaction():
    """Importing the entrypoint in a fresh interpreter installs redaction.

    A subprocess, because this process has long since imported `app.main`
    (and other tests here install redaction themselves), and re-importing
    it in place would build a second `app` that other tests then pick up."""
    import subprocess
    import sys
    from pathlib import Path

    probe = (
        "import logging, sys\n"
        f"assert not getattr(logging.getLogRecordFactory(), {log_redaction._MARKER!r}, False)\n"
        "import app.main\n"
        f"sys.exit(0 if getattr(logging.getLogRecordFactory(), {log_redaction._MARKER!r}, False) else 3)\n"
    )
    backend_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, "-c", probe], check=False, cwd=backend_dir, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
