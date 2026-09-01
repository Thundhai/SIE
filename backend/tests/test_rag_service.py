"""RAGService orchestration — milestone item 4 and the deterministic
gates described in that module's own docstring.

`RetrievalService.search()` itself is stubbed (monkeypatched) here, the
same "SQLite cannot run the real pgvector query" reasoning
`tests/test_retrieval_api.py` already documents — these tests are about
`RAGService`'s own orchestration logic, not about pgvector. The genuine
end-to-end path (a real search actually executing, through the full HTTP
API) is covered by the PostgreSQL-integration tests in tests/test_rag_api.py.
"""

import uuid

import pytest

from app.llm.provider import FakeLLMProvider
from app.models.audit_log import AuditLog
from app.rag.rag_service import RAGService
from app.rag.results import EvidenceState, RAGOutcome
from app.retrieval.results import RelevanceLevel, RetrievalOutcome, RetrievalResponse
from tests.rag_test_helpers import make_retrieval_result
from tests.test_ingestion_api import make_user


def stub_search(*, results=None, outcome=None):
    results = results or []
    outcome = outcome or (RetrievalOutcome.RESULTS if results else RetrievalOutcome.NO_RELEVANT_EVIDENCE)

    def _search(db, *, query_text, allowed_organization_id, filters=None, top_k=None, min_similarity=None, provider=None):
        return RetrievalResponse(
            query=query_text,
            outcome=outcome,
            embedding_provider="hashing",
            embedding_model="sie-hashing-embedder",
            embedding_model_version="v1",
            results=results,
            result_count=len(results),
            filters_applied={"scope": "GLOBAL"},
            search_metadata={"duration_ms": 1.0},
        )

    return _search


@pytest.fixture
def rag_service_instance():
    return RAGService()


@pytest.fixture
def a_user(db_session):
    return make_user(db_session, "rag-user@example.com")


# --- Insufficient evidence: the LLM is never even called -----------------------


def test_zero_evidence_produces_insufficient_evidence_without_calling_the_llm(
    monkeypatch, db_session, rag_service_instance, a_user
):
    monkeypatch.setattr(
        "app.rag.rag_service.retrieval_service.search", stub_search(results=[])
    )
    llm = FakeLLMProvider(canned_response="A confident hallucinated answer from general knowledge.")

    response = rag_service_instance.query(
        db_session,
        query_text="What is the capital of France?",
        allowed_organization_id=None,
        user_id=a_user.id,
        llm_provider=llm,
    )

    assert response.outcome == RAGOutcome.INSUFFICIENT_EVIDENCE
    assert response.evidence_state == EvidenceState.INSUFFICIENT
    assert response.answer is None
    assert response.abstention_reason is not None
    # The core guarantee (milestone item 32): a provider configured to
    # hallucinate confidently never gets the chance to.
    assert llm.calls == []


def test_only_low_relevance_evidence_is_also_insufficient(monkeypatch, db_session, rag_service_instance, a_user):
    weak = make_retrieval_result(relevance=RelevanceLevel.LOW)
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=[weak]))
    llm = FakeLLMProvider()

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.INSUFFICIENT_EVIDENCE
    assert llm.calls == []


# --- Answered, with real grounding and citations --------------------------------


def test_sufficient_evidence_produces_an_answered_response_with_citations(
    monkeypatch, db_session, rag_service_instance, a_user
):
    strong = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH, similarity=0.9),
        make_retrieval_result(relevance=RelevanceLevel.HIGH, similarity=0.85),
    ]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider()  # default grounded behavior

    response = rag_service_instance.query(
        db_session,
        query_text="What fall protection is required?",
        allowed_organization_id=None,
        user_id=a_user.id,
        llm_provider=llm,
    )

    assert response.outcome == RAGOutcome.ANSWERED
    assert response.evidence_state == EvidenceState.SUFFICIENT
    assert response.answer is not None
    assert len(response.citations) >= 1
    assert response.citations[0].citation_id == "E1"
    assert len(llm.calls) == 1


def test_partial_evidence_is_answered_but_flagged(monkeypatch, db_session, rag_service_instance, a_user):
    partial = [make_retrieval_result(relevance=RelevanceLevel.MODERATE)]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=partial))
    llm = FakeLLMProvider()

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.ANSWERED
    assert response.evidence_state == EvidenceState.PARTIAL
    assert any(w.startswith("PARTIAL_EVIDENCE") for w in response.warnings)


# --- Citation validation end to end ----------------------------------------------


def test_invalid_citation_from_the_model_is_stripped_and_flagged(
    monkeypatch, db_session, rag_service_instance, a_user
):
    strong = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH),
        make_retrieval_result(relevance=RelevanceLevel.HIGH),
    ]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider(canned_response="This is supported. [E1] This is not. [E999]")

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.ANSWERED
    assert "[E999]" not in response.answer
    assert "[E1]" in response.answer
    assert {c.citation_id for c in response.citations} == {"E1"}
    assert any("INVALID_CITATION_REMOVED" in w and "E999" in w for w in response.warnings)


def test_answer_citing_no_evidence_at_all_is_rejected_not_returned(
    monkeypatch, db_session, rag_service_instance, a_user
):
    """Milestone item 32, the general form: even when evidence *was*
    supplied to the model, an answer that cites none of it is treated as
    untrustworthy and withheld."""
    strong = [make_retrieval_result(relevance=RelevanceLevel.HIGH), make_retrieval_result(relevance=RelevanceLevel.HIGH)]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider(canned_response="Hard hats are always required by federal law.")

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.UNSUPPORTED_CLAIM_REJECTED
    assert response.answer is None
    assert response.citations == []
    assert any("UNSUPPORTED_CLAIM_REJECTED" in w for w in response.warnings)


# --- Source conflict: the LLM never adjudicates ----------------------------------


def test_conflicting_evidence_produces_source_conflict_without_calling_the_llm(
    monkeypatch, db_session, rag_service_instance, a_user
):
    conflicting = [
        make_retrieval_result(
            relevance=RelevanceLevel.HIGH, content="Hard hats are required.", source_name="Source A"
        ),
        make_retrieval_result(
            relevance=RelevanceLevel.HIGH, content="Hard hats are not required.", source_name="Source B"
        ),
    ]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=conflicting))
    llm = FakeLLMProvider(canned_response="Hard hats are required. [E1]")

    response = rag_service_instance.query(
        db_session, query_text="Are hard hats required?", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.SOURCE_CONFLICT
    assert len(response.conflicts) == 1
    assert "Source A" in response.answer
    assert "Source B" in response.answer
    assert llm.calls == []  # the model never adjudicates the conflict


# --- Provider failure: no fabricated content, evidence stays intact ------------


def test_provider_failure_returns_a_structured_failure_not_fabricated_content(
    monkeypatch, db_session, rag_service_instance, a_user
):
    strong = [make_retrieval_result(relevance=RelevanceLevel.HIGH), make_retrieval_result(relevance=RelevanceLevel.HIGH)]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider(fail=True, fail_message="simulated provider outage")

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.PROVIDER_FAILURE
    assert response.answer is None
    assert response.evidence_state == EvidenceState.SUFFICIENT  # evidence itself was fine
    assert response.evidence_count == 2  # evidence is not lost
    assert response.reproducibility["evidence"]  # reproducibility metadata survives
    assert any("PROVIDER_FAILURE" in w for w in response.warnings)


# --- Privacy boundary (milestone item 39) ---------------------------------------


class _ExternalStubProvider:
    provider_name = "external_stub"
    model_name = "external-model"
    model_version = "1"
    is_external = True

    def __init__(self):
        self.called = False

    def generate(self, request):  # pragma: no cover - must never be called in these tests
        self.called = True
        raise AssertionError("privacy-blocked provider must never be invoked")


def test_external_provider_is_blocked_from_private_organization_evidence_by_default(
    monkeypatch, db_session, rag_service_instance, a_user
):
    org_id = uuid.uuid4()
    private_evidence = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="ORGANIZATION", organization_id=org_id),
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="ORGANIZATION", organization_id=org_id),
    ]
    monkeypatch.setattr(
        "app.rag.rag_service.retrieval_service.search", stub_search(results=private_evidence)
    )
    monkeypatch.setattr("app.core.config.settings.ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA", False)
    provider = _ExternalStubProvider()

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=org_id, user_id=a_user.id, llm_provider=provider
    )

    assert response.outcome == RAGOutcome.PRIVACY_BLOCKED
    assert provider.called is False
    assert response.answer is None


def test_external_provider_is_allowed_when_explicitly_enabled(
    monkeypatch, db_session, rag_service_instance, a_user
):
    org_id = uuid.uuid4()
    private_evidence = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="ORGANIZATION", organization_id=org_id),
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="ORGANIZATION", organization_id=org_id),
    ]
    monkeypatch.setattr(
        "app.rag.rag_service.retrieval_service.search", stub_search(results=private_evidence)
    )
    monkeypatch.setattr("app.core.config.settings.ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA", True)
    llm = FakeLLMProvider()

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=org_id, user_id=a_user.id, llm_provider=llm
    )

    assert response.outcome == RAGOutcome.ANSWERED


def test_global_only_evidence_is_never_privacy_blocked(monkeypatch, db_session, rag_service_instance, a_user):
    global_evidence = [
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="GLOBAL", organization_id=None),
        make_retrieval_result(relevance=RelevanceLevel.HIGH, scope="GLOBAL", organization_id=None),
    ]
    monkeypatch.setattr(
        "app.rag.rag_service.retrieval_service.search", stub_search(results=global_evidence)
    )
    monkeypatch.setattr("app.core.config.settings.ALLOW_EXTERNAL_LLM_FOR_PRIVATE_DATA", False)
    provider = _ExternalStubProvider()
    llm_that_answers = FakeLLMProvider()
    # Swap in a working generate() so this provider can actually answer
    # once we've confirmed it's external but there's no private data.
    provider.generate = llm_that_answers.generate

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=provider
    )

    assert response.outcome == RAGOutcome.ANSWERED


# --- Audit / reproducibility -----------------------------------------------------


def test_a_rag_query_writes_one_audit_log_entry_without_the_raw_query_by_default(
    monkeypatch, db_session, rag_service_instance, a_user
):
    monkeypatch.setattr("app.core.config.settings.LOG_RAG_QUERY_TEXT", False)
    strong = [make_retrieval_result(relevance=RelevanceLevel.HIGH), make_retrieval_result(relevance=RelevanceLevel.HIGH)]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider()

    rag_service_instance.query(
        db_session,
        query_text="a sensitive operational query",
        allowed_organization_id=None,
        user_id=a_user.id,
        llm_provider=llm,
    )

    entries = db_session.query(AuditLog).filter(AuditLog.action == "RAG_QUERY_EXECUTED").all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.user_id == a_user.id
    assert entry.event_metadata["outcome"] == "ANSWERED"
    assert entry.event_metadata["query_text"] is None
    assert entry.event_metadata["query_length"] == len("a sensitive operational query")


def test_reproducibility_metadata_includes_chunk_ids_and_prompt_version(
    monkeypatch, db_session, rag_service_instance, a_user
):
    strong = [make_retrieval_result(relevance=RelevanceLevel.HIGH), make_retrieval_result(relevance=RelevanceLevel.HIGH)]
    monkeypatch.setattr("app.rag.rag_service.retrieval_service.search", stub_search(results=strong))
    llm = FakeLLMProvider()

    response = rag_service_instance.query(
        db_session, query_text="q", allowed_organization_id=None, user_id=a_user.id, llm_provider=llm
    )

    assert response.prompt_version == "v1"
    assert len(response.reproducibility["evidence"]) == 2
    assert all("chunk_id" in e and "similarity" in e for e in response.reproducibility["evidence"])
