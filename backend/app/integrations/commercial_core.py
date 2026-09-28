"""The one seam Public SIE's API routers call through to reach the
proprietary Commercial Core intelligence engine -- established by
M43-IP-03 (Public SIE Extraction / Cleanup) as the concrete answer to
that milestone's own required shape:

    PUBLIC API  ->  PUBLIC CONTRACT / CLIENT INTERFACE  ->  PRIVATE COMMERCIAL CORE

**What changed in Task 01D-B.** Commercial Core now has a real HTTP
service boundary (`cc_service`, Thundhai/SIE-Commercial-Core, built by
Task 01C) and Public SIE has a vendored copy of its contract package
(`vendor/sie_contract`, Task 01D-A). `HttpCommercialCoreClient` below is
the first real `CommercialCoreClient` implementation: an authenticated
HTTP call to `cc_service`'s `POST /internal/v1/attention`, never a
direct database or `domain_service` connection, never a duplicate of any
private computation. `NotConfiguredCommercialCoreClient` remains the
default for every capability this client does not (yet) implement, and
for Attention itself whenever Commercial Core is not configured for this
deployment.

**What it is.** A single, explicit interface (`CommercialCoreClient`)
every extracted-endpoint router depends on. When Commercial Core
eventually exposes the rest of its capabilities over this same boundary,
a real implementation is added to *this* class -- the router code that
depends on this interface does not change.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from functools import lru_cache

import sie_contract
from fastapi import HTTPException, status
from sie_contract import AttentionResultDTO, ErrorResponse, KnownErrorCode

from app.core.config import settings

logger = logging.getLogger("sie.integrations.commercial_core")

_ATTENTION_PATH = "/internal/v1/attention"


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


class CommercialCoreConfigurationError(RuntimeError):
    """Raised by `build_commercial_core_client()` when
    `COMMERCIAL_CORE_BASE_URL` / `COMMERCIAL_CORE_CLIENT_ID` /
    `COMMERCIAL_CORE_CLIENT_SECRET` are only partially set -- a genuine
    deployment misconfiguration, deliberately never treated the same as
    "none set" (which resolves to `NotConfiguredCommercialCoreClient`
    instead). Raised at first real use (inside
    `get_commercial_core_client()`/`build_commercial_core_client()`),
    never merely by importing this module or constructing `Settings` --
    the same "fail closed at first use" shape
    `app.services.oidc_verifier.get_oidc_verifier()` already established."""


class CommercialCoreIntegrationError(RuntimeError):
    """Base class for every failure `HttpCommercialCoreClient` raises once
    Commercial Core is configured. Every subclass's message is a fixed,
    safe, human-authored string -- never `str(exc)` for the underlying
    httpx exception, never a Commercial Core stack trace, never a
    credential or URL. Callers (see `app/api/v1/intelligence.py`) map
    these onto Public SIE's own `app.core.errors` vocabulary."""


class CommercialCoreAuthenticationError(CommercialCoreIntegrationError):
    """cc_service rejected this deployment's own Credential A (401) --
    never the calling Public SIE user's/machine client's fault: the
    caller was already authenticated and authorized by Public SIE itself
    before this client was ever invoked."""


class CommercialCoreAuthorizationError(CommercialCoreIntegrationError):
    """cc_service returned 403 -- either insufficient scope on this
    deployment's own Credential A, or (should never happen, since the
    organization sent is always `resolve_authorized_organization_id()`'s
    result) a tenant-mismatch rejection."""


class CommercialCoreValidationError(CommercialCoreIntegrationError):
    """cc_service rejected the request body itself (422)."""


class CommercialCoreDependencyUnavailableError(CommercialCoreIntegrationError):
    """cc_service reported its own downstream (the Domain Service)
    unavailable (503)."""


class CommercialCoreTimeoutError(CommercialCoreIntegrationError):
    """The HTTP call to cc_service timed out."""


class CommercialCoreConnectionError(CommercialCoreIntegrationError):
    """The HTTP call to cc_service could not be established at all."""


class CommercialCoreMalformedResponseError(CommercialCoreIntegrationError):
    """cc_service returned a 2xx response that is not valid JSON, or that
    fails `sie_contract.AttentionResultDTO` validation. Never treated as
    an empty successful result -- a malformed successful response is a
    protocol failure, not "no attention items"."""


class CommercialCoreUnexpectedStatusError(CommercialCoreIntegrationError):
    """cc_service returned an HTTP status this client has no specific
    handling for."""


class CommercialCoreClient:
    """The interface every extracted-endpoint router is written against.
    Never imported alongside a private module in the same file -- that
    would defeat the point of having an interface at all."""

    def unavailable(self, capability: str) -> CommercialCoreUnavailable:
        raise NotImplementedError

    def get_attention(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
    ) -> AttentionResultDTO:
        raise NotImplementedError


class NotConfiguredCommercialCoreClient(CommercialCoreClient):
    """The fallback implementation this repository ships when Commercial
    Core is not configured for this deployment. Every capability is
    unavailable, honestly, by construction -- not because a real client
    call happened to fail."""

    def unavailable(self, capability: str) -> CommercialCoreUnavailable:
        return CommercialCoreUnavailable(capability)

    def get_attention(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
    ) -> AttentionResultDTO:
        raise self.unavailable("Attention")


class HttpCommercialCoreClient(CommercialCoreClient):
    """The real `CommercialCoreClient` implementation: an authenticated
    HTTP call to `cc_service`'s `POST /internal/v1/attention` (Task 01C,
    Thundhai/SIE-Commercial-Core). Never imports or calls `domain_service`
    directly, never duplicates Commercial Core's Attention business logic.

    Authentication is Commercial Core Credential A -- `Authorization:
    Bearer <client_id>:<secret>` (see `cc_service/auth/credentials.py`'s
    `parse_credential()`). `client_id`/`client_secret` are read once, at
    construction, and never re-exposed: not logged, not placed in any
    exception message, not returned from any method.

    The organization sent to cc_service is always the caller's own
    `organization_id` argument -- callers of this class (see
    `app/api/v1/intelligence.py`) must pass
    `app.api.deps_context.resolve_authorized_organization_id()`'s result,
    never a raw, unchecked request value. This class has no tenant
    resolution logic of its own; it sends `organization_id` as the
    `X-Organization-Id` header purely so cc_service's own
    `reject_tenant_override()` can verify-and-reject on mismatch against
    its authenticated credential's bound organization -- defense in
    depth, not a second source of truth.

    **Known architectural constraint, inherited from Task 01C, not solved
    here.** Commercial Core's Credential A
    (`cc_service/auth/config.py::ServiceAuthSettings` in
    Thundhai/SIE-Commercial-Core) is, by that module's own explicit
    design, "single-credential... bound to exactly one organization, per
    deployed instance" -- there is no mechanism today for one Commercial
    Core deployment to serve more than one organization's Attention data.
    Since `COMMERCIAL_CORE_CLIENT_ID`/`COMMERCIAL_CORE_CLIENT_SECRET` are
    configured once, process-wide, for this Public SIE deployment, a
    request whose authorized `organization_id` is *not* the one
    Commercial Core's credential is bound to will be rejected by
    cc_service's own `reject_tenant_override()` with `TENANT_MISMATCH`
    (mapped, like every other `CommercialCoreAuthorizationError`, to a
    503 `MODEL_NOT_AVAILABLE` here -- see
    `app/api/v1/intelligence.py::_map_commercial_core_attention_error()`).
    Public SIE itself remains multi-tenant; a given Commercial Core
    deployment, as built today, does not extend that across arbitrary
    Public SIE organizations. This is not addressed by this class and
    must not be read as solved by it -- extending Commercial Core to a
    real multi-tenant credential/authorization model is out of scope
    here and belongs to a future Commercial Core milestone.
    """

    def __init__(self, *, base_url: str, client_id: str, client_secret: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._authorization_header = f"Bearer {client_id}:{client_secret}"
        self._timeout_seconds = timeout_seconds

    def unavailable(self, capability: str) -> CommercialCoreUnavailable:
        return CommercialCoreUnavailable(capability)

    def get_attention(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
    ) -> AttentionResultDTO:
        import httpx

        headers = {
            "Authorization": self._authorization_header,
            "X-SIE-Contract-Version": sie_contract.__version__,
            "X-Organization-Id": str(organization_id),
        }
        if request_id:
            headers["X-Request-Id"] = request_id

        body = {
            "scope": scope,
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "window_days": window_days,
        }

        log_fields = {"endpoint": f"{self._base_url}{_ATTENTION_PATH}", "request_id": request_id}
        logger.info("commercial_core.attention.request_started", extra=log_fields)

        # Deliberately a single attempt, no automatic retry -- mirrors
        # Task 01C's own domain_client, which has none by design (see
        # this task's own "Do NOT implement automatic retries" instruction).
        # Caught and re-raised outside this try/except (never `raise ... from
        # exc` or a bare `raise` inside the handler) so the new exception's
        # `__context__` is never set at all -- not merely display-suppressed.
        # A real httpx.TimeoutException/TransportError carries `.request`,
        # including the real `Authorization` header this method just sent;
        # `from None` alone stops it appearing in a standard traceback, but
        # leaves the original exception object (and that header) reachable
        # via `__context__` to anything that walks the chain directly rather
        # than through traceback formatting (e.g. some error-tracking SDKs) --
        # verified empirically, not merely theoretical.
        transport_failure: CommercialCoreIntegrationError | None = None
        try:
            response = httpx.post(
                f"{self._base_url}{_ATTENTION_PATH}",
                json=body,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            logger.warning("commercial_core.attention.timeout", extra=log_fields)
            transport_failure = CommercialCoreTimeoutError("Commercial Core did not respond in time.")
        except httpx.TransportError:
            logger.warning("commercial_core.attention.connection_failed", extra=log_fields)
            transport_failure = CommercialCoreConnectionError("Could not reach Commercial Core.")
        if transport_failure is not None:
            raise transport_failure

        if response.status_code == 200:
            logger.info("commercial_core.attention.response_received", extra=log_fields)
            try:
                return AttentionResultDTO(**response.json())
            except Exception:
                logger.error("commercial_core.attention.malformed_response", extra=log_fields)
                raise CommercialCoreMalformedResponseError(
                    "Commercial Core returned a successful response that does not match "
                    "the expected contract shape."
                ) from None

        error_code: str | None = None
        try:
            error_code = ErrorResponse(**response.json()).error_code
        except Exception:
            pass  # Falls through to the generic, status-code-only handling below.

        if response.status_code == 401:
            logger.error("commercial_core.attention.authentication_failed", extra=log_fields)
            raise CommercialCoreAuthenticationError(
                "Commercial Core rejected this deployment's own service credential."
            ) from None
        if response.status_code == 403:
            logger.error(
                "commercial_core.attention.authorization_failed", extra={**log_fields, "error_code": error_code}
            )
            if error_code == KnownErrorCode.TENANT_MISMATCH:
                raise CommercialCoreAuthorizationError(
                    "Commercial Core rejected this request's tenant binding."
                ) from None
            raise CommercialCoreAuthorizationError("Commercial Core denied this request.") from None
        if response.status_code == 422:
            logger.warning("commercial_core.attention.validation_failed", extra=log_fields)
            raise CommercialCoreValidationError("Commercial Core rejected the request as invalid.") from None
        if response.status_code == 503:
            logger.warning("commercial_core.attention.dependency_unavailable", extra=log_fields)
            raise CommercialCoreDependencyUnavailableError(
                "A Commercial Core dependency is currently unavailable."
            ) from None

        logger.error(
            "commercial_core.attention.unexpected_status",
            extra={**log_fields, "status_code": response.status_code},
        )
        raise CommercialCoreUnexpectedStatusError(
            f"Commercial Core returned an unexpected HTTP status ({response.status_code})."
        ) from None


commercial_core_client: CommercialCoreClient = NotConfiguredCommercialCoreClient()


def build_commercial_core_client(
    *,
    base_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout_seconds: float | None = None,
) -> CommercialCoreClient:
    """Construct a client from explicit arguments, falling back to app
    settings for anything omitted -- mirrors
    `app.llm.provider.build_llm_provider()`/
    `app.embeddings.provider.build_embedding_provider()` exactly. Split
    out from `get_commercial_core_client()` (which is cached) so tests
    can build an uncached, differently configured instance.

    Fails closed, at call time, on a genuine misconfiguration (some but
    not all of base_url/client_id/client_secret set) by raising
    `CommercialCoreConfigurationError` -- never at import time or at
    `Settings()` construction, and never by silently proceeding with a
    partial credential. When none of the three are set at all, returns
    the same `NotConfiguredCommercialCoreClient` singleton every other
    still-extracted capability already uses, so `NotConfiguredCommercialCoreClient`
    behavior remains available and production startup never fails merely
    because Commercial Core is not yet configured.
    """
    base_url = base_url if base_url is not None else settings.COMMERCIAL_CORE_BASE_URL
    client_id = client_id if client_id is not None else settings.COMMERCIAL_CORE_CLIENT_ID
    client_secret = client_secret if client_secret is not None else settings.COMMERCIAL_CORE_CLIENT_SECRET
    timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.COMMERCIAL_CORE_TIMEOUT_SECONDS

    fields = (
        ("COMMERCIAL_CORE_BASE_URL", base_url),
        ("COMMERCIAL_CORE_CLIENT_ID", client_id),
        ("COMMERCIAL_CORE_CLIENT_SECRET", client_secret),
    )
    provided = [name for name, value in fields if value]
    if not provided:
        return commercial_core_client

    missing = [name for name, value in fields if not value]
    if missing:
        raise CommercialCoreConfigurationError(
            "Commercial Core is partially configured; missing: " + ", ".join(missing)
        )

    return HttpCommercialCoreClient(
        base_url=base_url, client_id=client_id, client_secret=client_secret, timeout_seconds=timeout_seconds
    )


@lru_cache
def get_commercial_core_client() -> CommercialCoreClient:
    """Return the process-wide default client, built from app settings and
    cached -- mirrors `app.llm.provider.get_llm_provider()`. Callers that
    need a specific/uncached client (tests) should use
    `build_commercial_core_client()` instead."""
    return build_commercial_core_client()
