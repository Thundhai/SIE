"""LLMProvider — the boundary between SIE's RAG layer and whatever actually
turns a grounded prompt into response text.

Mirrors `app/embeddings/provider.py::EmbeddingProvider`'s shape exactly —
the same "configuration-based boundary, nothing above it imports a
concrete implementation" pattern already established for embeddings and
for `app/ingestion/storage.py::get_storage_provider()`. Nothing in
`app/rag/` (in particular `RAGService`) imports `httpx`, an OpenAI SDK, or
any other commercial-provider client directly — it depends on the
`LLMProvider` protocol and asks `get_llm_provider()` for one.

**The LLM is not the source of truth — see the README's "Evidence-Grounded
RAG" section.** This module only decides *which* text-generation
implementation runs; what it is allowed to say, and whether it is even
invoked at all, is entirely `RAGService`'s decision (see
`app/rag/rag_service.py` and `app/rag/sufficiency.py` — evidence
sufficiency is a deterministic rule evaluated *before* any LLM call, never
delegated to the LLM itself).

**Why the default provider is a deterministic fake, not a downloaded
model.** Exactly the same reasoning `EmbeddingProvider`'s own docstring
gives for `HashingEmbeddingProvider`: tests and CI must never require
network access, a commercial API key, or a locally-downloaded model.
`FakeLLMProvider` is a real, working implementation of the interface (not
a mock) — deterministic, offline, and clearly self-identified as a test
provider in every field it returns (`provider_name="fake"`,
`model_name="sie-fake-test-llm"`) so a response can never be mistaken for
one from a real AI model.

`OpenAICompatibleLLMProvider` below is the documented extension point for
a real provider — implemented, lazy-configured, but **not exercised
against a real model/API in this environment** (no reachable LLM API in
this session's sandboxed egress policy; see the README and the final
report for the corrective-milestone precedent — the identical honesty
principle `SentenceTransformerEmbeddingProvider` follows). Do not present
it as validated.

**Guardrail against shipping the test provider by accident.** `LLM_PROVIDER`
defaults to `"fake"` — the identical asymmetry `EmbeddingProvider`'s own
docstring documents for `EMBEDDING_PROVIDER`/`HashingEmbeddingProvider`:
unlike `DEV_MODE` (whose unsafe value is *not* the default), the test/CI-safe
default here is also the value that must never quietly end up serving real
production traffic. `build_llm_provider()` raises
`FakeLLMProviderInProductionError` — a hard failure, the same "fail closed"
shape `DEV_MODE` and `EmbeddingProvider`'s own guard already use — whenever
it would resolve to `"fake"` while `settings.APP_ENV` is `"production"`/
`"prod"`.

Never a commercial AI provider hardcoded here or anywhere in the domain
layer — `LLM_PROVIDER` is an app setting (`app/core/config.py`), resolved
once, at the edge. API keys are read from settings (environment
variables) at construction time and never logged, never included in any
`LLMResponse`/exception message, and never exposed through any API
response (see `app/api/v1/rag.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.core.config import settings

# Same APP_ENV convention as app/embeddings/provider.py's
# _PRODUCTION_APP_ENVS — kept as an identical, separately-defined
# constant here (not imported from that module) so app/llm/ has no
# dependency on app/embeddings/ at all; the two guards are conceptually
# identical but operate on unrelated settings.
_PRODUCTION_APP_ENVS = frozenset({"production", "prod"})


class FakeLLMProviderInProductionError(RuntimeError):
    """Raised by `build_llm_provider()` (and therefore by
    `get_llm_provider()`) when it would resolve to `FakeLLMProvider` while
    `settings.APP_ENV` names a real deployment. See this module's
    docstring — identical shape to
    `app.embeddings.provider.HashingProviderInProductionError`."""


class LLMProviderError(RuntimeError):
    """Raised by `LLMProvider.generate()` on any failure — network error,
    timeout, API error, malformed response from the underlying service,
    etc. `RAGService` catches this and returns a structured failure
    response (milestone item 28): it never falls back to fabricated
    content, and never silently swaps providers."""


@dataclass(frozen=True)
class LLMGenerationConfig:
    """Generation configuration a caller may tune, always within the
    server-enforced limits in `app/core/config.py` — a client of the RAG
    API can never raise these past what the deployment allows (see
    `app/api/v1/rag.py`)."""

    temperature: float = 0.0
    max_output_tokens: int = 800
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class LLMRequest:
    """What every `LLMProvider.generate()` call receives — exactly the
    four things the milestone spec names: system instructions, grounded
    context, the user's question, and generation configuration. Kept as
    three separate string fields (never concatenated into one blob by
    this module) so a provider implementation can place them in whatever
    structure its own API expects (e.g. a system message vs. a user
    message) while `app/rag/context_builder.py` remains the single place
    that decides their *content* and the delimiting between trusted
    instructions and untrusted retrieved evidence — see that module's
    docstring for the prompt-injection defense this split exists for."""

    system_instructions: str
    grounded_context: str
    user_question: str
    config: LLMGenerationConfig = field(default_factory=LLMGenerationConfig)


@dataclass(frozen=True)
class LLMUsage:
    """Usage metadata, where available — never fabricated when a provider
    doesn't report it (all fields `None` in that case, not a guessed
    number)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    """What every `LLMProvider.generate()` call returns. `provider` /
    `model` / `model_version` are always the *real* identity of whatever
    generated `text` — never omitted, never disguised (see this module's
    docstring on why `FakeLLMProvider` never claims to be a real model)."""

    text: str
    provider: str
    model: str
    model_version: str | None = None
    usage: LLMUsage | None = None
    request_id: str | None = None
    response_id: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """The interface every LLM implementation satisfies. `RAGService`
    depends on this, never on a concrete class. `is_external` is read by
    `RAGService`'s privacy boundary check (milestone item 39,
    `app/core/config.py::ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA`) — `True`
    for any provider that sends the grounded context to a
    network-reachable service outside this process, `False` for one that
    never leaves it (only `FakeLLMProvider` today)."""

    provider_name: str
    model_name: str
    model_version: str | None
    is_external: bool

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate response text for `request`. Raises `LLMProviderError`
        on any failure — never returns fabricated text in place of a real
        failure."""
        ...


class FakeLLMProvider:
    """Deterministic, dependency-free, offline test/dev LLM provider — see
    this module's docstring for why this, not a downloaded or commercial
    model, is the provider actually exercised by this codebase's test
    suite. **This is not a real AI model and never claims to be one** —
    every field it returns says so explicitly (`provider_name="fake"`,
    `model_name="sie-fake-test-llm"`).

    Default behavior (no `canned_response` given): builds a short,
    templated answer that cites the first evidence item(s) it finds `[Ei]`
    markers for in the supplied grounded context, phrased as
    "Based on the retrieved evidence..." (never "The law requires...") —
    deterministic and genuinely grounded in whatever context it was
    actually given, so tests can assert on citations/grounding without
    needing real model output.

    Configurable failure modes let tests deterministically exercise the
    behaviors the milestone spec explicitly requires coverage for:

      * `canned_response=...` — return this exact text instead of the
        default templated answer (citation validation tests, the
        "unsupported claim"/hallucination-simulation test — milestone
        item 32 — and the prompt-injection test, which asserts the
        *injected* text never appears in this canned response).
      * `fail=True` — every `generate()` call raises `LLMProviderError`
        (provider-failure tests — milestone item 37).

    `self.calls` records every `LLMRequest` this instance actually
    received, in order — the mechanism `RAGService`'s abstention tests use
    to assert the LLM was *never invoked at all* when evidence is
    insufficient (see `app/rag/rag_service.py`'s own docstring): the
    deterministic sufficiency gate runs before any provider call, so a
    provider configured to hallucinate a confident answer never gets the
    chance to.
    """

    provider_name = "fake"
    model_name = "sie-fake-test-llm"
    model_version = "v1"
    is_external = False

    def __init__(
        self,
        *,
        canned_response: str | None = None,
        fail: bool = False,
        fail_message: str = "The fake test LLM provider was configured to fail.",
    ) -> None:
        self._canned_response = canned_response
        self._fail = fail
        self._fail_message = fail_message
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._fail:
            raise LLMProviderError(self._fail_message)

        text = (
            self._canned_response
            if self._canned_response is not None
            else self._default_grounded_answer(request)
        )
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self.model_name,
            model_version=self.model_version,
            usage=LLMUsage(
                prompt_tokens=len(request.system_instructions) // 4
                + len(request.grounded_context) // 4
                + len(request.user_question) // 4,
                completion_tokens=len(text) // 4,
                total_tokens=None,
            ),
            request_id=f"fake-{uuid.uuid4()}",
            response_id=f"fake-{uuid.uuid4()}",
        )

    def _default_grounded_answer(self, request: LLMRequest) -> str:
        import re

        citation_ids = re.findall(r"\[E\d+\]", request.grounded_context)
        if not citation_ids:
            # No evidence was supplied at all. RAGService never calls a
            # provider in this situation in practice (the deterministic
            # sufficiency gate short-circuits first) — this branch exists
            # so the fake provider itself never fabricates a confident
            # answer even if invoked directly outside that guardrail.
            return (
                "I do not have sufficient supporting evidence to answer this "
                "question."
            )
        cited = " ".join(dict.fromkeys(citation_ids[:2]))  # first 1-2, de-duplicated
        return (
            f"Based on the retrieved evidence, this is addressed in {cited}. "
            f"See the cited evidence for the exact requirement text. {cited}"
        )


class OpenAICompatibleLLMProvider:
    """Extension point for a real provider — any HTTP service exposing an
    OpenAI-compatible `/chat/completions` endpoint (this covers OpenAI
    itself, and many self-hosted/open-source inference servers that speak
    the same schema — e.g. vLLM, llama.cpp's server, Ollama's
    OpenAI-compatible endpoint), configured entirely through
    `app/core/config.py` settings, never hardcoded. Selected via
    `LLM_PROVIDER=openai_compatible`.

    **Not exercised against a real model/API in this environment** — see
    this module's docstring. Implemented and reviewable, but its
    `generate()` path has not been run against a live endpoint here.

    The API key (`settings.LLM_API_KEY`) is read once at construction and
    sent only as the `Authorization` header of the one HTTP request this
    class makes — never logged, never placed on `self` under a name that
    would appear in a `repr()`/traceback, and never returned in any
    `LLMResponse`.
    """

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str | None = None,
        api_base_url: str | None = None,
        is_external: bool = True,
    ) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:  # pragma: no cover - httpx is a direct dependency today
            raise RuntimeError(
                "LLM_PROVIDER=openai_compatible requires the 'httpx' package."
            ) from exc

        if not settings.LLM_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=openai_compatible requires LLM_API_KEY to be set "
                "(an environment variable, never committed to the repository). "
                "Use LLM_PROVIDER=fake (the default) for tests/CI/development."
            )

        self.model_name = model_name
        self.model_version = model_version
        self.is_external = is_external
        self._api_base_url = (api_base_url or "https://api.openai.com/v1").rstrip("/")
        self._api_key = settings.LLM_API_KEY  # never logged, never re-exposed

    def generate(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover - network
        import httpx

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": request.system_instructions},
                {
                    "role": "user",
                    "content": f"{request.grounded_context}\n\n{request.user_question}",
                },
            ],
            "temperature": request.config.temperature,
            "max_tokens": request.config.max_output_tokens,
        }
        try:
            response = httpx.post(
                f"{self._api_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=request.config.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
        except Exception as exc:
            # Never leak the API key via the exception message — httpx's
            # own exceptions don't include request headers, so this is
            # safe to re-raise with only a generic description.
            raise LLMProviderError(
                f"OpenAICompatibleLLMProvider request failed: {exc}"
            ) from exc

        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self.model_name,
            model_version=self.model_version,
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            request_id=body.get("id"),
            response_id=body.get("id"),
        )


def build_llm_provider(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
) -> LLMProvider:
    """Construct a provider from explicit arguments, falling back to app
    settings for anything omitted. Split out from `get_llm_provider()`
    (which is cached) so tests can build an uncached, differently
    configured instance — mirrors
    `app.embeddings.provider.build_embedding_provider()` exactly."""
    provider = provider or settings.LLM_PROVIDER
    if provider == "fake" and settings.APP_ENV.lower() in _PRODUCTION_APP_ENVS:
        raise FakeLLMProviderInProductionError(
            f"LLM_PROVIDER=fake with APP_ENV={settings.APP_ENV!r}. FakeLLMProvider "
            "is a deterministic, offline test/dev provider — it is NOT a real AI "
            "model and must not serve as SIE's real reasoning/generation layer. "
            "Configure LLM_PROVIDER=openai_compatible (or another real provider "
            "wired through the LLMProvider abstraction) before serving real "
            "production traffic, or set APP_ENV to a non-production value if "
            "this really is a test/dev/CI deployment."
        )
    if provider == "fake":
        return FakeLLMProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            model_name=model_name or settings.LLM_MODEL_NAME,
            model_version=model_version or settings.LLM_MODEL_VERSION,
            api_base_url=settings.LLM_API_BASE_URL,
            is_external=settings.LLM_PROVIDER_IS_EXTERNAL,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER {provider!r}. Supported: 'fake', 'openai_compatible'."
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return the process-wide default provider, built from app settings
    and cached — mirrors `app.embeddings.provider.get_embedding_provider()`.
    Callers that need a specific/uncached provider (tests, in particular
    every test that wants to configure a `FakeLLMProvider` with
    `canned_response`/`fail`) should use `build_llm_provider()` or
    construct `FakeLLMProvider(...)` directly instead."""
    return build_llm_provider()
