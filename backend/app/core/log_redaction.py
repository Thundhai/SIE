"""Keep credentials out of every log line, tracebacks included.

The access log (`app/core/observability.py`) is built so it never records
a credential. This module is the backstop for everything else: error
logs, Uvicorn's own access and error loggers, tracebacks of unhandled
exceptions, and any future `logger.*` call that is handed a header,
an exception or a URL by mistake.

It works at the source. `install_log_redaction()` wraps the process-wide
`LogRecord` factory, so every record from every logger is scrubbed when
it is created: before any handler, formatter or capture sees it, and no
matter which handlers are attached now or later. It replaces:

* the value of an `Authorization` header, in any common rendering
  (`Authorization: …`, `"authorization": "…"`, `(b'authorization', b'…')`)
* `Bearer …` and `Basic …` credentials, which covers OIDC access tokens
  and machine credentials (`<client_id>:<secret>`)
* anything JWT-shaped (`eyJ….….…`)
* SIE one-time codes (`sie_link_…`)
* credential-like query parameters (`?access_token=…`, `&code=…`, …)

What stays: messages, logger names, levels, request IDs, methods, paths,
status codes, latencies and other numbers. Numbers and `None` are never
touched, so formatters that need them (Uvicorn's access formatter reads
the status code as an int) keep working.

Redaction is a safety net, not a licence: code must still never log a
credential on purpose.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # The value of an Authorization header, however it is rendered.
    (
        re.compile(r"""(?i)(\bauthorization['"]?\s*[:=,]\s*b?['"]?)[^'"\r\n]+"""),
        rf"\1{REDACTED}",
    ),
    # Bearer / Basic credentials anywhere else.
    (re.compile(r"(?i)\b(bearer|basic)(\s+)[A-Za-z0-9._~+/=:-]{8,}"), rf"\1\2{REDACTED}"),
    # JWT-shaped values (JWS and JWE both start with a base64url '{"').
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)*"), REDACTED),
    # SIE one-time codes (account links and invitations).
    (re.compile(r"\b(sie_(?:link|inv|invite)_)[A-Za-z0-9_-]+"), rf"\1{REDACTED}"),
    # Credential-like query parameters.
    (
        re.compile(
            r"(?i)([?&](?:access_token|id_token|refresh_token|token|code|client_secret|secret|password)=)"
            r"[^&\s'\"#]+"
        ),
        rf"\1{REDACTED}",
    ),
)

_EXCEPTION_FORMATTER = logging.Formatter()
_MARKER = "_sie_log_redaction"


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact(value)
    try:
        rendered = value.decode("utf-8", "replace") if isinstance(value, (bytes, bytearray)) else str(value)
    except Exception:  # noqa: BLE001 - formatting would fail the same way later; leave it
        return value
    scrubbed = redact(rendered)
    return value if scrubbed == rendered else scrubbed


def redact_record(record: logging.LogRecord) -> logging.LogRecord:
    record.msg = _redact_value(record.msg)
    if isinstance(record.args, Mapping):
        record.args = {key: _redact_value(value) for key, value in record.args.items()}
    elif isinstance(record.args, tuple):
        record.args = tuple(_redact_value(arg) for arg in record.args)
    if record.exc_info and record.exc_info[0] is not None:
        # Formatters reuse `exc_text` when it is set, so the traceback (and
        # every chained exception's message) is only ever rendered scrubbed.
        record.exc_text = redact(_EXCEPTION_FORMATTER.formatException(record.exc_info))
    if record.stack_info:
        record.stack_info = redact(record.stack_info)
    return record


def install_log_redaction() -> None:
    """Idempotent. Call once, as early as possible, in each entrypoint."""
    current = logging.getLogRecordFactory()
    if getattr(current, _MARKER, False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        return redact_record(current(*args, **kwargs))

    setattr(factory, _MARKER, True)
    logging.setLogRecordFactory(factory)
