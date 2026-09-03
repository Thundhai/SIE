"""SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization
v0.1, item 20's "Provider" required-test list — exercised against a real
`SentenceTransformerEmbeddingProvider` instance wrapping a real (if tiny,
offline-constructed — see tests/sentence_transformers_support.py)
`sentence_transformers.SentenceTransformer` model. No mock of the
provider class itself anywhere in this file: every test either
constructs the real class against a real model, or verifies it fails
closed against a real, deliberately-invalid input/model.

Self-skips when the optional `sentence-transformers` package isn't
installed — see tests/sentence_transformers_support.py's own docstring
for why that dependency is not in backend/requirements.txt.
"""

from __future__ import annotations

import pytest

from app.embeddings.provider import (
    EmbeddingInferenceError,
    EmbeddingModelLoadError,
    EmbeddingOutputValidationError,
    SentenceTransformerEmbeddingProvider,
)
from tests.sentence_transformers_support import build_tiny_offline_model, requires_sentence_transformers

DIMENSIONS = 32


@pytest.fixture
def tiny_model_dir(tmp_path):
    model = build_tiny_offline_model(dimensions=DIMENSIONS)
    output_dir = tmp_path / "tiny_model"
    model.save(str(output_dir))
    return output_dir


@pytest.fixture
def provider(tiny_model_dir):
    return SentenceTransformerEmbeddingProvider(
        model_name=str(tiny_model_dir), model_version="test-v1"
    )


# --- Real semantic embedding / dimension / shape -----------------------------------------


@requires_sentence_transformers
def test_embed_text_produces_a_real_vector_of_the_reported_dimension(provider):
    vector = provider.embed_text("safety harness at height")
    assert isinstance(vector, list)
    assert len(vector) == DIMENSIONS == provider.dimensions
    assert all(isinstance(v, float) for v in vector)
    assert any(v != 0.0 for v in vector)  # a real vector, not a degenerate all-zero output


@requires_sentence_transformers
def test_output_shape_is_deterministic_across_calls(provider):
    first = provider.embed_text("chemical spill in confined space")
    second = provider.embed_text("chemical spill in confined space")
    assert len(first) == len(second) == provider.dimensions
    # A real model with update_embeddings=False and no dropout at eval
    # time is deterministic for the same input — exact equality, not
    # merely "close".
    assert first == second


@requires_sentence_transformers
def test_provider_reports_its_own_real_model_dimension(provider):
    assert provider.dimensions == DIMENSIONS
    assert provider.provider_name == "sentence_transformers"


# --- Batch ordering -----------------------------------------------------------------------


@requires_sentence_transformers
def test_batch_embedding_preserves_input_order(provider):
    texts = ["safety harness", "chemical spill", "confined space entry", "crane lift plan"]
    batch_vectors = provider.embed_texts(texts)
    individual_vectors = [provider.embed_text(t) for t in texts]

    assert len(batch_vectors) == len(texts)
    for batch_vector, individual_vector in zip(batch_vectors, individual_vectors):
        assert batch_vector == individual_vector


@requires_sentence_transformers
def test_batch_embedding_calls_the_model_once_not_once_per_text(provider, monkeypatch):
    call_count = 0
    original_encode = provider._model.encode

    def counting_encode(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_encode(*args, **kwargs)

    monkeypatch.setattr(provider._model, "encode", counting_encode)

    provider.embed_texts(["safety harness", "chemical spill", "confined space entry"])

    assert call_count == 1, "embed_texts() must call the model once for the whole batch, not once per text."


# --- Empty input ----------------------------------------------------------------------------


@requires_sentence_transformers
def test_empty_batch_returns_empty_list_without_calling_the_model(provider, monkeypatch):
    def _fail(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("embed_texts([]) must not call the model at all")

    monkeypatch.setattr(provider._model, "encode", _fail)
    assert provider.embed_texts([]) == []


@requires_sentence_transformers
def test_empty_string_in_a_batch_is_rejected(provider):
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        provider.embed_texts(["a real text", "   ", "another real text"])


@requires_sentence_transformers
def test_none_like_whitespace_only_single_text_is_rejected(provider):
    with pytest.raises(ValueError):
        provider.embed_texts([""])


# --- Invalid configuration / model load failure ---------------------------------------------


@requires_sentence_transformers
def test_unknown_model_path_raises_a_typed_load_error():
    with pytest.raises(EmbeddingModelLoadError):
        SentenceTransformerEmbeddingProvider(
            model_name="/nonexistent/path/that/does/not/exist/anywhere",
            model_version="v1",
        )


@requires_sentence_transformers
def test_missing_sentence_transformers_dependency_raises_a_typed_load_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ImportError("simulated: sentence-transformers not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)

    with pytest.raises(EmbeddingModelLoadError, match="sentence-transformers"):
        SentenceTransformerEmbeddingProvider(model_name="anything", model_version="v1")


# --- Inference failure / malformed output ----------------------------------------------------


@requires_sentence_transformers
def test_inference_failure_raises_a_typed_error_not_a_silent_fallback(provider, monkeypatch):
    def broken_encode(*args, **kwargs):
        raise RuntimeError("simulated inference failure (e.g. out of memory)")

    monkeypatch.setattr(provider._model, "encode", broken_encode)

    with pytest.raises(EmbeddingInferenceError, match="simulated inference failure"):
        provider.embed_texts(["safety harness"])


@requires_sentence_transformers
def test_wrong_vector_count_from_the_model_is_rejected(provider, monkeypatch):
    def wrong_count_encode(texts, **kwargs):
        import numpy as np

        # Returns one fewer vector than requested -- a batch-ordering/
        # count contract violation the provider must catch itself.
        return np.zeros((len(texts) - 1, DIMENSIONS), dtype="float32")

    monkeypatch.setattr(provider._model, "encode", wrong_count_encode)

    with pytest.raises(EmbeddingOutputValidationError, match="vector"):
        provider.embed_texts(["one", "two"])


@requires_sentence_transformers
def test_wrong_dimension_from_the_model_is_rejected(provider, monkeypatch):
    def wrong_dim_encode(texts, **kwargs):
        import numpy as np

        return np.zeros((len(texts), DIMENSIONS + 1), dtype="float32")

    monkeypatch.setattr(provider._model, "encode", wrong_dim_encode)

    with pytest.raises(EmbeddingOutputValidationError, match=str(DIMENSIONS)):
        provider.embed_texts(["safety harness"])


@requires_sentence_transformers
def test_invalid_reported_dimension_at_construction_is_rejected(tiny_model_dir, monkeypatch):
    """A model that loads but cannot state a sane output dimension must
    never become a usable provider -- see EmbeddingModelLoadError's own
    docstring."""
    import sentence_transformers

    def zero_dim(self):
        return 0

    monkeypatch.setattr(
        sentence_transformers.SentenceTransformer, "get_embedding_dimension", zero_dim, raising=False
    )
    monkeypatch.setattr(
        sentence_transformers.SentenceTransformer,
        "get_sentence_embedding_dimension",
        zero_dim,
        raising=False,
    )

    with pytest.raises(EmbeddingModelLoadError, match="invalid embedding dimension"):
        SentenceTransformerEmbeddingProvider(model_name=str(tiny_model_dir), model_version="v1")
