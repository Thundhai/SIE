"""Idempotency-Key support — Intelligence Platform Integration &
Enterprise API v0.1, item 12. See `app/models/idempotency_key.py`'s own
docstring for the full design (why this is distinct from the ingestion
pipeline's own domain-level idempotency, and the exact replay/conflict
rules this module implements).

**Deliberately explicit at each call site, not a generic response-
capturing middleware.** Storing "the response" for later replay needs
the actual, already-serialized response body — which only exists after
a route's own logic runs and FastAPI serializes it against its
`response_model`. A middleware sitting outside FastAPI's dependency
injection would either need its own, second database session (bypassing
`app.core.database.get_db`'s test-time override entirely — a real
correctness risk, not just a style preference) or would have to
re-implement response buffering/decoding generically. Instead, the
three routes that opt into idempotency
(`POST /intelligence/events`, `POST /intelligence/events/batch`,
`POST /intelligence/predictions`) each call `check_and_replay()` before
doing their real work and `store_response()` right before returning —
a few explicit lines per route, using the same `Depends(get_db)` session
everything else on that route already uses.

    Idempotency-Key header present?
        no  -> idempotency is opt-in; the route runs exactly as before
        yes -> check_and_replay()
               no existing row              -> route runs; store_response() saves it
               existing row, same hash       -> replay the stored response, route never runs again
               existing row, different hash  -> 409 IDEMPOTENCY_CONFLICT (app/core/errors.py)

No scheduled cleanup job exists in this milestone (consistent with item
49's "no workflow automation" boundary) — `expires_at` records each
row's intended lifetime for a future cleanup pass to key off; nothing
prunes automatically today, so a long-running deployment should add one
before relying on this table staying small indefinitely.

**`store_response(..., commit=False)`** (SIE Milestone 17 corrective
patch). Every existing caller keeps calling `store_response()` exactly
as before — `commit` defaults to `True`, so this is purely additive.
It exists for a route whose own mutation must commit as a single
all-or-nothing unit together with the `IdempotencyKey` row (e.g.
`POST /actions` — `app/services/safety_action_service.py`'s own
`action_mutation_transaction()`): pass `commit=False` and the row is
`db.add()`ed and `db.flush()`ed (so it participates in the caller's own
open transaction and is visible to later statements in it) but not
committed — the caller commits once, itself, after every other write
that mutation needs has also been added. This is the smallest change
that lets `store_response()` participate in an outer transaction
without touching its behavior for any of its other, non-transactional
callers.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.models.idempotency_key import IdempotencyKey


def compute_request_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


@dataclass(frozen=True)
class IdempotencyLookup:
    is_replay: bool
    response_status_code: int | None = None
    response_body: Any | None = None


def _scope_filter(
    *, endpoint: str, idempotency_key: str, organization_id: uuid.UUID | None, api_client_id: uuid.UUID | None, user_id: uuid.UUID | None
):
    return (
        IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.idempotency_key == idempotency_key,
        IdempotencyKey.organization_id == organization_id,
        IdempotencyKey.api_client_id == api_client_id,
        IdempotencyKey.user_id == user_id,
    )


def check_and_replay(
    db: Session,
    *,
    endpoint: str,
    idempotency_key: str | None,
    request_hash: str,
    organization_id: uuid.UUID | None,
    api_client_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> IdempotencyLookup:
    """Call before doing the route's real work. Returns
    `IdempotencyLookup(is_replay=True, ...)` when this exact request
    (same caller, endpoint, key, AND body hash) was already handled --
    the caller should return `response_body` immediately, unchanged, and
    never repeat the underlying operation. Raises `ApiError` (409
    `IDEMPOTENCY_CONFLICT`) when the same key was reused for a
    materially different request."""
    if not idempotency_key:
        return IdempotencyLookup(is_replay=False)

    existing = db.execute(
        select(IdempotencyKey).where(
            *_scope_filter(
                endpoint=endpoint, idempotency_key=idempotency_key,
                organization_id=organization_id, api_client_id=api_client_id, user_id=user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return IdempotencyLookup(is_replay=False)

    if existing.request_hash != request_hash:
        raise ApiError(
            status_code=409,
            code=ErrorCode.IDEMPOTENCY_CONFLICT,
            message=(
                f"Idempotency-Key {idempotency_key!r} was already used for a different request body "
                f"on this endpoint. Use a new key for a genuinely new request."
            ),
        )

    return IdempotencyLookup(
        is_replay=True, response_status_code=existing.response_status_code, response_body=existing.response_body
    )


def store_response(
    db: Session,
    *,
    endpoint: str,
    idempotency_key: str | None,
    request_hash: str,
    response_status_code: int,
    response_body: Any,
    organization_id: uuid.UUID | None,
    api_client_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    commit: bool = True,
) -> None:
    """Call once, right before returning, after the route's real work
    succeeded. A no-op when no `Idempotency-Key` was supplied — see
    module docstring: idempotency is opt-in, never forced onto a caller
    that didn't ask for it.

    `commit=True` (default, unchanged) commits immediately, exactly as
    before every existing caller of this function. `commit=False` only
    `db.add()`s and `db.flush()`s the row — see this module's own
    docstring's "store_response(..., commit=False)" note, and
    `app/services/safety_action_service.py::action_mutation_transaction()`
    for the caller that uses it."""
    if not idempotency_key:
        return

    row = IdempotencyKey(
        organization_id=organization_id,
        api_client_id=api_client_id,
        user_id=user_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status_code=response_status_code,
        response_body=response_body,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.IDEMPOTENCY_KEY_TTL_HOURS),
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
