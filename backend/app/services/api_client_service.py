"""ApiClientService — machine-client credential lifecycle (milestone item
10). See `app/models/api_client.py`'s own docstring for the full design
rationale (why sha256 without a slow KDF is the appropriate secret hash
here, why scopes are explicit rather than inherited from a role).

**The raw secret exists in memory only during `create()`/`rotate_secret()`
and is returned to the caller exactly once**, inside
`NewApiClientCredential` — never stored, never logged, never
retrievable again afterward. `authenticate()` uses
`secrets.compare_digest()` (constant-time comparison) specifically so
verifying a wrong secret takes the same time as verifying a correct one,
closing the most basic timing side-channel.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_client import ApiClient
from app.services.audit_service import AuditAction, audit_service
from app.services.permissions import Permission

_SECRET_BYTES = 32
_SECRET_PREFIX_LENGTH = 8


def _as_utc(value: datetime) -> datetime:
    """SQLite (the test suite's engine) round-trips a `DateTime(timezone=True)`
    value as naive; PostgreSQL (production) keeps it aware. The same
    normalization every other `_as_utc()` in this codebase applies before
    comparing two datetimes it can't otherwise guarantee are both aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


_VALID_SCOPE_VALUES = frozenset(p.value for p in Permission)


def _validate_scopes(scopes: list[Permission | str]) -> list[str]:
    """Least privilege by default (Intelligence Platform Integration
    v0.1, item 6) starts with an explicit, *valid* scope list — a typo'd
    or made-up scope string (e.g. `"intelligence:predictt"`) would
    otherwise silently grant nothing while looking like it grants
    something, or worse, be added later as a real permission that this
    client was never actually reviewed for. `app.services.permissions.Permission`
    is the one scope vocabulary machine clients and human roles both draw
    from — see `app/models/api_client.py`'s own docstring for why this
    codebase deliberately doesn't maintain a second, parallel scope
    vocabulary for machine clients."""
    scope_values = [s.value if isinstance(s, Permission) else str(s) for s in scopes]
    unknown = [s for s in scope_values if s not in _VALID_SCOPE_VALUES]
    if unknown:
        raise ValueError(
            f"Unknown scope(s) {unknown!r} -- must be one of {sorted(_VALID_SCOPE_VALUES)}."
        )
    return scope_values


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _generate_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def _generate_client_id() -> str:
    return f"sie_{secrets.token_hex(12)}"


@dataclass
class NewApiClientCredential:
    """Returned exactly once, at creation/rotation time — see module
    docstring. `secret` must be shown to the caller and then discarded;
    SIE itself never stores or displays it again (only `api_client.secret_prefix`
    remains visible afterward)."""

    client_id: str
    secret: str
    api_client: ApiClient


class ApiClientService:
    def create(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        name: str,
        scopes: list[Permission | str],
        expires_at: datetime | None = None,
    ) -> NewApiClientCredential:
        client_id = _generate_client_id()
        secret = _generate_secret()
        scope_values = _validate_scopes(scopes)

        api_client = ApiClient(
            organization_id=organization_id,
            name=name,
            client_id=client_id,
            hashed_secret=_hash_secret(secret),
            secret_prefix=secret[:_SECRET_PREFIX_LENGTH],
            scopes=scope_values,
            status="ACTIVE",
            expires_at=expires_at,
        )
        db.add(api_client)
        db.commit()
        db.refresh(api_client)

        audit_service.log(
            db,
            action=AuditAction.API_CLIENT_CREATED,
            resource_type="ApiClient",
            resource_id=api_client.id,
            organization_id=organization_id,
            metadata={"name": name, "client_id": client_id, "scopes": scope_values},
        )
        return NewApiClientCredential(client_id=client_id, secret=secret, api_client=api_client)

    def authenticate(self, db: Session, *, client_id: str, secret: str) -> ApiClient | None:
        api_client = db.execute(select(ApiClient).where(ApiClient.client_id == client_id)).scalar_one_or_none()
        if api_client is None or api_client.status != "ACTIVE":
            return None
        if api_client.expires_at is not None and _as_utc(api_client.expires_at) <= datetime.now(timezone.utc):
            # Expired is rejected exactly like revoked (item 39's "expired
            # credential" case) -- `status` and `revoked_at` are left
            # alone, so this stays distinguishable from an explicit
            # revoke() in an audit trail, even though authentication
            # itself treats the two identically.
            return None
        if not secrets.compare_digest(api_client.hashed_secret, _hash_secret(secret)):
            return None
        api_client.last_used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(api_client)
        return api_client

    def rotate_secret(self, db: Session, *, api_client: ApiClient) -> NewApiClientCredential:
        secret = _generate_secret()
        api_client.hashed_secret = _hash_secret(secret)
        api_client.secret_prefix = secret[:_SECRET_PREFIX_LENGTH]
        api_client.rotated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(api_client)

        audit_service.log(
            db,
            action=AuditAction.API_CLIENT_SECRET_ROTATED,
            resource_type="ApiClient",
            resource_id=api_client.id,
            organization_id=api_client.organization_id,
            metadata={"client_id": api_client.client_id},
        )
        return NewApiClientCredential(client_id=api_client.client_id, secret=secret, api_client=api_client)

    def revoke(self, db: Session, *, api_client: ApiClient) -> ApiClient:
        api_client.status = "REVOKED"
        api_client.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(api_client)

        audit_service.log(
            db,
            action=AuditAction.API_CLIENT_REVOKED,
            resource_type="ApiClient",
            resource_id=api_client.id,
            organization_id=api_client.organization_id,
            metadata={"client_id": api_client.client_id},
        )
        return api_client

    def get(self, db: Session, *, id: uuid.UUID) -> ApiClient | None:
        return db.get(ApiClient, id)


api_client_service = ApiClientService()
