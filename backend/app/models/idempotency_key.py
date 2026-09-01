"""IdempotencyKey — HTTP-transport-level idempotency for a caller-supplied
`Idempotency-Key` header (Intelligence Platform Integration v0.1, item
12).

**Distinct from, and complementary to, the domain-level idempotency the
ingestion pipeline already has.** `SafetyEventIngestionService` already
dedupes by `(organization_id, source_system, source_record_id)` — that
protects against the *same event* being submitted twice under two
different request attempts. This table protects a different case: the
*same HTTP request* (e.g. a client's retry after a timeout, before it
ever learns whether the first attempt succeeded) safely replays the
first attempt's actual response instead of re-executing the operation —
useful even for an endpoint whose own domain logic isn't naturally
idempotent (a fresh `POST /predictions` call, for instance, could
otherwise generate two prediction rows for one logical request).

    caller -> Idempotency-Key: <opaque client-chosen string>
        -> IdempotencyKey lookup, scoped to (identity, endpoint, key)
           -> not found -> execute the request -> store the response
           -> found, same request body hash -> replay the stored response
           -> found, DIFFERENT request body hash -> 409 IDEMPOTENCY_CONFLICT

Scoped to the calling identity (`organization_id` + `api_client_id` for a
machine client, `organization_id` + `user_id` for a human) so one
client's idempotency key can never collide with, or replay, another
client's stored response — this is a tenant-isolation property, not just
a request-deduplication one. `response_body` stores only what this
endpoint's own response already returns to this same caller; nothing
here is a new information-disclosure surface.

Rows are not automatically pruned in this milestone (see
`app/core/idempotency.py`'s own docstring for why a scheduled cleanup job
is explicitly out of scope here) — `expires_at` records the intended
lifetime for a future cleanup pass to key off, but nothing here purges
today.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON as GenericJSON
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow

_JSONType = GenericJSON().with_variant(JSONB(), "postgresql")


class IdempotencyKey(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # The same scope tuple this class's own docstring describes --
        # this is what actually makes a lookup "find the one row for this
        # caller's key on this endpoint", not just a convention.
        UniqueConstraint(
            "endpoint", "idempotency_key", "organization_id", "api_client_id", "user_id",
            name="uq_idempotency_keys_scope",
        ),
    )

    # Nullable + SET NULL for the same reason AuditLog's are: this is a
    # short-lived operational record, not something that should block or
    # cascade-disappear with an organization/client, though in practice a
    # row's own expires_at will make it irrelevant long before that matters.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # sha256 of the normalized request body -- detects a caller reusing the
    # same Idempotency-Key for a materially different request (item 15's
    # IDEMPOTENCY_CONFLICT), without storing the request body itself twice.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(_JSONType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IdempotencyKey endpoint={self.endpoint!r} key={self.idempotency_key!r}>"
