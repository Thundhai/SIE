"""Hashing-vs-real semantic embedding evaluation harness — SIE Milestone
21: Real Semantic Embedding & Retrieval Productionization v0.1, item 11.

Reuses `tests/evaluation/harness.py`'s existing, unmodified
`seed_evaluation_corpus()`/`run_recall_at_k()` — the exact same
production `EmbeddingService`/`RetrievalService` code path every other
chunk in this codebase goes through — against **two** embedding
providers over the **same** synthetic corpus:

  * `HashingEmbeddingProvider` — the deterministic, dependency-free
    feature-hashing baseline (see `app/embeddings/provider.py`'s own
    docstring for exactly what it is and is not).
  * A small, genuinely backprop-trained local sentence-embedding model
    (see `scripts/train_local_semantic_model.py`) — real, but small and
    narrowly trained; **not** a stand-in for, or claim about, the
    recommended production pretrained model
    (`sentence-transformers/all-MiniLM-L6-v2` or similar) — see
    `docs/SEMANTIC_EMBEDDING.md`'s "Evaluation methodology" section for
    the full, honest explanation of why this substitution was necessary
    in this sandboxed, network-restricted environment, and exactly what
    it does and does not demonstrate.

Two query sets are evaluated against each provider:

  * `tests/fixtures/evaluation/queries.py` (`QUERIES`) — the existing,
    lighter paraphrase set (already used by
    `tests/evaluation/test_recall_at_k.py`'s own regression test).
  * `tests/fixtures/evaluation/hard_paraphrase_queries.py`
    (`HARD_PARAPHRASE_QUERIES`) — deliberately keyword-disjoint
    paraphrases (item 11: "avoid evaluation cases where the answer can be
    retrieved simply because the same keywords appear").

The corpus is seeded **twice** in one session — once per provider,
producing two independent copies of the same 28 synthetic chunks, each
embedded under its own provider's model identity. `RetrievalService`'s
own existing model-identity filtering (`_model_clause` —
`app/retrieval/retrieval_service.py`) then means a search under one
provider's identity only ever matches that provider's own copy: real,
unmodified model-identity isolation, not a special evaluation-only code
path.

**Not a production benchmark.** See `RESULT_LABEL_HASHING`/
`RESULT_LABEL_REAL` below — these exact strings are what every
consumer of this harness's results (the report, the completion report)
must use, never a vaguer "real vs. baseline" framing that could be
misread as a production accuracy claim.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.embeddings.provider import EmbeddingProvider, HashingEmbeddingProvider
from tests.evaluation.harness import RecallReport, run_recall_at_k, seed_evaluation_corpus
from tests.fixtures.evaluation.hard_paraphrase_queries import HARD_PARAPHRASE_QUERIES
from tests.fixtures.evaluation.queries import EvaluationQuery, QUERIES

LOCAL_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "local_semantic_model"
LOCAL_MODEL_VERSION = "local-scratch-v1"

RESULT_LABEL_HASHING = (
    "Prototype deterministic baseline (HashingEmbeddingProvider) — feature "
    "hashing / bag-of-words, not a trained semantic model."
)
RESULT_LABEL_REAL = (
    "Real semantic embedding performance — a small, genuinely "
    "backprop-trained local sentence-embedding model "
    "(scripts/train_local_semantic_model.py), evaluated because this "
    "environment cannot download the recommended production pretrained "
    "model. NOT a claim about that production model's quality — see "
    "docs/SEMANTIC_EMBEDDING.md."
)


def real_local_provider_available() -> bool:
    """False (never raises) when the optional `sentence-transformers`
    dependency isn't installed, or when
    `scripts/train_local_semantic_model.py` hasn't been run yet in this
    checkout — the local model directory is deliberately untracked by Git
    (see `backend/.gitignore`'s `/var/` rule), so a fresh checkout (and
    every CI run) genuinely does not have it. Callers use this to skip,
    not fail — see `tests/evaluation/test_semantic_embedding_evaluation.py`."""
    if not LOCAL_MODEL_DIR.is_dir():
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def build_real_local_provider() -> EmbeddingProvider:
    from app.embeddings.provider import SentenceTransformerEmbeddingProvider

    return SentenceTransformerEmbeddingProvider(
        model_name=str(LOCAL_MODEL_DIR), model_version=LOCAL_MODEL_VERSION
    )


@dataclass
class PerformanceBenchmark:
    """Item 16's own required fields, exactly — a controlled-fixture
    baseline, never presented as a production SLA (see this module's own
    docstring and the report this feeds)."""

    provider_name: str
    model_name: str
    num_texts: int
    batch_size: int
    dimensions: int
    total_seconds: float
    avg_latency_ms: float
    throughput_texts_per_second: float


def run_performance_benchmark(provider: EmbeddingProvider, texts: list[str]) -> PerformanceBenchmark:
    """One real `embed_texts()` call over `texts` (the same controlled
    fixture used for the evaluation corpus — see `run_semantic_evaluation`),
    timed end to end. Not a warmed-up/averaged-over-many-runs microbenchmark
    — a single, honestly-labeled measurement, matching item 16's "this is a
    baseline, not a production SLA" instruction."""
    batch_size = getattr(provider, "_batch_size", len(texts)) or len(texts)
    started = time.monotonic()
    provider.embed_texts(texts)
    elapsed = time.monotonic() - started
    count = len(texts)
    return PerformanceBenchmark(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        num_texts=count,
        batch_size=batch_size,
        dimensions=provider.dimensions,
        total_seconds=round(elapsed, 4),
        avg_latency_ms=round((elapsed / count) * 1000, 3) if count else 0.0,
        throughput_texts_per_second=round(count / elapsed, 2) if elapsed > 0 else 0.0,
    )


@dataclass
class QuerySetResult:
    query_set_name: str
    hashing: RecallReport
    real: RecallReport | None
    real_label: str = RESULT_LABEL_REAL
    hashing_label: str = RESULT_LABEL_HASHING


@dataclass
class SemanticEvaluationReport:
    results: list[QuerySetResult] = field(default_factory=list)
    real_provider_available: bool = False
    real_provider_model_name: str | None = None
    real_provider_dimensions: int | None = None
    hashing_seed_seconds: float = 0.0
    real_seed_seconds: float | None = None
    benchmarks: list[PerformanceBenchmark] = field(default_factory=list)


def run_semantic_evaluation(db: Session) -> SemanticEvaluationReport:
    """Runs the full hashing-vs-real comparison described in this
    module's own docstring, over both query sets, and returns a
    structured report. Always runs the hashing side (it has no external
    dependency); runs the real side only when
    `real_local_provider_available()` is true — the caller decides
    whether that absence should be a test failure (never in CI, where
    the local model directory won't exist) or is fine to simply record
    (see the pytest wrapper for exactly which)."""
    from tests.fixtures.evaluation.corpus import CORPUS

    benchmark_texts = [entry.text for entry in CORPUS]

    hashing_provider = HashingEmbeddingProvider(model_name="sie-hashing-embedder", model_version="v1", dimensions=256)

    hashing_seed_start = time.monotonic()
    seed_evaluation_corpus(db, provider=hashing_provider)
    hashing_seed_seconds = round(time.monotonic() - hashing_seed_start, 3)

    report = SemanticEvaluationReport(hashing_seed_seconds=hashing_seed_seconds)
    report.benchmarks.append(run_performance_benchmark(hashing_provider, benchmark_texts))

    real_provider: EmbeddingProvider | None = None
    if real_local_provider_available():
        real_provider = build_real_local_provider()
        report.real_provider_available = True
        report.real_provider_model_name = real_provider.model_name
        report.real_provider_dimensions = real_provider.dimensions
        report.benchmarks.append(run_performance_benchmark(real_provider, benchmark_texts))

        real_seed_start = time.monotonic()
        seed_evaluation_corpus(db, provider=real_provider)
        report.real_seed_seconds = round(time.monotonic() - real_seed_start, 3)

    query_sets: list[tuple[str, list[EvaluationQuery]]] = [
        ("existing_paraphrase_queries", QUERIES),
        ("hard_keyword_disjoint_paraphrase_queries", HARD_PARAPHRASE_QUERIES),
    ]

    for name, queries in query_sets:
        hashing_recall = run_recall_at_k(db, provider=hashing_provider, queries=queries)
        real_recall = (
            run_recall_at_k(db, provider=real_provider, queries=queries)
            if real_provider is not None
            else None
        )
        report.results.append(
            QuerySetResult(query_set_name=name, hashing=hashing_recall, real=real_recall)
        )

    return report
