"""Milestone spec item 22: the deterministic test/dev embedding provider.

Pure unit tests — no database, no network. `HashingEmbeddingProvider` is
the *only* provider actually exercised anywhere in this milestone's test
suite or evaluation harness (see app/embeddings/provider.py's own
docstring for why) — these tests are what back that claim.
"""

import math

import pytest

from app.embeddings.provider import (
    HashingEmbeddingProvider,
    HashingProviderInProductionError,
    build_embedding_provider,
    get_embedding_provider,
)


def test_embedding_is_deterministic_for_the_same_text():
    provider = HashingEmbeddingProvider(dimensions=64)
    a = provider.embed_text("Workers must wear a harness when working at height.")
    b = provider.embed_text("Workers must wear a harness when working at height.")
    assert a == b


def test_embedding_has_the_configured_dimension():
    provider = HashingEmbeddingProvider(dimensions=128)
    vector = provider.embed_text("Some safety text.")
    assert len(vector) == 128


def test_embedding_is_l2_normalized():
    provider = HashingEmbeddingProvider(dimensions=64)
    vector = provider.embed_text("Confined space entry requires atmospheric testing.")
    norm = math.sqrt(sum(v * v for v in vector))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_empty_or_stopword_only_text_returns_zero_vector_without_raising():
    provider = HashingEmbeddingProvider(dimensions=32)
    assert provider.embed_text("") == [0.0] * 32
    assert provider.embed_text("the a an of") == [0.0] * 32


def test_embed_texts_batches_in_the_same_order_as_embed_text():
    provider = HashingEmbeddingProvider(dimensions=32)
    texts = ["fall protection harness", "confined space entry", "permit to work"]
    batched = provider.embed_texts(texts)
    individual = [provider.embed_text(t) for t in texts]
    assert batched == individual


def test_topically_similar_text_scores_higher_than_unrelated_text():
    provider = HashingEmbeddingProvider(dimensions=256)
    height_a = provider.embed_text(
        "Workers must wear a full-body harness when working at height above 1.8 metres."
    )
    height_b = provider.embed_text(
        "Fall protection equipment such as a harness is required at height."
    )
    unrelated = provider.embed_text(
        "The quarterly financial report shows revenue growth in the software division."
    )

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert cos(height_a, height_b) > cos(height_a, unrelated)


def test_provider_identity_fields_are_set():
    provider = HashingEmbeddingProvider(
        model_name="custom-model", model_version="v2", dimensions=16
    )
    assert provider.provider_name == "hashing"
    assert provider.model_name == "custom-model"
    assert provider.model_version == "v2"
    assert provider.dimensions == 16


def test_dimensions_must_be_positive():
    import pytest

    with pytest.raises(ValueError):
        HashingEmbeddingProvider(dimensions=0)


def test_build_embedding_provider_reads_app_settings_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_DIMENSIONS", 48)
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_MODEL_NAME", "configured-model")
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_MODEL_VERSION", "v9")

    provider = build_embedding_provider()

    assert isinstance(provider, HashingEmbeddingProvider)
    assert provider.dimensions == 48
    assert provider.model_name == "configured-model"
    assert provider.model_version == "v9"


def test_build_embedding_provider_rejects_unknown_provider_name():
    import pytest

    with pytest.raises(ValueError):
        build_embedding_provider(provider="not-a-real-provider")


def test_get_embedding_provider_is_cached():
    assert get_embedding_provider() is get_embedding_provider()


# --- Production-hashing-provider guardrail ---
#
# HashingEmbeddingProvider is the safe-for-tests default, which is the
# opposite direction of DEV_MODE's safety (the unsafe-for-production
# value is *not* the default there) — so nothing else stops
# EMBEDDING_PROVIDER=hashing from quietly reaching a real deployment.
# build_embedding_provider() (and therefore get_embedding_provider(),
# the function application startup and every request path actually
# call) closes that gap by refusing to construct the provider at all —
# a hard failure, the same "fail closed" shape DEV_MODE already uses for
# auth — rather than merely logging about it. These tests are what back
# that claim.


def test_hashing_provider_in_production_app_env_fails_hard(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "production")

    with pytest.raises(HashingProviderInProductionError, match="NOT a trained semantic model"):
        build_embedding_provider()


def test_hashing_provider_in_prod_app_env_also_fails_hard(monkeypatch):
    """'prod' is treated the same as 'production' — a real deployment
    should not slip past this check just by spelling APP_ENV differently."""
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "prod")

    with pytest.raises(HashingProviderInProductionError):
        build_embedding_provider()


def test_get_embedding_provider_startup_path_also_fails_hard_in_production(monkeypatch):
    """get_embedding_provider() — what application startup and every
    request path actually call, not build_embedding_provider() directly
    — must refuse too: a misconfigured production deployment cannot
    serve a single request on the hashing provider."""
    get_embedding_provider.cache_clear()
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "production")

    try:
        with pytest.raises(HashingProviderInProductionError):
            get_embedding_provider()
    finally:
        # lru_cache does not cache a raised exception, but clear
        # defensively so this test can never leak state into another.
        get_embedding_provider.cache_clear()


@pytest.mark.parametrize("app_env", ["development", "test", "testing", "ci", "staging", ""])
def test_hashing_provider_is_allowed_outside_production(monkeypatch, app_env):
    """Development, test, and CI environments are unaffected — only
    APP_ENV values naming a real deployment ("production"/"prod") are
    refused."""
    monkeypatch.setattr("app.core.config.settings.EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", app_env)

    provider = build_embedding_provider()

    assert isinstance(provider, HashingEmbeddingProvider)


def test_sentence_transformers_provider_in_production_is_not_refused(monkeypatch):
    """The guard is specifically about the hashing provider reaching
    production, not about production configuration in general. Stubs out
    the real (network-dependent) SentenceTransformerEmbeddingProvider
    construction so this stays a fast, offline unit test."""
    import app.embeddings.provider as provider_module

    class _StubSentenceTransformerProvider:
        provider_name = "sentence_transformers"

        def __init__(self, *, model_name=None, model_version=None, device=None, cache_folder=None, batch_size=32):
            self.model_name = model_name
            self.model_version = model_version
            self.dimensions = 384

    monkeypatch.setattr(
        provider_module, "SentenceTransformerEmbeddingProvider", _StubSentenceTransformerProvider
    )
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "production")

    provider = build_embedding_provider(provider="sentence_transformers")

    assert isinstance(provider, _StubSentenceTransformerProvider)
