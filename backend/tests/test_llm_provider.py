"""LLMProvider abstraction — milestone items 1-3.

Pure unit tests — no network, no commercial API key, no real AI model.
`FakeLLMProvider` is the *only* provider actually exercised anywhere in
this milestone's test suite, exactly mirroring
`tests/test_embedding_provider.py`'s own claim for `HashingEmbeddingProvider`.
"""

import pytest

from app.llm.provider import (
    FakeLLMProvider,
    FakeLLMProviderInProductionError,
    LLMGenerationConfig,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    OpenAICompatibleLLMProvider,
    build_llm_provider,
    get_llm_provider,
)


def make_request(**overrides) -> LLMRequest:
    defaults = dict(
        system_instructions="You are SIE.",
        grounded_context="=== RETRIEVED EVIDENCE ===\n[E1]\nContent: Hard hats are required.",
        user_question="Are hard hats required?",
        config=LLMGenerationConfig(),
    )
    defaults.update(overrides)
    return LLMRequest(**defaults)


# --- FakeLLMProvider identity: never disguised as a real model -----------------


def test_fake_provider_identifies_itself_as_a_test_provider():
    provider = FakeLLMProvider()
    assert provider.provider_name == "fake"
    assert "fake" in provider.model_name.lower() or "test" in provider.model_name.lower()
    assert isinstance(provider, LLMProvider)
    assert provider.is_external is False


def test_fake_provider_response_carries_its_real_identity_never_a_real_models():
    response = FakeLLMProvider().generate(make_request())
    assert response.provider == "fake"
    assert response.model == "sie-fake-test-llm"


# --- Deterministic grounded answer ----------------------------------------------


def test_fake_provider_default_answer_cites_evidence_found_in_the_context():
    response = FakeLLMProvider().generate(make_request())
    assert "[E1]" in response.text
    assert "Based on the retrieved evidence" in response.text


def test_fake_provider_default_answer_never_claims_a_law_requires_something():
    response = FakeLLMProvider().generate(make_request())
    assert "the law requires" not in response.text.lower()


def test_fake_provider_is_deterministic_for_the_same_request():
    request = make_request()
    a = FakeLLMProvider().generate(request).text
    b = FakeLLMProvider().generate(request).text
    assert a == b


def test_fake_provider_with_no_evidence_in_context_does_not_fabricate_an_answer():
    request = make_request(grounded_context="=== RETRIEVED EVIDENCE ===\nNo evidence was supplied.")
    response = FakeLLMProvider().generate(request)
    assert "sufficient" in response.text.lower()
    assert "[E" not in response.text


# --- Configurable canned response / failure — deterministic test hooks ---------


def test_fake_provider_canned_response_is_returned_verbatim():
    provider = FakeLLMProvider(canned_response="Hard hats are always required. [E1]")
    response = provider.generate(make_request())
    assert response.text == "Hard hats are always required. [E1]"


def test_fake_provider_fail_mode_raises_llm_provider_error():
    provider = FakeLLMProvider(fail=True, fail_message="simulated outage")
    with pytest.raises(LLMProviderError, match="simulated outage"):
        provider.generate(make_request())


def test_fake_provider_records_every_request_it_receives():
    provider = FakeLLMProvider()
    assert provider.calls == []
    request = make_request()
    provider.generate(request)
    assert provider.calls == [request]


def test_fake_provider_usage_metadata_is_present_not_fabricated_as_a_real_count():
    response = FakeLLMProvider().generate(make_request())
    assert response.usage is not None
    assert response.request_id is not None


# --- build_llm_provider() / get_llm_provider() ----------------------------------


def test_build_llm_provider_reads_app_settings_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_PROVIDER", "fake")
    provider = build_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


def test_build_llm_provider_rejects_unknown_provider_name():
    with pytest.raises(ValueError):
        build_llm_provider(provider="not-a-real-provider")


def test_get_llm_provider_is_cached():
    assert get_llm_provider() is get_llm_provider()


# --- Production guardrail — identical shape to the embedding provider's --------


def test_fake_provider_in_production_app_env_fails_hard(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_PROVIDER", "fake")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "production")
    with pytest.raises(FakeLLMProviderInProductionError, match="NOT a real AI model"):
        build_llm_provider()


def test_fake_provider_in_prod_app_env_also_fails_hard(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_PROVIDER", "fake")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "prod")
    with pytest.raises(FakeLLMProviderInProductionError):
        build_llm_provider()


def test_get_llm_provider_startup_path_also_fails_hard_in_production(monkeypatch):
    get_llm_provider.cache_clear()
    monkeypatch.setattr("app.core.config.settings.LLM_PROVIDER", "fake")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "production")
    try:
        with pytest.raises(FakeLLMProviderInProductionError):
            get_llm_provider()
    finally:
        get_llm_provider.cache_clear()


@pytest.mark.parametrize("app_env", ["development", "test", "testing", "ci", "staging", ""])
def test_fake_provider_is_allowed_outside_production(monkeypatch, app_env):
    monkeypatch.setattr("app.core.config.settings.LLM_PROVIDER", "fake")
    monkeypatch.setattr("app.core.config.settings.APP_ENV", app_env)
    provider = build_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


# --- Real-provider extension point: config-driven, never a hard dependency -----


def test_openai_compatible_provider_refuses_to_construct_without_an_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_API_KEY", None)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        OpenAICompatibleLLMProvider(model_name="gpt-4o-mini")


def test_openai_compatible_provider_stores_the_api_key_only_in_a_private_attribute(monkeypatch):
    """The key must be usable (functionality requires it) but must never
    end up on any of the provider's public identity fields — those are
    exactly what `RAGService` copies into `RAGResponse.model_metadata`,
    which reaches the API response (see app/schemas/rag.py)."""
    monkeypatch.setattr("app.core.config.settings.LLM_API_KEY", "sk-super-secret-value")
    provider = OpenAICompatibleLLMProvider(model_name="gpt-4o-mini")
    assert provider._api_key == "sk-super-secret-value"
    assert "sk-super-secret-value" not in provider.provider_name
    assert "sk-super-secret-value" not in provider.model_name
    assert "sk-super-secret-value" not in (provider.model_version or "")


def test_build_llm_provider_with_openai_compatible_reads_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr("app.core.config.settings.LLM_MODEL_NAME", "gpt-4o-mini")
    provider = build_llm_provider(provider="openai_compatible")
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.model_name == "gpt-4o-mini"
    assert provider.is_external is True
