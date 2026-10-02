"""Error semantics for the Shared Contract.

Every error that crosses the Public SIE <-> Commercial Core boundary is
one of these -- never a bare exception, a raw HTTP status alone, or a
stack trace. `error_code` is a deliberately open vocabulary (see the
README's "Open vs. closed vocabularies"): Commercial Core may introduce
a new code without that being a breaking contract change, provided a
correctly-written consumer already falls back gracefully on an
unrecognized code (surface `message` verbatim, treat `retryable` as the
one thing it must honor).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """A single, uniform error shape for every boundary-crossing failure."""

    model_config = ConfigDict(frozen=True)

    error_code: str = Field(
        ...,
        description=(
            "Open vocabulary, e.g. 'NOT_FOUND', 'UNAUTHORIZED_ORGANIZATION', "
            "'INTELLIGENCE_UNAVAILABLE', 'VALIDATION_ERROR'. Never an HTTP "
            "status code by itself -- this field names *what went wrong*, "
            "not the transport-level status."
        ),
    )
    message: str = Field(..., description="Human-readable, safe to display to an operator. Never a stack trace or internal exception text.")
    request_id: str | None = Field(
        default=None,
        description="Opaque correlation id for cross-system log correlation, when available. Never contains organization or user data itself.",
    )
    retryable: bool = Field(
        ...,
        description="Whether the same request, unmodified, might succeed later (e.g. a transient dependency outage) as opposed to needing a different request.",
    )


class KnownErrorCode:
    """Plain string constants -- **not a closed enum** -- naming the
    `error_code` values this contract's producers are known to emit
    today. `ErrorResponse.error_code` remains a genuinely open `str`
    vocabulary (see this module's own docstring and README's "Open vs.
    closed vocabularies"): a new code is not a breaking contract change,
    and a correctly-written consumer must already fall back gracefully
    on one it does not recognize. This class exists only so a consumer
    that *does* want to branch on a known code can reference a stable
    name instead of a bare string literal -- adding a member here is
    documentation, never a contract commitment that no other code will
    ever appear.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RECOMMENDATION_GENERATION_FAILURE = "RECOMMENDATION_GENERATION_FAILURE"
    CONFLICT_CHECK_FAILURE = "CONFLICT_CHECK_FAILURE"
    STALE_CANDIDATE = "STALE_CANDIDATE"
    CANDIDATE_MISMATCH = "CANDIDATE_MISMATCH"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    UNSUPPORTED_CONTRACT_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
