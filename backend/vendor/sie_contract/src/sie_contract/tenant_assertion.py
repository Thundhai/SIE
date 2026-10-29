"""Tenant assertion -- the signed statement Public SIE attaches to every
Commercial Core call naming the organization, actor and capability it
already authorized (since 0.9.0).

Public SIE signs a compact JWS (`EdDSA`, Ed25519) carrying
`TenantAssertionClaims` and sends it in the `X-SIE-Tenant-Assertion`
header. Commercial Core's gateway (`cc_service`) and domain service each
verify it independently, so a compromised gateway alone cannot act for
an organization Public SIE never authorized.

**This module is data, not a verifier.** It defines the wire shape
(header fields, claims), the fixed constants both sides must agree on,
and the permission-to-capability mapping. It never checks a signature,
compares a timestamp with the current time, or looks anything up: each
service keeps its own verifier (so the gateway and the domain never
import each other), and both must agree with the shared golden vectors
in `test_vectors/tenant_assertion_v1.json`.

The model validators here enforce only what is true of a well-formed
assertion regardless of when or where it is checked: exact audience and
version, a lifetime of at most `MAX_LIFETIME_SECONDS`, a version-4
`jti`, and a capability the stated permission actually grants. Whether
it is fresh (`iat`/`exp` against the verifier's clock, with
`CLOCK_SKEW_SECONDS`), from a known key, from the configured issuer, for
this route, for this request's organization, or already used, is the
verifier's job.

Claims never carry secrets, names or email addresses: only identifiers.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from sie_contract.tenancy import ActorType

TENANT_ASSERTION_HEADER = "X-SIE-Tenant-Assertion"
"""HTTP header carrying the compact JWS."""

TENANT_ASSERTION_TYP = "sie-tenant+jwt"
"""Required JWS `typ`: keeps this token from being confused with any other JWT."""

TENANT_ASSERTION_ALG = "EdDSA"
"""The only accepted JWS `alg` (Ed25519). Anything else, `none` and HMAC included, is rejected."""

TENANT_ASSERTION_AUDIENCE = "sie-commercial-core"
"""Required `aud`."""

TENANT_ASSERTION_SCHEMA_VERSION = 1
"""Required `ver` for the claims defined here."""

MAX_LIFETIME_SECONDS = 60
"""`exp - iat` may not exceed this (owner decision D2)."""

CLOCK_SKEW_SECONDS = 15
"""Allowed clock difference between signer and verifier (owner decision D2):
`iat <= now + CLOCK_SKEW_SECONDS` and `exp > now - CLOCK_SKEW_SECONDS`."""

MAX_HEADER_BYTES = 2048
"""Maximum size of the serialized header value. Longer values are rejected unparsed."""


class TenantCapability(str, Enum):
    """The one Commercial Core route class an assertion is good for.
    Values equal the gateway's own service scopes
    (`cc_service/service_scopes.py`), so a verifier compares `cap` with
    the route's required scope directly. Closed set: a verifier must
    reject a capability it does not know, so adding one is a breaking
    change (README "Versioning strategy")."""

    ATTENTION_READ = "commercial_core:attention_read"
    ANALYTICS_READ = "commercial_core:analytics_read"
    ENTERPRISE_INTELLIGENCE_READ = "commercial_core:enterprise_intelligence_read"
    DECISIONS_READ = "commercial_core:decisions_read"
    DECISIONS_WRITE = "commercial_core:decisions_write"
    RAG_QUERY = "commercial_core:rag_query"


PERMISSION_CAPABILITIES: dict[str, frozenset[TenantCapability]] = {
    "intelligence:read": frozenset(
        {
            TenantCapability.ATTENTION_READ,
            TenantCapability.ANALYTICS_READ,
            TenantCapability.ENTERPRISE_INTELLIGENCE_READ,
            TenantCapability.DECISIONS_READ,
        }
    ),
    "intelligence:decision_write": frozenset({TenantCapability.DECISIONS_WRITE}),
    "knowledge:read": frozenset({TenantCapability.RAG_QUERY}),
}
"""Public SIE permission (its `Permission` enum value) -> the capabilities
it lets Public SIE assert. The signer mints exactly one capability per
call: the one for the route being called."""

WRITE_CAPABILITIES: frozenset[TenantCapability] = frozenset({TenantCapability.DECISIONS_WRITE})
"""Capabilities whose `jti` the domain service accepts only once (owner
decision D3). Reads are not replay-tracked."""


class TenantAssertionHeader(BaseModel):
    """The JWS protected header. No other fields are allowed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alg: Literal["EdDSA"]
    typ: Literal["sie-tenant+jwt"]
    kid: str = Field(..., min_length=1, max_length=64, description="Identifies the signing key in the verifier's key map.")


class TenantAssertionClaims(BaseModel):
    """Claims, schema version 1. No other claims are allowed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    iss: str = Field(..., min_length=1, max_length=256, description="The signing Public SIE deployment; must equal the verifier's configured issuer.")
    aud: Literal["sie-commercial-core"]
    org: uuid.UUID = Field(..., description="The organization Public SIE authorized. Must match the request's organization header and, at the domain, its body.")
    sub: uuid.UUID = Field(..., description="The acting user's id, or the API client's id for a machine caller. Must equal a decision's `actor_id`.")
    act: ActorType
    perm: str = Field(..., description="The Public SIE permission that was checked (a key of `PERMISSION_CAPABILITIES`).")
    cap: TenantCapability = Field(..., description="The one route class this assertion is good for; must equal the route's required scope.")
    iat: StrictInt = Field(..., description="Issued at, seconds since the Unix epoch.")
    exp: StrictInt = Field(..., description="Expires at, seconds since the Unix epoch.")
    jti: uuid.UUID = Field(..., description="Unique id, version 4. Accepted only once for a write capability.")
    rid: str | None = Field(
        default=None,
        max_length=128,
        description="The request id, when one was sent; must equal `X-Request-Id`. Log correlation only, not a security control.",
    )
    # StrictInt plus the check below rather than `Literal[1]`, which would
    # also accept JSON `true` and `1.0`.
    ver: StrictInt = Field(..., description="Claims schema version; must be 1.")

    @model_validator(mode="after")
    def _well_formed(self) -> TenantAssertionClaims:
        if self.ver != TENANT_ASSERTION_SCHEMA_VERSION:
            raise ValueError(f"ver must be {TENANT_ASSERTION_SCHEMA_VERSION}")
        if self.exp <= self.iat:
            raise ValueError("exp must be after iat")
        if self.exp - self.iat > MAX_LIFETIME_SECONDS:
            raise ValueError(f"lifetime may not exceed {MAX_LIFETIME_SECONDS} seconds")
        if self.jti.version != 4:
            raise ValueError("jti must be a version-4 UUID")
        if self.perm not in PERMISSION_CAPABILITIES:
            raise ValueError("perm is not a known permission")
        if self.cap not in PERMISSION_CAPABILITIES[self.perm]:
            raise ValueError("cap is not granted by perm")
        return self


__all__ = [
    "CLOCK_SKEW_SECONDS",
    "MAX_HEADER_BYTES",
    "MAX_LIFETIME_SECONDS",
    "PERMISSION_CAPABILITIES",
    "TENANT_ASSERTION_ALG",
    "TENANT_ASSERTION_AUDIENCE",
    "TENANT_ASSERTION_HEADER",
    "TENANT_ASSERTION_SCHEMA_VERSION",
    "TENANT_ASSERTION_TYP",
    "WRITE_CAPABILITIES",
    "TenantAssertionClaims",
    "TenantAssertionHeader",
    "TenantCapability",
]
