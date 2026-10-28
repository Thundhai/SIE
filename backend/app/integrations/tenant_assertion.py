"""SIE-2: signs the tenant assertion Public SIE attaches to every Commercial
Core call (`sie_contract.tenant_assertion`, contract 0.9.0).

The assertion is a compact JWS (`EdDSA`, Ed25519) stating which
organization, actor and capability Public SIE has already authorized for
this one call. Commercial Core's gateway and domain service each verify
it, so a compromised gateway alone cannot act for an organization Public
SIE never authorized.

**Inert until configured.** With none of the three
`COMMERCIAL_CORE_TENANT_ASSERTION_*` key settings set,
`build_tenant_assertion_signer()` returns `None` and no header is sent:
Commercial Core in `legacy` or `dual` mode serves the request exactly as
before. Setting some but not all of them is a configuration error at
first use, never a silent half-configuration.

The signing key is an Ed25519 private JWK (`{"kty": "OKP", "crv":
"Ed25519", "x": ..., "d": ...}`), the private half of the public JWK
Commercial Core's verifiers list under the same `kid`. It lives only in
this deployment's secret environment and is never logged or re-exposed.

Claims carry identifiers only, never names, emails or secrets: the
organization, the actor's id (the user id, or the API client's UUID for a
machine caller), the permission Public SIE checked and exactly one
capability, the one for the route being called.
"""

from __future__ import annotations

import base64
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sie_contract import (
    MAX_HEADER_BYTES,
    MAX_LIFETIME_SECONDS,
    TENANT_ASSERTION_ALG,
    TENANT_ASSERTION_AUDIENCE,
    TENANT_ASSERTION_SCHEMA_VERSION,
    TENANT_ASSERTION_TYP,
    ActorType,
    TenantAssertionClaims,
    TenantAssertionHeader,
    TenantCapability,
)

from app.core.config import settings
from app.services.permissions import Permission

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.api.deps_context import RequestContext

# Commercial Core keeps an `X-Request-Id` unchanged only when it has this
# shape (cc_service/transport/headers.py), and a signed `rid` must equal
# the id it keeps. Any other request id is left out of the claims.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class TenantAssertionConfigurationError(RuntimeError):
    """The signing settings are partial or invalid. The message names the
    setting, never its value."""


@dataclass(frozen=True)
class TenantActor:
    """Who Public SIE authorized for this call, and under which permission."""

    actor_id: uuid.UUID
    actor_type: ActorType
    permission: Permission


def tenant_actor_from_context(context: RequestContext, permission: Permission) -> TenantActor:
    """The actor for an already-authorized request: the user for a human
    caller, the API client's UUID for a machine caller."""
    if context.is_machine:
        actor_id, actor_type = context.api_client_id, ActorType.MACHINE
    else:
        actor_id, actor_type = context.user_id, ActorType.HUMAN
    if actor_id is None:
        raise ValueError(f"A {context.kind} RequestContext carries no actor id.")
    return TenantActor(actor_id=actor_id, actor_type=actor_type, permission=permission)


class TenantAssertionSigner:
    def __init__(
        self,
        *,
        issuer: str,
        key_id: str,
        private_key: Ed25519PrivateKey,
        lifetime_seconds: int = MAX_LIFETIME_SECONDS,
    ) -> None:
        if not 1 <= lifetime_seconds <= MAX_LIFETIME_SECONDS:
            raise TenantAssertionConfigurationError(
                f"COMMERCIAL_CORE_TENANT_ASSERTION_LIFETIME_SECONDS must be 1-{MAX_LIFETIME_SECONDS}."
            )
        try:
            TenantAssertionHeader(alg=TENANT_ASSERTION_ALG, typ=TENANT_ASSERTION_TYP, kid=key_id)
        except ValueError:
            raise TenantAssertionConfigurationError(
                "COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID must be 1-64 characters."
            ) from None
        self.issuer = issuer
        self.key_id = key_id
        self._private_key = private_key  # never logged, never re-exposed
        self._lifetime_seconds = lifetime_seconds

    def sign(
        self,
        *,
        organization_id: uuid.UUID,
        actor: TenantActor,
        capability: TenantCapability,
        request_id: str | None = None,
        now: float | None = None,
    ) -> str:
        """One assertion for one call. Raises `ValueError` if `capability`
        is not one `actor.permission` grants: the route checked the wrong
        permission, which is a bug, so nothing is sent."""
        import jwt

        iat = int(now if now is not None else time.time())
        claims = TenantAssertionClaims(
            iss=self.issuer,
            aud=TENANT_ASSERTION_AUDIENCE,
            org=organization_id,
            sub=actor.actor_id,
            act=actor.actor_type,
            perm=actor.permission.value,
            cap=capability,
            iat=iat,
            exp=iat + self._lifetime_seconds,
            jti=uuid.uuid4(),
            rid=request_id if request_id and _SAFE_REQUEST_ID.match(request_id) else None,
            ver=TENANT_ASSERTION_SCHEMA_VERSION,
        )
        token = jwt.encode(
            claims.model_dump(mode="json", exclude_none=True),
            self._private_key,
            algorithm=TENANT_ASSERTION_ALG,
            headers={"typ": TENANT_ASSERTION_TYP, "kid": self.key_id},
        )
        if len(token.encode("ascii")) > MAX_HEADER_BYTES:
            # Cannot happen with identifier-only claims and a 64-character
            # kid, but a verifier rejects anything longer unparsed.
            raise ValueError("Tenant assertion exceeds the contract's header size limit.")
        return token


def _load_private_jwk(value: str) -> Ed25519PrivateKey:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    error = TenantAssertionConfigurationError(
        'COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY must be an Ed25519 private JWK: '
        '{"kty": "OKP", "crv": "Ed25519", "x": ..., "d": ...}.'
    )
    # Each error is raised after its `try`, never inside the handler: a
    # JSONDecodeError keeps the whole input (the private `d` included) in
    # `.doc`, and raising inside the handler would leave it reachable as
    # `__context__` even with `from None`.
    try:
        jwk = json.loads(value)
    except ValueError:
        jwk = None
    if not isinstance(jwk, dict) or jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise error
    raw = {}
    for name in ("d", "x"):
        part = jwk.get(name)
        if not isinstance(part, str) or not _B64URL.match(part):
            raise error
        try:
            raw[name] = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        except ValueError:  # binascii.Error: an impossible base64 length
            raw[name] = b""
        if len(raw[name]) != 32:
            raise error
    private_key = Ed25519PrivateKey.from_private_bytes(raw["d"])
    if private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw) != raw["x"]:
        # A mismatched pair would sign tokens no verifier listing `x` accepts.
        raise TenantAssertionConfigurationError(
            "COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY's x does not match its d."
        )
    return private_key


def build_tenant_assertion_signer(
    *,
    signing_key: str | None = None,
    key_id: str | None = None,
    issuer: str | None = None,
    lifetime_seconds: int | None = None,
) -> TenantAssertionSigner | None:
    """A signer from explicit arguments, falling back to settings. `None`
    when none of key, key id and issuer is set (assertions off)."""
    signing_key = signing_key if signing_key is not None else settings.COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY
    key_id = key_id if key_id is not None else settings.COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID
    issuer = issuer if issuer is not None else settings.COMMERCIAL_CORE_TENANT_ASSERTION_ISSUER
    lifetime_seconds = (
        lifetime_seconds if lifetime_seconds is not None else settings.COMMERCIAL_CORE_TENANT_ASSERTION_LIFETIME_SECONDS
    )

    fields = (
        ("COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY", signing_key),
        ("COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID", key_id),
        ("COMMERCIAL_CORE_TENANT_ASSERTION_ISSUER", issuer),
    )
    if not any(value for _, value in fields):
        return None
    missing = [name for name, value in fields if not value]
    if missing:
        raise TenantAssertionConfigurationError(
            "Tenant assertion signing is partially configured; missing: " + ", ".join(missing)
        )
    return TenantAssertionSigner(
        issuer=issuer,
        key_id=key_id,
        private_key=_load_private_jwk(signing_key),
        lifetime_seconds=lifetime_seconds,
    )


__all__ = [
    "TenantActor",
    "TenantAssertionConfigurationError",
    "TenantAssertionSigner",
    "build_tenant_assertion_signer",
    "tenant_actor_from_context",
]
