"""OpenAICompatibleEmbeddingProvider (EMBEDDING_PROVIDER=openai_compatible):
request shape, batching and ordering, normalization, the external-data
gate, and fail-closed errors. All HTTP goes to an in-process
`httpx.MockTransport`; nothing touches the network.
"""

from __future__ import annotations

import json
import math
import types

import httpx
import pytest

from app.embeddings.provider import (
    EmbeddingInferenceError,
    EmbeddingModelLoadError,
    EmbeddingOutputValidationError,
    EmbeddingProviderUnavailableError,
    ExternalEmbeddingsNotAllowedError,
    HashingProviderInProductionError,
    OpenAICompatibleEmbeddingProvider,
    build_embedding_provider,
)

KEY = "dummy"
DIMS = 4


def _vector(seed: int, dims: int = DIMS) -> list[float]:
    return [float(seed + i + 1) for i in range(dims)]


def _transport(requests: list[dict], *, status: int = 200, dims: int = DIMS, shuffle: bool = False, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append({"url": str(request.url), "auth": request.headers.get("authorization"), "payload": payload})
        if body is not None:
            return httpx.Response(status, json=body)
        data = [{"index": i, "embedding": _vector(len(text), dims)} for i, text in enumerate(payload["input"])]
        if shuffle:
            data.reverse()
        return httpx.Response(status, json={"data": data, "model": payload["model"]})

    return httpx.MockTransport(handler)


def _provider(requests: list[dict], **kwargs) -> OpenAICompatibleEmbeddingProvider:
    transport_kwargs = {k: kwargs.pop(k) for k in ("status", "dims", "shuffle", "body") if k in kwargs}
    options = {
        "model_name": "text-embedding-3-small",
        "model_version": "v1",
        "dimensions": DIMS,
        "api_key": KEY,
        "allow_external": True,
        "client": httpx.Client(transport=_transport(requests, **transport_kwargs)),
    }
    options.update(kwargs)
    return OpenAICompatibleEmbeddingProvider(**options)


def test_request_shape_and_unit_length_output():
    requests: list[dict] = []
    vectors = _provider(requests, api_base_url="https://llm.example/v1/").embed_texts(["alpha", "beta"])

    assert requests == [
        {
            "url": "https://llm.example/v1/embeddings",
            "auth": f"Bearer {KEY}",
            "payload": {"model": "text-embedding-3-small", "input": ["alpha", "beta"]},
        }
    ]
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == DIMS
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)


def test_defaults_to_the_openai_endpoint():
    requests: list[dict] = []
    _provider(requests).embed_text("alpha")
    assert requests[0]["url"] == "https://api.openai.com/v1/embeddings"


def test_dimensions_are_requested_only_when_enabled():
    requests: list[dict] = []
    _provider(requests, send_dimensions=True).embed_text("alpha")
    assert requests[0]["payload"]["dimensions"] == DIMS


def test_batches_preserve_input_order_even_when_the_api_reorders():
    requests: list[dict] = []
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    vectors = _provider(requests, batch_size=2, shuffle=True).embed_texts(texts)

    assert [len(r["payload"]["input"]) for r in requests] == [2, 2, 1]
    expected = [_vector(len(t)) for t in texts]
    for vector, raw in zip(vectors, expected):
        norm = math.sqrt(sum(v * v for v in raw))
        assert vector == pytest.approx([v / norm for v in raw])


def test_an_external_api_is_refused_unless_allowed():
    with pytest.raises(ExternalEmbeddingsNotAllowedError, match="ALLOW_EXTERNAL_EMBEDDINGS_FOR_PRIVATE_DATA"):
        _provider([], allow_external=False)
    # A self-hosted API inside the deployment boundary is not external.
    _provider([], allow_external=False, is_external=False, api_base_url="http://embeddings.internal:8080/v1").embed_text(
        "alpha"
    )


def test_a_self_hosted_api_must_name_its_url():
    # Otherwise the OpenAI default would get the text with the gate skipped.
    with pytest.raises(EmbeddingModelLoadError, match="EMBEDDING_API_BASE_URL"):
        _provider([], allow_external=False, is_external=False)


@pytest.mark.parametrize("url", ["http://llm.example/v1", " HTTP://llm.example/v1", "ftp://llm.example"])
def test_an_external_api_must_use_https(url):
    with pytest.raises(EmbeddingModelLoadError, match="https://"):
        _provider([], api_base_url=url)


def test_a_missing_key_is_refused():
    with pytest.raises(EmbeddingModelLoadError, match="EMBEDDING_API_KEY"):
        _provider([], api_key=None)


@pytest.mark.parametrize(
    "kwargs,texts,error,fragment",
    [
        ({"status": 400}, ["alpha", "beta"], EmbeddingInferenceError, "HTTP 400"),
        ({"dims": DIMS + 1}, ["alpha", "beta"], EmbeddingOutputValidationError, "5-dimensional"),
        ({"body": {"unexpected": True}}, ["alpha"], EmbeddingOutputValidationError, "malformed"),
        ({"body": {"data": [{"index": 0, "embedding": _vector(1)}]}}, ["alpha", "beta"], EmbeddingOutputValidationError, "count mismatch"),
        ({"body": {"data": [{"index": 0, "embedding": [0.0] * DIMS}]}}, ["alpha"], EmbeddingOutputValidationError, "all-zero"),
        ({"body": {"data": [{"index": 0, "embedding": [1e200] * DIMS}]}}, ["alpha"], EmbeddingOutputValidationError, "overflowing"),
    ],
)
def test_bad_responses_fail_closed_without_leaking_the_key(kwargs, texts, error, fragment):
    with pytest.raises(error, match=fragment) as raised:
        _provider([], **kwargs).embed_texts(texts)
    assert KEY not in str(raised.value)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_values_are_rejected(token):
    # Python's json module accepts these tokens, so they reach the vector.
    raw = '{"data": [{"index": 0, "embedding": [1.0, %s, 1.0, 1.0]}]}' % token
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=raw)))
    with pytest.raises(EmbeddingOutputValidationError, match="non-finite"):
        _provider([], client=client).embed_text("alpha")


@pytest.mark.parametrize("status", [401, 403, 404, 408, 429, 500, 503])
def test_request_wide_failures_are_unavailable_errors(status):
    with pytest.raises(EmbeddingProviderUnavailableError, match=f"HTTP {status}") as raised:
        _provider([], status=status).embed_texts(["alpha", "beta"])
    assert KEY not in str(raised.value)


def test_a_network_failure_is_an_unavailable_error():
    def boom(request):
        raise httpx.ConnectError("unreachable")

    provider = _provider([], client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(EmbeddingProviderUnavailableError, match="ConnectError"):
        provider.embed_text("alpha")


def test_the_timeout_bounds_the_whole_call(monkeypatch):
    requests: list[dict] = []
    timeouts: list[float] = []
    clock = iter([100.0, 100.0, 107.0, 111.0])
    # A stand-in for the module's `time`, so httpx keeps the real clock.
    monkeypatch.setattr("app.embeddings.provider.time", types.SimpleNamespace(monotonic=lambda: next(clock)))
    provider = _provider(requests, batch_size=1, timeout_seconds=10)
    real_post = provider._client.post

    def post(*args, timeout, **kwargs):
        timeouts.append(timeout)
        return real_post(*args, timeout=timeout, **kwargs)

    provider._client.post = post
    with pytest.raises(EmbeddingProviderUnavailableError, match="10s budget"):
        provider.embed_texts(["a", "b", "c"])
    assert timeouts == [10.0, 3.0] and len(requests) == 2


def test_empty_text_is_rejected_before_any_request():
    requests: list[dict] = []
    with pytest.raises(ValueError, match="index 1"):
        _provider(requests).embed_texts(["alpha", "  "])
    assert requests == []


def test_build_embedding_provider_wires_every_setting(monkeypatch):
    for name, value in {
        "EMBEDDING_PROVIDER": "openai_compatible",
        "EMBEDDING_MODEL_NAME": "text-embedding-3-small",
        "EMBEDDING_DIMENSIONS": 256,
        "EMBEDDING_API_BASE_URL": "https://llm.example/v1",
        "EMBEDDING_API_KEY": KEY,
        "EMBEDDING_API_SEND_DIMENSIONS": True,
        "EMBEDDING_BATCH_SIZE": 16,
        "ALLOW_EXTERNAL_EMBEDDINGS_FOR_PRIVATE_DATA": True,
        "APP_ENV": "production",
    }.items():
        monkeypatch.setattr(f"app.core.config.settings.{name}", value)

    provider = build_embedding_provider()
    assert isinstance(provider, OpenAICompatibleEmbeddingProvider)
    assert (provider.model_name, provider.dimensions, provider.is_external) == ("text-embedding-3-small", 256, True)
    assert provider._url == "https://llm.example/v1/embeddings"
    assert provider._send_dimensions is True and provider.max_batch_size == 16

    # The production guard still refuses the hashing provider.
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    with pytest.raises(HashingProviderInProductionError):
        build_embedding_provider()


def test_build_embedding_provider_refuses_external_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_API_KEY", KEY)
    with pytest.raises(ExternalEmbeddingsNotAllowedError):
        build_embedding_provider()
