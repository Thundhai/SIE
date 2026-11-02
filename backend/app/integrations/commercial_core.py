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
from sie_contract import (
    TENANT_ASSERTION_HEADER,
    TenantCapability,
    ActorType,
    AnalyticsSignalsResultDTO,
    AnalyticsSummaryDTO,
    AnalyticsTrendDTO,
    AttentionResultDTO,
    DecisionListResultDTO,
    DecisionReferenceDTO,
    EnterpriseIntelligenceResultDTO,
    ErrorResponse,
    KnownErrorCode,
    RAGAnswerDTO,
    RAGOutcome,
)

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.integrations.tenant_assertion import (
    TenantActor,
    TenantAssertionSigner,
    build_tenant_assertion_signer,
)

logger = logging.getLogger("sie.integrations.commercial_core")

_ATTENTION_PATH = "/internal/v1/attention"
_ANALYTICS_SUMMARY_PATH = "/internal/v1/analytics/summary"
_ANALYTICS_TRENDS_PATH = "/internal/v1/analytics/trends"
_ANALYTICS_SIGNALS_PATH = "/internal/v1/analytics/signals"
_ENTERPRISE_INTELLIGENCE_PATH = "/internal/v1/intelligence/enterprise"
_DECISIONS_PATH = "/internal/v1/decisions"
_DECISIONS_GET_PATH = "/internal/v1/decisions/get"
_DECISIONS_LIST_PATH = "/internal/v1/decisions/list"
_RAG_QUERY_PATH = "/internal/v1/rag/query"


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


class CommercialCoreTenantAssertionRejectedError(CommercialCoreAuthenticationError):
    """Commercial Core rejected the signed tenant assertion (401
    `TENANT_ASSERTION_INVALID`): a signing-key, issuer or clock problem
    on this deployment, never the caller's fault. Commercial Core's
    message never says which check failed."""


class CommercialCoreTenantNotEntitledError(CommercialCoreAuthorizationError):
    """Commercial Core is not enabled for this organization, or not for
    this capability (403 `TENANT_NOT_ENTITLED`)."""


class CommercialCoreValidationError(CommercialCoreIntegrationError):
    """cc_service rejected the request body itself (422)."""


class CommercialCoreNotFoundError(CommercialCoreIntegrationError):
    """cc_service reported 404 -- Decisions' own create/get can both
    404 (an unknown `decision_id`, `site_id`, or `linked_action_id`, or
    an `attention_reference` that does not match any current Attention
    item), and every site-scoped Attention, Analytics and Enterprise
    Intelligence read 404s for a `site_id` that is not a site of the
    request's organization (Commercial Core's own site-ownership check --
    a missing site and another organization's site look identical). The
    caller's own request being wrong, never a dependency failure --
    mapped to a 404, not treated as `MODEL_NOT_AVAILABLE` like every
    other `CommercialCoreIntegrationError`."""


class CommercialCoreDependencyUnavailableError(CommercialCoreIntegrationError):
    """cc_service reported its own downstream (the Domain Service)
    unavailable (503)."""


class CommercialCoreCapabilityDisabledError(CommercialCoreDependencyUnavailableError):
    """cc_service returned 503 with `retryable: false` -- the capability is
    switched off (or not provisioned) on that Commercial Core deployment,
    so retrying will not help until an operator turns it on. Today only
    RAG reports this (`DOMAIN_SERVICE_RAG_ENABLED` off, or no production
    model/embedding provider). Still a `CommercialCoreDependencyUnavailableError`,
    so every existing caller keeps treating it as a 503."""


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
        tenant_actor: TenantActor | None = None,
    ) -> AttentionResultDTO:
        raise NotImplementedError

    def get_analytics_summary(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSummaryDTO:
        raise NotImplementedError

    def get_analytics_trends(
        self,
        *,
        organization_id: uuid.UUID,
        metric: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsTrendDTO:
        raise NotImplementedError

    def get_analytics_signals(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSignalsResultDTO:
        raise NotImplementedError

    def get_enterprise_intelligence(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> EnterpriseIntelligenceResultDTO:
        raise NotImplementedError

    def create_decision(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime,
        window_days: int,
        attention_reference: str,
        decision_type: str,
        rationale: str,
        linked_action_id: uuid.UUID | None,
        actor_type: ActorType,
        actor_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        raise NotImplementedError

    def get_decision(
        self,
        *,
        organization_id: uuid.UUID,
        decision_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        raise NotImplementedError

    def list_decisions(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        attention_reference: str | None,
        decision_type: str | None,
        linked_action_id: uuid.UUID | None,
        page: int,
        page_size: int,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionListResultDTO:
        raise NotImplementedError

    def query_rag(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        top_k: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> RAGAnswerDTO:
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
        tenant_actor: TenantActor | None = None,
    ) -> AttentionResultDTO:
        raise self.unavailable("Attention")

    def get_analytics_summary(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSummaryDTO:
        raise self.unavailable("Analytics summary")

    def get_analytics_trends(
        self,
        *,
        organization_id: uuid.UUID,
        metric: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsTrendDTO:
        raise self.unavailable("Analytics trends")

    def get_analytics_signals(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSignalsResultDTO:
        raise self.unavailable("Analytics signals")

    def get_enterprise_intelligence(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> EnterpriseIntelligenceResultDTO:
        raise self.unavailable("Enterprise intelligence")

    def create_decision(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime,
        window_days: int,
        attention_reference: str,
        decision_type: str,
        rationale: str,
        linked_action_id: uuid.UUID | None,
        actor_type: ActorType,
        actor_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        raise self.unavailable("Intelligence decision recording/history")

    def get_decision(
        self,
        *,
        organization_id: uuid.UUID,
        decision_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        raise self.unavailable("Intelligence decision recording/history")

    def list_decisions(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        attention_reference: str | None,
        decision_type: str | None,
        linked_action_id: uuid.UUID | None,
        page: int,
        page_size: int,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionListResultDTO:
        raise self.unavailable("Intelligence decision recording/history")

    def query_rag(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        top_k: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> RAGAnswerDTO:
        raise self.unavailable("Evidence-grounded RAG query")


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

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: float,
        rag_timeout_seconds: float | None = None,
        tenant_assertion_signer: TenantAssertionSigner | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._tenant_assertion_signer = tenant_assertion_signer
        self._authorization_header = f"Bearer {client_id}:{client_secret}"
        self._timeout_seconds = timeout_seconds
        self._rag_timeout_seconds = (
            rag_timeout_seconds if rag_timeout_seconds is not None else settings.COMMERCIAL_CORE_RAG_TIMEOUT_SECONDS
        )

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
        tenant_actor: TenantActor | None = None,
    ) -> AttentionResultDTO:
        import httpx

        headers = {
            "Authorization": self._authorization_header,
            "X-SIE-Contract-Version": sie_contract.__version__,
            "X-Organization-Id": str(organization_id),
        }
        if request_id:
            headers["X-Request-Id"] = request_id
        self._add_tenant_assertion(
            headers,
            organization_id=organization_id,
            capability=TenantCapability.ATTENTION_READ,
            tenant_actor=tenant_actor,
            request_id=request_id,
        )

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
        error_message: str | None = None
        try:
            parsed_error = ErrorResponse(**response.json())
            error_code = parsed_error.error_code
            error_message = parsed_error.message
        except Exception:
            pass  # Falls through to the generic, status-code-only handling below.

        if response.status_code == 401 and error_code == KnownErrorCode.TENANT_ASSERTION_INVALID:
            logger.error("commercial_core.attention.tenant_assertion_rejected", extra=log_fields)
            raise CommercialCoreTenantAssertionRejectedError(
                "Commercial Core rejected this deployment's tenant assertion."
            ) from None
        if response.status_code == 401:
            logger.error("commercial_core.attention.authentication_failed", extra=log_fields)
            raise CommercialCoreAuthenticationError(
                "Commercial Core rejected this deployment's own service credential."
            ) from None
        if response.status_code == 403:
            logger.error(
                "commercial_core.attention.authorization_failed", extra={**log_fields, "error_code": error_code}
            )
            if error_code == KnownErrorCode.TENANT_NOT_ENTITLED:
                raise CommercialCoreTenantNotEntitledError(
                    "Commercial Core is not enabled for this organization."
                ) from None
            if error_code == KnownErrorCode.TENANT_MISMATCH:
                raise CommercialCoreAuthorizationError(
                    "Commercial Core rejected this request's tenant binding."
                ) from None
            raise CommercialCoreAuthorizationError("Commercial Core denied this request.") from None
        if response.status_code == 404:
            logger.warning("commercial_core.attention.not_found", extra=log_fields)
            raise CommercialCoreNotFoundError(
                error_message or "Commercial Core reported that the requested resource does not exist."
            ) from None
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

    def _add_tenant_assertion(
        self,
        headers: dict[str, str],
        *,
        organization_id: uuid.UUID,
        capability: TenantCapability,
        tenant_actor: TenantActor | None,
        request_id: str | None,
    ) -> None:
        """Adds the signed tenant assertion (SIE-2) when this deployment
        signs them. Without a signer nothing is added and Commercial
        Core's `legacy`/`dual` modes serve the call as before."""
        if self._tenant_assertion_signer is None:
            return
        if tenant_actor is None:
            # Every router passes its actor; a call without one goes
            # unsigned, which Commercial Core's `multi` mode refuses.
            logger.warning("commercial_core.tenant_assertion.no_actor", extra={"capability": capability.value})
            return
        headers[TENANT_ASSERTION_HEADER] = self._tenant_assertion_signer.sign(
            organization_id=organization_id, actor=tenant_actor, capability=capability, request_id=request_id
        )

    def _post_and_decode(
        self,
        path: str,
        body: dict,
        *,
        organization_id: uuid.UUID,
        request_id: str | None,
        log_name: str,
        capability: TenantCapability,
        tenant_actor: TenantActor | None,
        expected_status: int = 200,
        timeout_seconds: float | None = None,
    ):
        """Shared request/response mechanics for the three Analytics
        methods below -- headers, transport-failure mapping, and
        non-2xx mapping are identical to `get_attention()`'s own
        inline implementation above (kept separate, not refactored
        into this shared helper, so this addition cannot change that
        already-verified method's behavior). Returns the decoded JSON
        body on `expected_status` (200 for every pre-existing caller;
        Decisions' own create call passes 201, the one write in this
        client); raises the same typed exceptions `get_attention()`
        raises, on every other outcome. `404` maps to
        `CommercialCoreNotFoundError` carrying Commercial Core's own safe
        message, never a 503: this is the caller's own request being
        wrong (an unknown `decision_id`, or a `site_id` outside the
        request's organization), not a dependency failure."""
        import httpx

        headers = {
            "Authorization": self._authorization_header,
            "X-SIE-Contract-Version": sie_contract.__version__,
            "X-Organization-Id": str(organization_id),
        }
        if request_id:
            headers["X-Request-Id"] = request_id
        self._add_tenant_assertion(
            headers,
            organization_id=organization_id,
            capability=capability,
            tenant_actor=tenant_actor,
            request_id=request_id,
        )

        log_fields = {"endpoint": f"{self._base_url}{path}", "request_id": request_id}
        logger.info(f"commercial_core.{log_name}.request_started", extra=log_fields)

        transport_failure: CommercialCoreIntegrationError | None = None
        try:
            response = httpx.post(
                f"{self._base_url}{path}",
                json=body,
                headers=headers,
                timeout=timeout_seconds if timeout_seconds is not None else self._timeout_seconds,
            )
        except httpx.TimeoutException:
            logger.warning(f"commercial_core.{log_name}.timeout", extra=log_fields)
            transport_failure = CommercialCoreTimeoutError("Commercial Core did not respond in time.")
        except httpx.TransportError:
            logger.warning(f"commercial_core.{log_name}.connection_failed", extra=log_fields)
            transport_failure = CommercialCoreConnectionError("Could not reach Commercial Core.")
        if transport_failure is not None:
            raise transport_failure

        if response.status_code == expected_status:
            logger.info(f"commercial_core.{log_name}.response_received", extra=log_fields)
            try:
                return response.json()
            except Exception:
                logger.error(f"commercial_core.{log_name}.malformed_response", extra=log_fields)
                raise CommercialCoreMalformedResponseError(
                    "Commercial Core returned a successful response that does not match "
                    "the expected contract shape."
                ) from None

        error_code: str | None = None
        error_message: str | None = None
        error_retryable: bool | None = None
        try:
            parsed_error = ErrorResponse(**response.json())
            error_code = parsed_error.error_code
            error_message = parsed_error.message
            error_retryable = parsed_error.retryable
        except Exception:
            pass  # Falls through to the generic, status-code-only handling below.

        if response.status_code == 401 and error_code == KnownErrorCode.TENANT_ASSERTION_INVALID:
            logger.error(f"commercial_core.{log_name}.tenant_assertion_rejected", extra=log_fields)
            raise CommercialCoreTenantAssertionRejectedError(
                "Commercial Core rejected this deployment's tenant assertion."
            ) from None
        if response.status_code == 401:
            logger.error(f"commercial_core.{log_name}.authentication_failed", extra=log_fields)
            raise CommercialCoreAuthenticationError(
                "Commercial Core rejected this deployment's own service credential."
            ) from None
        if response.status_code == 403:
            logger.error(f"commercial_core.{log_name}.authorization_failed", extra={**log_fields, "error_code": error_code})
            if error_code == KnownErrorCode.TENANT_NOT_ENTITLED:
                raise CommercialCoreTenantNotEntitledError(
                    "Commercial Core is not enabled for this organization."
                ) from None
            if error_code == KnownErrorCode.TENANT_MISMATCH:
                raise CommercialCoreAuthorizationError(
                    "Commercial Core rejected this request's tenant binding."
                ) from None
            raise CommercialCoreAuthorizationError("Commercial Core denied this request.") from None
        if response.status_code == 404:
            logger.warning(f"commercial_core.{log_name}.not_found", extra=log_fields)
            raise CommercialCoreNotFoundError(error_message or "Commercial Core reported that the requested resource does not exist.") from None
        if response.status_code == 422:
            logger.warning(f"commercial_core.{log_name}.validation_failed", extra=log_fields)
            raise CommercialCoreValidationError("Commercial Core rejected the request as invalid.") from None
        if response.status_code == 503 and error_retryable is False:
            logger.warning(f"commercial_core.{log_name}.capability_disabled", extra=log_fields)
            raise CommercialCoreCapabilityDisabledError(
                "This Commercial Core capability is not enabled on its deployment."
            ) from None
        if response.status_code == 503:
            logger.warning(f"commercial_core.{log_name}.dependency_unavailable", extra=log_fields)
            raise CommercialCoreDependencyUnavailableError(
                "A Commercial Core dependency is currently unavailable."
            ) from None

        logger.error(f"commercial_core.{log_name}.unexpected_status", extra={**log_fields, "status_code": response.status_code})
        raise CommercialCoreUnexpectedStatusError(
            f"Commercial Core returned an unexpected HTTP status ({response.status_code})."
        ) from None

    def get_analytics_summary(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSummaryDTO:
        body = {
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "window_days": window_days,
        }
        decoded = self._post_and_decode(
            _ANALYTICS_SUMMARY_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="analytics_summary",
            capability=TenantCapability.ANALYTICS_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return AnalyticsSummaryDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def get_analytics_trends(
        self,
        *,
        organization_id: uuid.UUID,
        metric: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsTrendDTO:
        body = {
            "metric": metric,
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "period_days": window_days,
        }
        decoded = self._post_and_decode(
            _ANALYTICS_TRENDS_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="analytics_trends",
            capability=TenantCapability.ANALYTICS_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return AnalyticsTrendDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def get_analytics_signals(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> AnalyticsSignalsResultDTO:
        body = {
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "window_days": window_days,
        }
        decoded = self._post_and_decode(
            _ANALYTICS_SIGNALS_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="analytics_signals",
            capability=TenantCapability.ANALYTICS_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return AnalyticsSignalsResultDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def get_enterprise_intelligence(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime | None,
        window_days: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> EnterpriseIntelligenceResultDTO:
        body = {
            "scope": scope,
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat() if as_of is not None else None,
            "window_days": window_days,
        }
        decoded = self._post_and_decode(
            _ENTERPRISE_INTELLIGENCE_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="enterprise_intelligence",
            capability=TenantCapability.ENTERPRISE_INTELLIGENCE_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return EnterpriseIntelligenceResultDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def create_decision(
        self,
        *,
        organization_id: uuid.UUID,
        scope: str,
        site_id: uuid.UUID | None,
        as_of: datetime,
        window_days: int,
        attention_reference: str,
        decision_type: str,
        rationale: str,
        linked_action_id: uuid.UUID | None,
        actor_type: ActorType,
        actor_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        body = {
            "scope": scope,
            "site_id": str(site_id) if site_id is not None else None,
            "as_of": as_of.isoformat(),
            "window_days": window_days,
            "attention_reference": attention_reference,
            "decision_type": decision_type,
            "rationale": rationale,
            "linked_action_id": str(linked_action_id) if linked_action_id is not None else None,
            "actor_type": actor_type.value,
            "actor_id": str(actor_id),
        }
        decoded = self._post_and_decode(
            _DECISIONS_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="decisions_create",
            capability=TenantCapability.DECISIONS_WRITE,
            tenant_actor=tenant_actor,
            expected_status=201,
        )
        try:
            return DecisionReferenceDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def get_decision(
        self,
        *,
        organization_id: uuid.UUID,
        decision_id: uuid.UUID,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionReferenceDTO:
        body = {"decision_id": str(decision_id)}
        decoded = self._post_and_decode(
            _DECISIONS_GET_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="decisions_get",
            capability=TenantCapability.DECISIONS_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return DecisionReferenceDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def list_decisions(
        self,
        *,
        organization_id: uuid.UUID,
        site_id: uuid.UUID | None,
        attention_reference: str | None,
        decision_type: str | None,
        linked_action_id: uuid.UUID | None,
        page: int,
        page_size: int,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> DecisionListResultDTO:
        body = {
            "site_id": str(site_id) if site_id is not None else None,
            "attention_reference": attention_reference,
            "decision_type": decision_type,
            "linked_action_id": str(linked_action_id) if linked_action_id is not None else None,
            "page": page,
            "page_size": page_size,
        }
        decoded = self._post_and_decode(
            _DECISIONS_LIST_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="decisions_list",
            capability=TenantCapability.DECISIONS_READ,
            tenant_actor=tenant_actor,
        )
        try:
            return DecisionListResultDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None

    def query_rag(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        top_k: int | None,
        request_id: str | None,
        tenant_actor: TenantActor | None = None,
    ) -> RAGAnswerDTO:
        """One evidence-grounded question to cc_service's
        `POST /internal/v1/rag/query`. The body is `query`/`top_k` only:
        cc_service takes the organization from its own credential's
        `TenantContext` and rejects a body `organization_id`, so it travels
        only as the usual `X-Organization-Id` verify-and-reject header.

        Decodes against `sie_contract.RAGAnswerDTO` (contract 0.8.0). A
        response for a different organization or a different question, or
        an `ANSWERED` one citing no evidence, is treated as malformed,
        never returned. The query text is never logged. Uses
        RAG's own, longer timeout (`COMMERCIAL_CORE_RAG_TIMEOUT_SECONDS`)
        because the answer includes a model call."""
        body = {"query": query, "top_k": top_k}
        decoded = self._post_and_decode(
            _RAG_QUERY_PATH,
            body,
            organization_id=organization_id,
            request_id=request_id,
            log_name="rag_query",
            capability=TenantCapability.RAG_QUERY,
            tenant_actor=tenant_actor,
            timeout_seconds=self._rag_timeout_seconds,
        )
        try:
            dto = RAGAnswerDTO(**decoded)
        except Exception:
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned a successful response that does not match the expected contract shape."
            ) from None
        if dto.organization_id != organization_id:
            logger.error("commercial_core.rag_query.organization_mismatch", extra={"request_id": request_id})
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned an answer for a different organization than the one requested."
            )
        if dto.query != query:
            logger.error("commercial_core.rag_query.query_mismatch", extra={"request_id": request_id})
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned an answer to a different question than the one asked."
            )
        if dto.outcome is RAGOutcome.ANSWERED and not dto.citations:
            # Commercial Core never answers without citing evidence (an
            # uncited answer becomes UNSUPPORTED_CLAIM_REJECTED), so one
            # that arrives uncited is not evidence-grounded.
            logger.error("commercial_core.rag_query.answer_without_citations", extra={"request_id": request_id})
            raise CommercialCoreMalformedResponseError(
                "Commercial Core returned an answer that cites no evidence."
            )
        return dto


TENANT_NOT_ENTITLED_REASON = "TENANT_NOT_ENTITLED"


def tenant_not_entitled_error() -> ApiError:
    """What a router returns for `CommercialCoreTenantNotEntitledError`:
    a 403 that says the feature is not enabled for this organization,
    distinct from the 503 every dependency failure gets."""
    return ApiError(
        status_code=403,
        code=ErrorCode.TENANT_ACCESS_DENIED,
        message="This feature is not enabled for this organization.",
        details={"reason": TENANT_NOT_ENTITLED_REASON},
    )


commercial_core_client: CommercialCoreClient = NotConfiguredCommercialCoreClient()


def build_commercial_core_client(
    *,
    base_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout_seconds: float | None = None,
    rag_timeout_seconds: float | None = None,
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
    rag_timeout_seconds = (
        rag_timeout_seconds if rag_timeout_seconds is not None else settings.COMMERCIAL_CORE_RAG_TIMEOUT_SECONDS
    )

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
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        timeout_seconds=timeout_seconds,
        rag_timeout_seconds=rag_timeout_seconds,
        tenant_assertion_signer=build_tenant_assertion_signer(),
    )


@lru_cache
def get_commercial_core_client() -> CommercialCoreClient:
    """Return the process-wide default client, built from app settings and
    cached -- mirrors `app.llm.provider.get_llm_provider()`. Callers that
    need a specific/uncached client (tests) should use
    `build_commercial_core_client()` instead."""
    return build_commercial_core_client()
