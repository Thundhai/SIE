"""RAG evaluation harness test — milestone item 31. PostgreSQL-integration
test (see tests/postgres_support.py); skipped automatically when no real
server is reachable. See tests/evaluation/rag_harness.py's own docstring
for what this is and is not: a small, synthetic, regression-catching
check, never a production/enterprise accuracy claim.
"""

from app.llm.provider import FakeLLMProvider
from tests.evaluation.rag_harness import run_rag_evaluation, seed_rag_evaluation_fixtures
from tests.postgres_support import requires_postgres


@requires_postgres
def test_rag_evaluation_runs_and_reports_separate_metrics_per_dimension(pg_session):
    seed_rag_evaluation_fixtures(pg_session)
    report = run_rag_evaluation(pg_session, llm_provider=FakeLLMProvider())

    print(report.summary())  # surfaced in `pytest -s` output / CI logs, not fabricated

    assert report.question_count > 0

    # Injection resistance: the system prompt must never leak, on any
    # injection-category question (milestone item 35).
    assert report.injection_resistance_rate == 1.0

    # Conflict detection: the milestone's own worked example, seeded
    # deterministically -- must be caught every time.
    assert report.conflict_detection_rate == 1.0

    # Abstention correctness: genuinely unanswerable questions should
    # abstain. Not asserted at a perfect 1.0: `HashingEmbeddingProvider`
    # is a bag-of-words/feature-hashing embedding, not a trained semantic
    # model (see the README) -- an unrelated query can occasionally still
    # hash into overlapping buckets with unrelated corpus vocabulary and
    # cross the relevance bar, exactly the same honest limitation the
    # README's "Semantic Knowledge Architecture" section already
    # documents. A real LLM-quality embedding model would be expected to
    # score much closer to 1.0 here; this number honestly reflects the
    # provider actually exercised in this environment.
    assert report.abstention_correctness is not None
    assert report.abstention_correctness >= 0.6

    # Citation validity: FakeLLMProvider's default grounded-answer
    # behavior never cites an id it wasn't given -- this must be perfect.
    assert report.citation_validity_rate == 1.0

    # Unsupported-claim rate: the default deterministic provider always
    # cites the evidence it was given when evidence exists, so this
    # should be zero -- tracked as a metric, not asserted away.
    assert report.unsupported_claim_rate == 0.0

    # Tenant leakage: every fixture in this evaluation corpus is GLOBAL;
    # zero organization-scoped citations should ever appear.
    assert report.tenant_leakage_count == 0

    # Answerable-question grounding: a real, computed rate -- not
    # asserted at 1.0 (HashingEmbeddingProvider is not a trained
    # semantic model; some individual queries may not clear the
    # sufficiency bar), but must be meaningfully above chance.
    assert report.answerable_grounding_rate is not None
    assert report.answerable_grounding_rate >= 0.7

    # Partial-question handling: every question in this category must
    # produce *some* explicit, safe outcome (never silently fabricated).
    assert report.partial_evidence_rate == 1.0
