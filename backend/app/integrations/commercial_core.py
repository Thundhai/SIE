"""The one seam Public SIE's API routers call through to reach the
proprietary Commercial Core intelligence engine -- established by
M43-IP-03 (Public SIE Extraction / Cleanup) as the concrete answer to
that milestone's own required shape:

    PUBLIC API  ->  PUBLIC CONTRACT / CLIENT INTERFACE  ->  PRIVATE COMMERCIAL CORE

**What this module deliberately is not.** It is not a live network
client, an RPC stub, or a copy of any private algorithm. Commercial Core
(`Thundhai/SIE-Commercial-Core`) has no HTTP route layer of its own yet
(see that repository's `PRIVATE_CORE_BOOTSTRAP.md` -- it is invoked as a
library against a shared database today, not a deployable service) --
building a real network client here now, with nothing on the other end
to call, would be exactly the "expose private implementation through a
contract merely to look integrated" this milestone's governance
forbids, and would edge into M43B's own scope (evidence/recommendation
integration), which this milestone must not implement.

**What it is.** A single, explicit interface (`CommercialCoreClient`)
every extracted-endpoint router depends on, plus the one implementation
this deployment actually has (`NotConfiguredCommercialCoreClient`) --
which raises a clear, typed, honest error rather than silently
returning empty/fake data or reimplementing the private computation
locally. When Commercial Core eventually exposes a real service boundary
(its own HTTP API, or a message queue, or a published `sie-contract`
distribution Public SIE can depend on as a real package), a real
`CommercialCoreClient` implementation is swapped in *here* --the router
code that depends on this interface does not change.
"""

from __future__ import annotations

from fastapi import HTTPException, status


class CommercialCoreUnavailable(HTTPException):
    """Raised by every extracted intelligence/prediction/RAG/organizational-
    memory/learning-candidate endpoint. Distinguished from a generic 501 by
    its own type so tests and callers can assert on "this specific,
    documented boundary condition" rather than "some 501 or other"."""

    def __init__(self, capability: str) -> None:
        super().__init__(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"{capability} is not available in Public SIE: this capability's "
                "implementation was extracted to the private Commercial Core repository "
                "by M43-IP-03 (Public SIE Extraction / Cleanup), and no Commercial Core "
                "client integration is wired into this deployment yet. See "
                "docs/M43_IP_03_PUBLIC_EXTRACTION.md for what moved and why, and "
                "sie-contract (in the Commercial Core repository) for the DTOs a future "
                "integration would exchange."
            ),
        )


class CommercialCoreClient:
    """The interface every extracted-endpoint router is written against.
    Never imported alongside a private module in the same file -- that
    would defeat the point of having an interface at all."""

    def unavailable(self, capability: str) -> CommercialCoreUnavailable:
        raise NotImplementedError


class NotConfiguredCommercialCoreClient(CommercialCoreClient):
    """The only implementation this repository ships. Every capability is
    unavailable, honestly, by construction -- not because a real client
    call happened to fail."""

    def unavailable(self, capability: str) -> CommercialCoreUnavailable:
        return CommercialCoreUnavailable(capability)


commercial_core_client: CommercialCoreClient = NotConfiguredCommercialCoreClient()
