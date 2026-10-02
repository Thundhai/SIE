"""Tenant/organization scope types, plus the service-identity envelope
CC-SERVICE-01 (Contract Foundation & Namespace Isolation) introduces.

**This module does not implement authentication or authorization.** It
gives the *already-authorized result* of Public SIE's existing
human/machine auth mechanism (`app.api.deps_context.authorize_context()`
as of Thundhai/SIE main@053bc48) a stable external shape. See
`../../docs/BOUNDARY_DECISIONS.md` Section 7 for the full rationale and
`README.md`'s "Tenant/organization scope rules".

The critical invariant this package assumes, and every consumer must
preserve: `TenantContext.organization_id` is never a value taken
directly from untrusted caller input. For a machine caller it is fixed
once, at credential-issuance time, from `ApiClient.organization_id` --
never overridable by a request field. For a human caller it is resolved
through the authorization service against that user's actual
organization membership/role -- never trusted from a client-supplied
header or body field alone. `TenantContext` is what a caller ends up
with *after* that resolution, not a proposal a callee re-derives trust
from.

**Four distinct layers -- SIE ADR CLOSURE ADDENDUM, ADR-06.** A real
Commercial Core service boundary must keep these separate, never
collapse them into one field:

- SERVICE IDENTITY (`ServiceIdentity`, below): proof that this call
  genuinely originated from a trusted caller (Public SIE's own
  backend) -- not who the call is on behalf of.
- TENANT IDENTITY (`TenantContext.organization_id`): which
  organization's data this call concerns -- only trustworthy because it
  arrives *inside* an authenticated `ServiceIdentity` envelope, never
  because a bare field says so.
- USER IDENTITY (`TenantContext.actor_id`/`actor_type`): who triggered
  the underlying action, for provenance/audit -- an opaque reference,
  never re-usable credential material.
- AUTHORIZATION: not represented by any type in this module at all.
  Whether the operation was *allowed* is decided entirely by Public
  SIE, before the service call is ever made (see
  `KnownErrorCode.AUTHORIZATION_FAILURE` in `errors.py` for how a
  denial is represented if Commercial Core ever needs to reject an
  already-authorized-looking call for some other reason). Commercial
  Core never independently evaluates a permission.

`TenantContext.service_identity` is therefore a *required* field: a
`TenantContext` cannot be constructed without one, which is the
type-level expression of "an arbitrary client-supplied `organization_id`
is never trusted on its own" -- it must arrive wrapped in a
`ServiceIdentity`.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ActorType(str, Enum):
    """Who is acting -- mirrors the two existing, established caller
    kinds (human session, machine API client). Closed set: a genuinely
    new kind of caller is an authentication-architecture change, not a
    contract addition, and is out of scope for this package to predict.
    """

    HUMAN = "human"
    MACHINE = "machine"


class ServiceIdentity(BaseModel):
    """Represents that a call was authenticated as originating from a
    specific, trusted service (e.g. the Public SIE backend) -- distinct
    from *who the call is on behalf of* (see `TenantContext`).

    **ABSTRACT BY DESIGN -- a CC-SERVICE-02 dependency, not decided
    here.** SIE ADR CLOSURE ADDENDUM (ADR-06) decided that Commercial
    Core uses a dedicated service identity rather than forwarding an
    end-user's authentication context, and that the evidence-supported
    mechanism family is an extension of Public SIE's existing
    `ApiClient` machine-credential pattern (`client_id:secret`,
    sha256-verified) -- but the *exact* request-binding mechanics (one
    long-lived service credential vs. per-request context-forwarding)
    were left open, and no specific token/certificate technology is
    chosen by this milestone.

    This type therefore intentionally carries no signature, certificate,
    or token field of any kind -- adding one now would mean choosing
    that mechanism, which is explicitly out of CC-SERVICE-01's scope
    (see its Absolute Non-Goals: "service authentication implementation",
    "mTLS", "service credentials"). `caller` is a plain, non-cryptographic
    label; it proves nothing on its own. The actual verification happens
    at a layer CC-SERVICE-02 will define. Do not treat the presence of
    this type as evidence that authentication is implemented -- it is a
    placeholder for where the verified result of that authentication
    would be represented once CC-SERVICE-02 defines it.
    """

    model_config = ConfigDict(frozen=True)

    caller: str = Field(
        ...,
        description=(
            "An open, non-implementation-specific label identifying which "
            "trusted service made this call, e.g. 'public-sie-backend'. "
            "Not a credential, not a token, not proof of anything on its "
            "own -- see class docstring."
        ),
    )


class TenantContext(BaseModel):
    """An already-authorized organization scope for one request/call,
    delivered inside an authenticated `ServiceIdentity` envelope."""

    model_config = ConfigDict(frozen=True)

    service_identity: ServiceIdentity = Field(
        ...,
        description=(
            "The authenticated caller this tenant context arrived from. "
            "Required -- see module docstring's four-layer explanation. A "
            "TenantContext cannot be constructed without one, which is "
            "the type-level expression of 'an arbitrary organization_id "
            "is never trusted on its own'."
        ),
    )
    organization_id: uuid.UUID | None = Field(
        ...,
        description=(
            "None only for a GLOBAL-scope request (see Thundhai/SIE's "
            "existing GLOBAL-knowledge carve-out) -- never means "
            "'unscoped' or 'trust the caller's own claim'."
        ),
    )
    actor_type: ActorType
    actor_id: uuid.UUID = Field(..., description="The authenticated user_id (human) or api_client_id (machine) -- never a raw credential or secret.")
    request_id: str | None = Field(default=None, description="Correlation id for this call, if the caller supplied or was assigned one.")
