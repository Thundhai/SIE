"""EmbeddingProvider — the boundary between SIE and whatever actually
turns text into a vector.

This module is deliberately the *only* place that decides which concrete
embedding implementation runs. Nothing above it (`EmbeddingService`,
`RetrievalService`) imports a concrete provider directly — they depend on
the `EmbeddingProvider` protocol and ask `get_embedding_provider()` for
one, the same "configuration-based boundary" shape already used by
`app/ingestion/storage.py::get_storage_provider()`.

**Why the default provider is a deterministic hash embedding, not a
downloaded model.** The milestone spec is explicit: if a model dependency
would make the test suite unreliable or require downloading large model
weights, build a deterministic test provider and a production-provider
abstraction instead of hard-coding a heavy or commercial dependency into
the domain layer. This environment has no reliable place to cache a
multi-hundred-megabyte sentence-transformer download for every test run
or CI invocation, so `HashingEmbeddingProvider` is the *only* provider
actually exercised in this milestone — for development, for the test
suite, and for the evaluation harness alike. It is a real, working
implementation of the interface (not a mock): a seeded, order-independent
bag-of-words feature-hashing embedding (the same "hashing trick" used by
e.g. scikit-learn's `HashingVectorizer` / Vowpal Wabbit), fully
deterministic and dependency-free. It is **not** a trained semantic
model, and nothing in this codebase claims otherwise — see the README's
"Semantic Knowledge Architecture" section for what this does and does not
mean for retrieval quality.

`SentenceTransformerEmbeddingProvider` below is the documented extension
point for a real local/open-source embedding model
(`sentence-transformers`, per the milestone's own suggestion) — the
interface a future swap would implement. It lazy-imports its dependency
inside `__init__`, not at module import time, so this module (and every
caller of `get_embedding_provider()`) stays importable, and the test
suite stays offline, whether or not that optional dependency is
installed. It has not been exercised against a real model download in
this environment; do not present it as validated.

Never a commercial AI provider hardcoded here or anywhere in the domain
layer — `EMBEDDING_PROVIDER` is an app setting (`app/core/config.py`),
resolved once, at the edge.

**Guardrail against shipping the test provider by accident.**
`EMBEDDING_PROVIDER` defaults to `"hashing"` — unlike `DEV_MODE`, whose
unsafe value is *not* the default, the test/CI-safe default here is also
the value that must never quietly end up serving real production
traffic. `build_embedding_provider()` therefore logs a loud `WARNING`
(not a hard failure — see that function's own comment for why) whenever
it resolves to `"hashing"` while `settings.APP_ENV` is `"production"`/
`"prod"`, naming exactly what to do instead
(`EMBEDDING_PROVIDER=sentence_transformers`, or another real model wired
through this same abstraction).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# APP_ENV values treated as "this is a real deployment", for the
# production-hashing-provider warning below. Unlike DEV_MODE (an
# auth-safety setting that fails *closed* by defaulting to the safe
# value), EMBEDDING_PROVIDER's safe-for-tests default ("hashing") is
# also the value that must never be *silently* carried into a real
# deployment — so this is the one place APP_ENV is actually read for
# behavior, not just recorded.
_PRODUCTION_APP_ENVS = frozenset({"production", "prod"})

# A small, generic stopword list. Two tiers, both domain-agnostic (not
# tuned to any particular topic's vocabulary): standard English function
# words (articles, prepositions, conjunctions — the usual TF-IDF/BM25
# stopword set), plus a handful of regulatory/procedural filler words
# ("required", "shall", "before", ...) that are near-universal across
# *any* safety/compliance document regardless of topic and would
# otherwise dilute genuine topical overlap between a query and its
# relevant chunk. Removing them serves the same purpose stopword removal
# always serves in a bag-of-words model, without pulling in a full NLP
# dependency for it.
_STOPWORDS = frozenset(
    """
    a an the this that these those is are was were be been being
    of to in on at for with by from as into over under
    and or but if then than so
    it its it's their there here
    do does did done not no
    all any some each every
    must shall should required require requires requirement requirements
    before after when where while during
    """.split()  # noqa: SIM905 - a readable word list, not a real list literal
)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """The interface every embedding implementation satisfies.
    `EmbeddingService`/`RetrievalService` depend on this, never on a
    concrete class."""

    provider_name: str
    model_name: str
    model_version: str
    dimensions: int

    def embed_text(self, text: str) -> list[float]:
        """Embed a single piece of text into a vector of length
        `self.dimensions`."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed several texts at once, in the same order. The default
        implementations simply loop over `embed_text`; a real model
        provider would override this for real batching efficiency —
        callers should still prefer this method over a manual loop so
        that swap-in is free."""
        ...


class HashingEmbeddingProvider:
    """Deterministic, dependency-free embedding via feature hashing —
    see this module's docstring for why this, and not a trained model,
    is the provider actually used throughout this milestone.

    Algorithm: lowercase, tokenize into words, drop a small generic
    stopword list, hash each surviving token into one of `dimensions`
    buckets with a deterministic sign (the standard "hashing trick" —
    reduces collision bias versus unsigned hashing), weight each
    occurrence by 1 + log(term frequency) (sublinear scaling, so a word
    repeated many times doesn't linearly dominate), sum into one dense
    vector, then L2-normalize. Two texts sharing vocabulary land closer
    together under cosine similarity than two that don't — genuine,
    explainable signal for the evaluation harness in
    tests/fixtures/evaluation/, just not a learned semantic
    representation.
    """

    provider_name = "hashing"

    def __init__(
        self,
        *,
        model_name: str = "sie-hashing-embedder",
        model_version: str = "v1",
        dimensions: int = 256,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.model_name = model_name
        self.model_version = model_version
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]
        if not tokens:
            # Genuinely empty/stopword-only input — a zero vector is the
            # honest answer (EmbeddingService does not call this for
            # empty chunk content in the first place; this guard is
            # purely so the provider itself never raises).
            return vector

        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        for token, count in counts.items():
            index, sign = self._hash_token(token)
            weight = 1.0 + math.log(count)
            vector[index] += sign * weight

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def _hash_token(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        as_int = int.from_bytes(digest, "big")
        index = as_int % self.dimensions
        sign = 1.0 if (as_int >> 63) & 1 else -1.0
        return index, sign


class SentenceTransformerEmbeddingProvider:
    """Documented extension point for a real local/open-source embedding
    model — **not exercised in this environment** (no `sentence-
    transformers`/model weights available; see this module's docstring).
    Lazy-imports its dependency so importing this module never requires
    it. Selected via `EMBEDDING_PROVIDER=sentence_transformers`, distinct
    from — and not the default over — `HashingEmbeddingProvider`.
    """

    provider_name = "sentence_transformers"

    def __init__(self, *, model_name: str = "all-MiniLM-L6-v2", model_version: str = "1") -> None:
        try:
            # type: ignore[import-not-found]
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "EMBEDDING_PROVIDER=sentence_transformers requires the optional "
                "'sentence-transformers' package, which is not installed in this "
                "environment. Install it, or use EMBEDDING_PROVIDER=hashing "
                "(the default)."
            ) from exc

        self.model_name = model_name
        self.model_version = model_version
        self._model = SentenceTransformer(model_name)
        self.dimensions = self._model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - optional
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


def build_embedding_provider(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    dimensions: int | None = None,
) -> EmbeddingProvider:
    """Construct a provider from explicit arguments, falling back to app
    settings for anything omitted. Split out from `get_embedding_provider()`
    (which is cached) so tests can build an uncached, differently-configured
    instance without disturbing the process-wide cache."""
    provider = provider or settings.EMBEDDING_PROVIDER
    if provider == "hashing" and settings.APP_ENV.lower() in _PRODUCTION_APP_ENVS:
        # A loud warning, not a hard failure: HashingEmbeddingProvider is
        # a real, working implementation (tenant isolation, provenance,
        # retrieval all function correctly with it) — just not a trained
        # semantic model (see this module's docstring and the README's
        # "Semantic Knowledge Architecture" / "Known gaps" sections).
        # Refusing to start would be safer for a genuine production
        # deployment, but would also break any legitimate non-production
        # use of APP_ENV=production (e.g. a prod-configuration smoke
        # test). This warning is deliberately impossible to miss instead.
        logger.warning(
            "EMBEDDING_PROVIDER=hashing with APP_ENV=%r. "
            "HashingEmbeddingProvider is a deterministic, dependency-free "
            "feature-hashing embedding built for tests/CI/evaluation — it "
            "is NOT a trained semantic model and must not be relied on as "
            "SIE's real semantic retrieval engine. Configure "
            "EMBEDDING_PROVIDER=sentence_transformers (or another real "
            "model wired through the EmbeddingProvider abstraction) "
            "before serving real production traffic.",
            settings.APP_ENV,
        )
    if provider == "hashing":
        return HashingEmbeddingProvider(
            model_name=model_name or settings.EMBEDDING_MODEL_NAME,
            model_version=model_version or settings.EMBEDDING_MODEL_VERSION,
            dimensions=dimensions or settings.EMBEDDING_DIMENSIONS,
        )
    if provider == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(
            model_name=model_name or settings.EMBEDDING_MODEL_NAME,
            model_version=model_version or settings.EMBEDDING_MODEL_VERSION,
        )
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER {provider!r}. Supported: 'hashing', "
        "'sentence_transformers'."
    )


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Return the process-wide default provider, built from app settings
    and cached — mirrors `app/ingestion/storage.py::get_storage_provider()`'s
    shape. Callers that need a specific/uncached provider (tests, the
    evaluation harness pinning a model identity) should use
    `build_embedding_provider()` directly instead."""
    return build_embedding_provider()
