"""Milestone spec items 19-21, 26-27: the synthetic evaluation corpus,
Recall@K calculation, and the explicit "do not fabricate performance"
requirement.

PostgreSQL-integration test — see tests/postgres_support.py. Skipped
automatically if no real PostgreSQL + pgvector server is reachable.
"""

from tests.evaluation.harness import run_recall_at_k, seed_evaluation_corpus
from tests.fixtures.evaluation.queries import QUERIES
from tests.postgres_support import requires_postgres


@requires_postgres
def test_evaluation_corpus_seeds_successfully(pg_session):
    seed_evaluation_corpus(pg_session)

    from app.models.knowledge_chunk import KnowledgeChunk

    count = pg_session.query(KnowledgeChunk).count()
    from tests.fixtures.evaluation.corpus import CORPUS

    assert count == len(CORPUS)


@requires_postgres
def test_recall_at_k_on_synthetic_fixture(pg_session, capsys):
    """Calculates real Recall@1/3/5 on the synthetic corpus — this is a
    regression check, not a production accuracy claim (see
    tests/evaluation/harness.py::LABEL). The bar asserted here is
    deliberately loose: it exists to catch retrieval breaking outright
    (e.g. a query never finding its own topic at all), not to pin an
    exact score to this particular deterministic hashing provider.
    """
    seed_evaluation_corpus(pg_session)

    report = run_recall_at_k(pg_session, ks=[1, 3, 5])

    print(f"\n{report.summary()}")
    for row in report.per_query:
        print(f"  [{row['first_hit_rank'] or 'MISS'}] {row['expected_topic']:<20} {row['query']}")

    assert report.recall_at_k[5] >= 0.5, (
        "Recall@5 dropped below the regression floor on the synthetic "
        f"evaluation fixture: {report.summary()}"
    )
    # Recall@K is monotonically non-decreasing in K by construction.
    assert report.recall_at_k[1] <= report.recall_at_k[3] <= report.recall_at_k[5]
    assert len(report.per_query) == len(QUERIES)
