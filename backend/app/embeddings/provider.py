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

`SentenceTransformerEmbeddingProvider` below is the real production
implementation (SIE Milestone 21: Real Semantic Embedding & Retrieval
Productionization v0.1) — a genuine `sentence-transformers` model,
selected via `EMBEDDING_PROVIDER=sentence_transformers`, never the
default. It lazy-imports its dependency inside `__init__`, not at module
import time, so this module (and every caller of
`get_embedding_provider()`) stays importable, and the test suite stays
offline, whether or not that optional dependency is installed. See
`docs/SEMANTIC_EMBEDDING.md` for the recommended production model,
licensing, runtime requirements, and exactly how (and how much) this was
validated in a sandboxed environment with no access to the public
`huggingface.co` model hub — that document is explicit about the
difference between "this provider class is real, tested, working code"
and "a specific large pretrained checkpoint's semantic quality was
personally verified in this session," which are not the same claim.

Never a commercial AI provider hardcoded here or anywhere in the domain
layer — `EMBEDDING_PROVIDER` is an app setting (`app/core/config.py`),
resolved once, at the edge.

**Guardrail against shipping the test provider by accident.**
`EMBEDDING_PROVIDER` defaults to `"hashing"` — unlike `DEV_MODE`, whose
unsafe value is *not* the default, the test/CI-safe default here is also
the value that must never quietly end up serving real production
traffic. `build_embedding_provider()` therefore raises
`HashingProviderInProductionError` — a hard failure, the same "fail
closed" shape `DEV_MODE` already uses for auth
(`app/api/deps_auth.py`) — whenever it would resolve to `"hashing"`
while `settings.APP_ENV` is `"production"`/`"prod"`, naming exactly what
to do instead (`EMBEDDING_PROVIDER=sentence_transformers`, or another
real model wired through this same abstraction). Since
`get_embedding_provider()` is what application startup and every request
path actually call, a production deployment misconfigured this way
cannot serve a single request on the hashing provider — it fails before
any embedding is generated, not after silently returning
semantically-meaningless vectors. Development, test, and CI environments
(any other `APP_ENV` value) are unaffected and keep using
`HashingEmbeddingProvider` exactly as before.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.core.config import settings

if TYPE_CHECKING:
    import httpx

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# "Is this a real deployment" (for the production-hashing-provider guard
# below) is `settings.is_production` (app/core/config.py), the one
# predicate every production guard shares. Unlike DEV_MODE (an
# auth-safety setting that fails *closed* by defaulting to the safe
# value), EMBEDDING_PROVIDER's safe-for-tests default ("hashing") is
# also the value that must never be *silently* carried into a real
# deployment.


class EmbeddingProviderError(RuntimeError):
    """Base class for every real-provider failure below — never caught
    and silently converted into a fallback to `HashingEmbeddingProvider`
    anywhere in this codebase (see this module's docstring and item 14 of
    the milestone this introduces it for: "a fallback would make the
    system appear operational while silently degrading semantic
    quality"). `EmbeddingService.embed_chunk`/`embed_chunks_batch` still
    catch this (like any other exception) to report a per-chunk `FAILED`
    outcome rather than crash a whole batch — that is error *reporting*,
    not a fallback to a different, semantically-meaningless provider."""


class EmbeddingModelLoadError(EmbeddingProviderError):
    """Raised when a real embedding model cannot be constructed: the
    optional `sentence-transformers` dependency is not installed, the
    named model/path cannot be resolved (unknown Hub id, no network
    access, a local path that does not exist or is not a valid saved
    model), or it loaded but reported an unusable configuration (e.g. a
    non-positive embedding dimension). Raised eagerly, at provider
    construction time — never deferred to the first `embed_text()` call."""


class EmbeddingInferenceError(EmbeddingProviderError):
    """Raised when a real model's forward pass itself fails for a batch
    that was otherwise valid input (e.g. an out-of-memory error, a
    corrupted model state, an unexpected runtime error inside the
    underlying framework). Distinct from `EmbeddingModelLoadError`
    (happens at construction) and from a plain `ValueError` on malformed
    *input* (raised directly by `embed_texts()` before the model is ever
    called)."""


class EmbeddingOutputValidationError(EmbeddingProviderError):
    """Raised when a model's own output does not match what it claimed
    about itself: a different vector count than input texts, or a vector
    whose length doesn't match `self.dimensions`. This is the "malformed
    model output" / "unexpected embedding dimension" guard — checked
    immediately after every real inference call, before any vector from
    that call is ever returned to `EmbeddingService` or written to the
    database."""


class HashingProviderInProductionError(RuntimeError):
    """Raised by `build_embedding_provider()` (and therefore by
    `get_embedding_provider()`) when it would resolve to
    `HashingEmbeddingProvider` while `settings.APP_ENV` names a real
    deployment. `HashingEmbeddingProvider` is a deterministic,
    dependency-free feature-hashing embedding built for tests/CI/
    evaluation — see this module's docstring — and must never silently
    become SIE's real semantic retrieval engine just because
    `EMBEDDING_PROVIDER` (unlike `DEV_MODE`) defaults to the test-safe
    value. Fixing this means either configuring a real provider
    (`EMBEDDING_PROVIDER=sentence_transformers`, or another model wired
    through the same abstraction) or correcting `APP_ENV` if this really
    is a non-production deployment.
    """

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
    """A real, working `sentence-transformers` embedding provider — the
    production implementation this milestone adds. Lazy-imports its
    dependency so importing this module never requires it; the test
    suite (and CI's default configuration) stays fully offline whether or
    not the optional dependency is installed — see this module's own
    docstring. Selected via `EMBEDDING_PROVIDER=sentence_transformers`,
    distinct from — and never the default over — `HashingEmbeddingProvider`.

    `model_name` doubles as `sentence_transformers.SentenceTransformer`'s
    own `model_name_or_path` argument: a Hugging Face Hub model id (the
    documented production path — downloaded once, then cached locally;
    see `docs/SEMANTIC_EMBEDDING.md`) or a local filesystem directory
    already containing a saved sentence-transformers model (a pre-baked
    cache, or an offline-trained model — see that same document's
    "Evaluation methodology" section for why this second form matters in
    a sandboxed environment with no access to the public model hub). No
    request-supplied value ever reaches this constructor — `model_name`,
    `device`, and `cache_folder` all come from `app.core.config.settings`
    only, resolved once at provider-construction time (see
    `build_embedding_provider()` below and this module's "Security" note
    in `docs/SEMANTIC_EMBEDDING.md`).
    """

    provider_name = "sentence_transformers"

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str,
        device: str | None = None,
        cache_folder: str | None = None,
        batch_size: int = 32,
    ) -> None:
        try:
            # type: ignore[import-not-found]
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingModelLoadError(
                "EMBEDDING_PROVIDER=sentence_transformers requires the optional "
                "'sentence-transformers' package, which is not installed in this "
                "environment. Install it, or use EMBEDDING_PROVIDER=hashing "
                "(the default, deterministic test/dev provider)."
            ) from exc

        self.model_name = model_name
        self.model_version = model_version
        self._batch_size = batch_size

        try:
            self._model = SentenceTransformer(
                model_name, device=device, cache_folder=cache_folder
            )
        except Exception as exc:  # noqa: BLE001 - reported as a clear, typed load failure
            raise EmbeddingModelLoadError(
                f"Could not load embedding model {model_name!r} "
                f"(provider=sentence_transformers): {type(exc).__name__}: {exc}. "
                "This is a fail-closed error, not a fallback -- see "
                "app/embeddings/provider.py's own docstring on why this codebase "
                "never silently substitutes HashingEmbeddingProvider here."
            ) from exc

        # get_sentence_embedding_dimension() was renamed to
        # get_embedding_dimension() in newer sentence-transformers
        # releases; try the current name first, fall back for
        # compatibility with older pinned versions a deployment might use.
        dimension_getter = getattr(
            self._model, "get_embedding_dimension", None
        ) or getattr(self._model, "get_sentence_embedding_dimension", None)
        dimensions = dimension_getter() if dimension_getter is not None else None
        if not dimensions or dimensions <= 0:
            raise EmbeddingModelLoadError(
                f"Model {model_name!r} reported an invalid embedding dimension "
                f"({dimensions!r}). Refusing to construct a provider that cannot "
                "state its own output shape."
            )
        self.dimensions = int(dimensions)

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Real batch inference: one `SentenceTransformer.encode()` call
        for the whole list (internally chunked into `self._batch_size`-
        sized minibatches by that call, not by this method) — never one
        model invocation per text. Preserves input order exactly
        (`encode()`'s own documented contract: `input[i] -> output[i]`,
        and this method never reorders/sorts before encoding). See
        `EmbeddingModelLoadError`/`EmbeddingInferenceError`/
        `EmbeddingOutputValidationError`'s own docstrings for the
        three distinct failure modes this validates against."""
        if not texts:
            return []

        for index, text in enumerate(texts):
            if text is None or not text.strip():
                raise ValueError(
                    f"embed_texts() received an empty or whitespace-only text at "
                    f"index {index}; every element of a batch must have real "
                    "content to embed."
                )

        try:
            vectors = self._model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:  # noqa: BLE001 - reported as a clear, typed inference failure
            raise EmbeddingInferenceError(
                f"Embedding inference failed for a batch of {len(texts)} text(s) "
                f"under model {self.model_name!r}: {type(exc).__name__}: {exc}"
            ) from exc

        if len(vectors) != len(texts):
            raise EmbeddingOutputValidationError(
                f"Model {self.model_name!r} returned {len(vectors)} vector(s) for "
                f"{len(texts)} input text(s) -- a batch-ordering/count mismatch."
            )

        result: list[list[float]] = []
        for index, vector in enumerate(vectors):
            row = [float(value) for value in vector]
            if len(row) != self.dimensions:
                raise EmbeddingOutputValidationError(
                    f"Model {self.model_name!r} returned a {len(row)}-dimensional "
                    f"vector at batch index {index}, but this provider reports "
                    f"dimensions={self.dimensions}."
                )
            result.append(row)
        return result


class EmbeddingProviderUnavailableError(EmbeddingInferenceError):
    """The provider failed for the whole request, not for one input: a
    network error, a timeout, an authentication failure, rate limiting or
    a server error. Retrying the same texts one at a time cannot help and
    would multiply the traffic, so `EmbeddingService` fails the batch
    instead of isolating per chunk."""


class ExternalEmbeddingsNotAllowedError(EmbeddingModelLoadError):
    """An external embedding API is configured but the owner has not
    allowed document text to be sent to a third party
    (`ALLOW_EXTERNAL_EMBEDDINGS_FOR_PRIVATE_DATA`)."""


class OpenAICompatibleEmbeddingProvider:
    """Embeddings from an HTTP API in the OpenAI `/embeddings` shape
    (`POST {base}/embeddings` with `model` and a list `input`; the
    response's `data[i].embedding`, ordered by `data[i].index`). Selected
    via `EMBEDDING_PROVIDER=openai_compatible`.

    Needs no local model or extra memory, so it runs where
    `SentenceTransformerEmbeddingProvider` cannot (a 512 MB instance).
    Fails closed like the other real provider: a missing key, a refused
    external API, an HTTP error, a count mismatch or a wrong-width vector
    each raise a typed `EmbeddingProviderError`, never a fallback.

    Vectors are scaled to unit length, matching
    `SentenceTransformerEmbeddingProvider`'s `normalize_embeddings=True`,
    so similarity scores stay comparable across providers. The API key is
    read from settings only, sent only in the Authorization header, and
    never appears in an exception or log message.
    """

    provider_name = "openai_compatible"

    #: HTTP statuses that mean the request as a whole failed (see
    #: `EmbeddingProviderUnavailableError`); any other non-200 status may
    #: be one bad input, so `EmbeddingService` may isolate it.
    _REQUEST_WIDE_STATUSES = frozenset({401, 403, 404, 408, 429})

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str,
        dimensions: int,
        api_base_url: str | None = None,
        api_key: str | None = None,
        send_dimensions: bool = False,
        batch_size: int = 32,
        timeout_seconds: float = 60.0,
        is_external: bool = True,
        allow_external: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise EmbeddingModelLoadError(
                "EMBEDDING_PROVIDER=openai_compatible requires EMBEDDING_API_KEY to be "
                "set (an environment variable, never committed to the repository)."
            )
        if is_external and not allow_external:
            raise ExternalEmbeddingsNotAllowedError(
                "EMBEDDING_PROVIDER=openai_compatible would send document text to an "
                "external API, and ALLOW_EXTERNAL_EMBEDDINGS_FOR_PRIVATE_DATA is false. "
                "Set it to true only once the provider's data terms are approved, or set "
                "EMBEDDING_PROVIDER_IS_EXTERNAL=false for a self-hosted API."
            )
        if not is_external and not (api_base_url and api_base_url.strip()):
            # Otherwise the OpenAI default would receive the text with the
            # external-data gate above already skipped.
            raise EmbeddingModelLoadError(
                "EMBEDDING_PROVIDER_IS_EXTERNAL=false requires EMBEDDING_API_BASE_URL to name "
                "the self-hosted API."
            )
        base_url = (api_base_url or "https://api.openai.com/v1").strip().rstrip("/")
        if is_external and not base_url.lower().startswith("https://"):
            raise EmbeddingModelLoadError(
                "EMBEDDING_API_BASE_URL must use https:// for an external API: the key and the "
                "document text would otherwise travel unencrypted."
            )
        if dimensions <= 0:
            raise EmbeddingModelLoadError(f"EMBEDDING_DIMENSIONS must be positive, not {dimensions!r}.")
        if batch_size <= 0:
            raise EmbeddingModelLoadError(f"EMBEDDING_BATCH_SIZE must be positive, not {batch_size!r}.")

        import httpx

        self.model_name = model_name
        self.model_version = model_version
        self.dimensions = int(dimensions)
        self.is_external = is_external
        self._url = f"{base_url}/embeddings"
        self._api_key = api_key  # never logged, never re-exposed
        self._send_dimensions = send_dimensions
        self._batch_size = batch_size
        self._timeout_seconds = float(timeout_seconds)
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def max_batch_size(self) -> int:
        """Texts per API request. `EmbeddingService` hands over at most
        this many at a time, so a failure never repeats batches that
        already succeeded."""
        return self._batch_size

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """One request per `batch_size` texts, results in input order.
        `EMBEDDING_INFERENCE_TIMEOUT_SECONDS` bounds the whole call, not
        each request."""
        if not texts:
            return []
        for index, text in enumerate(texts):
            if text is None or not text.strip():
                raise ValueError(
                    f"embed_texts() received an empty or whitespace-only text at "
                    f"index {index}; every element of a batch must have real "
                    "content to embed."
                )
        deadline = time.monotonic() + self._timeout_seconds
        result: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EmbeddingProviderUnavailableError(
                    f"Embedding call for {len(texts)} text(s) under model {self.model_name!r} exceeded "
                    f"its {self._timeout_seconds:g}s budget."
                )
            result.extend(self._embed_batch(texts[start : start + self._batch_size], offset=start, timeout=remaining))
        return result

    def _embed_batch(self, batch: list[str], *, offset: int, timeout: float) -> list[list[float]]:
        payload: dict = {"model": self.model_name, "input": batch}
        if self._send_dimensions:
            payload["dimensions"] = self.dimensions
        try:
            response = self._client.post(
                self._url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"}, timeout=timeout
            )
        except Exception as exc:  # noqa: BLE001 - network failures, reported as typed inference failures
            # httpx exceptions carry no request headers, so the key cannot leak here.
            raise EmbeddingProviderUnavailableError(
                f"Embedding request for {len(batch)} text(s) under model {self.model_name!r} "
                f"failed: {type(exc).__name__}"
            ) from exc
        if response.status_code != 200:
            request_wide = response.status_code in self._REQUEST_WIDE_STATUSES or response.status_code >= 500
            raise (EmbeddingProviderUnavailableError if request_wide else EmbeddingInferenceError)(
                f"Embedding API answered HTTP {response.status_code} for {len(batch)} text(s) "
                f"under model {self.model_name!r}."
            )
        try:
            data = response.json()["data"]
            rows = sorted(data, key=lambda item: item["index"])
            vectors = [[float(value) for value in row["embedding"]] for row in rows]
        except Exception as exc:  # noqa: BLE001 - any malformed body is one typed failure
            raise EmbeddingOutputValidationError(
                f"Embedding API returned a malformed body for model {self.model_name!r}."
            ) from exc
        if len(vectors) != len(batch) or [row["index"] for row in rows] != list(range(len(batch))):
            raise EmbeddingOutputValidationError(
                f"Model {self.model_name!r} returned {len(vectors)} vector(s) for "
                f"{len(batch)} input text(s) -- a batch-ordering/count mismatch."
            )
        normalized: list[list[float]] = []
        for index, vector in enumerate(vectors):
            if len(vector) != self.dimensions:
                raise EmbeddingOutputValidationError(
                    f"Model {self.model_name!r} returned a {len(vector)}-dimensional vector at "
                    f"batch index {offset + index}, but EMBEDDING_DIMENSIONS is {self.dimensions}."
                )
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingOutputValidationError(
                    f"Model {self.model_name!r} returned a non-finite value at batch index {offset + index}."
                )
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0.0 or not math.isfinite(norm):
                raise EmbeddingOutputValidationError(
                    f"Model {self.model_name!r} returned an all-zero or overflowing vector at batch index {offset + index}."
                )
            normalized.append([value / norm for value in vector])
        return normalized


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
    if provider == "hashing" and settings.is_production:
        # A hard failure, not a warning: HashingEmbeddingProvider is a
        # real, working implementation (tenant isolation, provenance,
        # retrieval all function correctly with it) — just not a trained
        # semantic model (see this module's docstring and the README's
        # "Semantic Knowledge Architecture" / "Known gaps" sections).
        # This is the same "fail closed" shape DEV_MODE already uses for
        # auth (app/api/deps_auth.py) — a deployment that would silently
        # serve real traffic on a test/CI provider must refuse to start
        # (or refuse to construct the provider, if get_embedding_provider()
        # is called after startup) rather than merely log about it.
        raise HashingProviderInProductionError(
            f"EMBEDDING_PROVIDER=hashing with APP_ENV={settings.APP_ENV!r}. "
            "HashingEmbeddingProvider is a deterministic, dependency-free "
            "feature-hashing embedding built for tests/CI/evaluation — it "
            "is NOT a trained semantic model and must not serve as SIE's "
            "real semantic retrieval engine. Configure "
            "EMBEDDING_PROVIDER=sentence_transformers or openai_compatible (or another real "
            "model wired through the EmbeddingProvider abstraction) "
            "before serving real production traffic, or set APP_ENV to a "
            "non-production value if this really is a test/dev/CI "
            "deployment."
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
            device=settings.EMBEDDING_DEVICE,
            cache_folder=settings.EMBEDDING_MODEL_CACHE_DIR,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        )
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            model_name=model_name or settings.EMBEDDING_MODEL_NAME,
            model_version=model_version or settings.EMBEDDING_MODEL_VERSION,
            dimensions=dimensions or settings.EMBEDDING_DIMENSIONS,
            api_base_url=settings.EMBEDDING_API_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            send_dimensions=settings.EMBEDDING_API_SEND_DIMENSIONS,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            timeout_seconds=settings.EMBEDDING_INFERENCE_TIMEOUT_SECONDS,
            is_external=settings.EMBEDDING_PROVIDER_IS_EXTERNAL,
            allow_external=settings.ALLOW_EXTERNAL_EMBEDDINGS_FOR_PRIVATE_DATA,
        )
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER {provider!r}. Supported: 'hashing', "
        "'sentence_transformers', 'openai_compatible'."
    )


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Return the process-wide default provider, built from app settings
    and cached — mirrors `app/ingestion/storage.py::get_storage_provider()`'s
    shape. Callers that need a specific/uncached provider (tests, the
    evaluation harness pinning a model identity) should use
    `build_embedding_provider()` directly instead."""
    return build_embedding_provider()
