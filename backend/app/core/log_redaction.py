"""Keep credentials out of every log line, tracebacks included.

The access log (`app/core/observability.py`) is built so it never records
a credential. This module is the backstop for everything else: error
logs, Uvicorn's own access and error loggers, tracebacks of unhandled
exceptions, and any future `logger.*` call that is handed a header,
an exception or a URL by mistake.

`install_log_redaction()` scrubs every record at the source, before any
handler, formatter or capture sees it, whichever handlers exist now or
are added later. It hooks two places:

* the process-wide `LogRecord` factory, which every record goes through
* `Logger.makeRecord`, because the fields a call passes in `extra=` are
  attached to the record only after the factory has returned

On each record it scrubs:

* the message, judged as it will be rendered (template and arguments
  together), so a credential split between them (`"Bearer %s", token`)
  is caught too
* each argument, keeping numbers and `None` as they are. Uvicorn's own
  access record (that exact logger and template) keeps its arguments as
  arguments, because its formatter unpacks them and reads the status code
  as an int; its joined line is also checked, so a credential split
  across two fields is caught (`_redact_uvicorn_access`)
* a structured message (a dict or list passed as the message) key by key;
  structures nested deeper than the inspection limit are replaced whole
* every `extra` field, recursively through dicts, lists and tuples. A
  field (or dict key, or `%(name)s` argument) whose name says it is a
  credential (`token`, `client_secret`, `password`, `authorization`,
  `api_key`, `cookie`, ...) is replaced outright, whatever its value
  looks like
* the traceback and every chained exception message. The scrubbed
  traceback is stored in `exc_text`, which standard formatters print,
  and the raw exception objects are dropped from the record, so nothing
  can render the unscrubbed original later
* `stack_info`

What it replaces:

* the value of an `Authorization` header, in any common rendering
  (`Authorization: …`, `"authorization": "…"`, `(b'authorization', b'…')`)
* `Bearer …` and `Basic …` credentials of any length, which covers OIDC
  access tokens and machine credentials (`<client_id>:<secret>`)
* anything JWT-shaped (`eyJ….….…`)
* SIE one-time codes (`sie_link_…`)
* credential-like query parameters (`?access_token=…`, `&code=…`, …)

Messages, logger names, levels, request IDs, methods, paths, status codes
and other numbers are left alone.

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
        re.compile(r"""(?i)(\bauthorization['"]?\s*[:=,]\s*(?:b(?=['"]))?['"]?)[^'"\r\n]+"""),
        rf"\1{REDACTED}",
    ),
    # Bearer / Basic credentials anywhere else, whatever their length, and
    # also as a quoted str or bytes repr (`Bearer 'x'`, `Basic b'x'`).
    (
        re.compile(r"""(?i)\b(bearer|basic)(\s+)(?:b?(['"])[^'"\r\n]+\3|[A-Za-z0-9._~+/=:-]+)"""),
        rf"\1\2{REDACTED}",
    ),
    # JWT-shaped values (JWS and JWE both start with a base64url '{"').
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)*"), REDACTED),
    # SIE one-time codes (account links and invitations).
    (re.compile(r"\b(sie_(?:link|inv|invite)_)[A-Za-z0-9_-]+"), rf"\1{REDACTED}"),
    # Credential-like query parameters.
    (
        re.compile(
            r"(?i)([?&](?:access_?token|id_?token|refresh_?token|auth_?token|token|code|client_?secret|secret|"
            r"password|passwd|api_?key|access_?key|session_?id|signature|sig)=)"
            r"[^&\s'\"#]+"
        ),
        rf"\1{REDACTED}",
    ),
)

_EXCEPTION_FORMATTER = logging.Formatter()
_MARKER = "_sie_log_redaction"
_MAX_DEPTH = 6
# Attributes every LogRecord has; anything else on a record came from `extra`.
_STANDARD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
# Uvicorn's access record: its formatter unpacks the arguments (and reads
# the status code as an int), and its template is fixed, so no credential
# can sit in it. Only a record with exactly this logger name AND this
# template keeps its (individually scrubbed) arguments; anything else,
# a child logger included, is judged as rendered like every other record.
_UVICORN_ACCESS_LOGGER = "uvicorn.access"
_UVICORN_ACCESS_TEMPLATE = '%s - "%s %s HTTP/%s" %d'
# The shape of the fields Uvicorn itself puts on that record. Only the
# client address and the path are free text; the method, HTTP version and
# status are constrained. See `_redact_uvicorn_access`.
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})
_HTTP_VERSION = re.compile(r"^\d(?:\.\d)?$")
_CLIENT_ADDR = re.compile(r"^[^\s'\"]*$")
# Field names that say their value is a credential, whatever it looks like
# (an opaque token has no recognisable shape): `token`, `auth_token`,
# `client_secret`, `password`, `authorization`, `api_key`, `cookie`, ...
# Deliberately not `*_tokens` / `token_count` (LLM usage metrics) or
# `*_code` (`error_code`, `status_code`).
# Names are compared in snake_case, so camelCase (`accessToken`,
# `clientSecret`, `apiKey`) and kebab-case are recognised too.
_CREDENTIAL_KEY = re.compile(
    r"^(?:.*_)?(?:token|secret|password|passwd|authorization|api_?key|credentials?|cookie|set_cookie|session_?id)$"
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value: Any) -> Any:
    """A scalar: strings are scrubbed, numbers and None kept as they are,
    anything else replaced by its scrubbed text only if that text held a
    credential."""
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


def _is_credential_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalised = _CAMEL_BOUNDARY.sub("_", key).replace("-", "_").lower()
    return _CREDENTIAL_KEY.match(normalised) is not None


def _is_empty(value: Any) -> bool:
    # Identity and type checks only: `==` on an arbitrary object (a NumPy
    # array, say) can raise while the record is being built.
    return value is None or (isinstance(value, (str, bytes, bytearray)) and len(value) == 0)


def _redact_named(key: Any, value: Any, depth: int) -> Any:
    """A field's value; a field whose name says it is a credential is
    replaced outright (unless it is empty), whatever its shape."""
    if _is_credential_key(key) and not _is_empty(value):
        return REDACTED
    return _redact_structure(value, depth)


def _redact_structure(value: Any, depth: int = 0) -> Any:
    """Like `_redact_value`, but keeps the shape of dicts, lists and tuples
    (structured `extra` fields) and scrubs inside them."""
    if isinstance(value, (Mapping, list, tuple)):
        if depth >= _MAX_DEPTH:
            # Too deep to inspect key by key: fail closed rather than fall
            # back to text patterns that can't see a credential-named key.
            return REDACTED
        if isinstance(value, Mapping):
            return {key: _redact_named(key, item, depth + 1) for key, item in value.items()}
        items = [_redact_structure(item, depth + 1) for item in value]
        return items if isinstance(value, list) else tuple(items)
    return _redact_value(value)


def _redact_uvicorn_access(record: logging.LogRecord) -> bool:
    """Uvicorn's access line, checked whole. Returns False when the record
    isn't usable as an access record, so the caller treats it like any
    other record.

    Each argument has already been scrubbed on its own. A credential can
    still be split across two fields and only appear once the formatter
    joins them, so the joined line is checked too:

    * no credential in the joined line: the record is kept as it is.
    * a credential, and every field has the shape Uvicorn gives it (a
      standard method, a numeric HTTP version, an int status, a client
      address with no space or quote): kept as it is. With those shapes
      the only pattern that can cross a field boundary is a path ending in
      "bearer"/"basic" running into the template's own " HTTP/1.1", which
      carries no secret: the method, version and status can't hold one,
      and the template's spaces and quotes stop every other pattern.
      So `/files/bearer` stays visible.
    * a credential and any other shape (a forged record): every text
      field is replaced, keeping the status code, so the formatter still
      works and nothing of the credential is emitted.
    """
    args = record.args
    if not (isinstance(args, tuple) and len(args) == 5 and isinstance(args[4], int)):
        return False
    try:
        line = _UVICORN_ACCESS_TEMPLATE % args
    except Exception:  # noqa: BLE001 - not a usable access record
        return False
    if redact(line) == line:
        return True
    client_addr, method, _path, http_version, status = args
    genuine = (
        isinstance(client_addr, str)
        and _CLIENT_ADDR.match(client_addr) is not None
        and method in _HTTP_METHODS
        and isinstance(http_version, str)
        and _HTTP_VERSION.match(http_version) is not None
    )
    if not genuine:
        record.args = (REDACTED, REDACTED, REDACTED, REDACTED, status)
    return True


def _redact_message(record: logging.LogRecord) -> None:
    # Key-aware and recursive, so a nested `{"token": ...}` is caught too.
    if isinstance(record.args, Mapping):
        record.args = {key: _redact_named(key, value, 1) for key, value in record.args.items()}
    elif isinstance(record.args, tuple):
        record.args = tuple(_redact_structure(arg, 1) for arg in record.args)

    if (
        record.name == _UVICORN_ACCESS_LOGGER
        and record.msg == _UVICORN_ACCESS_TEMPLATE
        and _redact_uvicorn_access(record)
    ):
        return
    # A structured message (`logger.info({"token": t})`) is scrubbed key by
    # key before it is ever turned into text.
    if isinstance(record.msg, (Mapping, list, tuple)):
        record.msg = _redact_structure(record.msg, 1)
    try:
        rendered = record.getMessage()
    except Exception:  # noqa: BLE001 - a broken format ("Bearer %d", token)
        # Without the template an opaque argument can't be recognised, and
        # logging's formatting-error report would print it: keep only the
        # scrubbed template.
        record.msg = redact(str(record.msg))
        record.args = None
        return
    scrubbed = redact(rendered)
    if scrubbed != rendered:
        # The credential is in the template, or spans template and an
        # argument: keep only the scrubbed text.
        record.msg = scrubbed
        record.args = None


def _redact_exception(record: logging.LogRecord) -> None:
    if record.exc_info and record.exc_info[0] is not None:
        # Formatters print `exc_text` whenever it is set, so the traceback
        # (and every chained exception's message) is only ever rendered
        # scrubbed. The raw exception objects still hold the unscrubbed
        # messages, so they don't stay on the record.
        record.exc_text = redact(_EXCEPTION_FORMATTER.formatException(record.exc_info))
        record.exc_info = None
    elif isinstance(record.exc_text, str):
        record.exc_text = redact(record.exc_text)
    if record.stack_info:
        record.stack_info = redact(record.stack_info)


def redact_record(record: logging.LogRecord) -> logging.LogRecord:
    _redact_message(record)
    _redact_exception(record)
    return record


def redact_extra(record: logging.LogRecord) -> logging.LogRecord:
    for key in list(record.__dict__):
        if key not in _STANDARD_ATTRIBUTES:
            record.__dict__[key] = _redact_named(key, record.__dict__[key], 0)
    return record


def install_log_redaction() -> None:
    """Idempotent. Call once, as early as possible, in each entrypoint."""
    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, _MARKER, False):

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            return redact_record(current_factory(*args, **kwargs))

        setattr(factory, _MARKER, True)
        logging.setLogRecordFactory(factory)

    current_make_record = logging.Logger.makeRecord
    if not getattr(current_make_record, _MARKER, False):

        def make_record(self: logging.Logger, *args: Any, **kwargs: Any) -> logging.LogRecord:
            return redact_extra(current_make_record(self, *args, **kwargs))

        setattr(make_record, _MARKER, True)
        logging.Logger.makeRecord = make_record  # type: ignore[method-assign]
