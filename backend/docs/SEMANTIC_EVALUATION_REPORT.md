# SIE Semantic Embedding Evaluation Report

**SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization v0.1.**

Generated 2026-09-03T15:25:09.976477+00:00 by `tests/evaluation/test_semantic_embedding_evaluation.py` against a real PostgreSQL 16 + pgvector database.

## What this is, and is not

- **Hashing baseline:** Prototype deterministic baseline (HashingEmbeddingProvider) — feature hashing / bag-of-words, not a trained semantic model.
- **Real semantic embedding:** Real semantic embedding performance — a small, genuinely backprop-trained local sentence-embedding model (scripts/train_local_semantic_model.py), evaluated because this environment cannot download the recommended production pretrained model. NOT a claim about that production model's quality — see docs/SEMANTIC_EMBEDDING.md.

This is a small, synthetic-fixture evaluation (28 corpus chunks across 6 safety topics) — a regression/sanity check and an honest, real comparison between the two provider implementations this codebase actually ships, **not** a production accuracy benchmark, and **not** a claim about the recommended production pretrained model's quality (this environment could not download it — see docs/SEMANTIC_EMBEDDING.md).

**Real-model validation performed in this run:** yes
**Real model:** `/home/user/SIE/backend/var/local_semantic_model` (256 dimensions)

## Results

### existing_paraphrase_queries

- Hashing: Recall@1=0.83, Recall@3=1.00, Recall@5=1.00 (n=12 queries)
- Real:    Recall@1=0.67, Recall@3=0.83, Recall@5=0.92 (n=12 queries)

### hard_keyword_disjoint_paraphrase_queries

- Hashing: Recall@1=0.33, Recall@3=0.75, Recall@5=0.75 (n=12 queries)
- Real:    Recall@1=0.33, Recall@3=0.83, Recall@5=0.92 (n=12 queries)

## Performance benchmark

Baseline only — not a production SLA. One `embed_texts()` call over the 28-chunk corpus, timed end to end.

| Provider | Model | Texts | Batch size | Dimensions | Total (s) | Avg latency (ms) | Throughput (texts/s) |
|---|---|---|---|---|---|---|---|
| hashing | sie-hashing-embedder | 28 | 28 | 256 | 0.0011 | 0.038 | 26176.15 |
| sentence_transformers | /home/user/SIE/backend/var/local_semantic_model | 28 | 32 | 256 | 0.0115 | 0.412 | 2429.74 |

## Methodology

- Corpus: `tests/fixtures/evaluation/corpus.py` — 28 synthetic, non-confidential safety-domain chunks across 6 topics, seeded once per provider (each provider embeds its own independent copy of the corpus, isolated by the existing model-identity filter — see `app/retrieval/retrieval_service.py::_model_clause`).
- Query sets:
  - `existing_paraphrase_queries` — `tests/fixtures/evaluation/queries.py`, 12 queries.
  - `hard_keyword_disjoint_paraphrase_queries` — `tests/fixtures/evaluation/hard_paraphrase_queries.py`, 12 queries deliberately written to avoid literal keyword overlap with their correct chunk, per this milestone's own instruction to avoid evaluation cases retrievable by lexical shortcut alone.
- Metric: Recall@K (K=1,3,5) — per-query binary hit/miss (did any chunk from the query's expected topic appear in the top-K results), averaged over all queries in the set. Computed via the real, unmodified `RetrievalService.search()` — see `tests/evaluation/harness.py`.
- Real model: a small, locally-trained (not downloaded) `sentence-transformers`-format model — `scripts/train_local_semantic_model.py` — trained on `tests/fixtures/evaluation/semantic_training_pairs.py` (36 synthetic paraphrase pairs), a **disjoint** set from both evaluation query sets above.

## Limitations

- The evaluation corpus and query sets are small and synthetic — results here are not statistically robust and must not be extrapolated to real enterprise content, a different domain, or a different query distribution.
- The real model evaluated here is a small, narrowly-trained demonstration model, not the recommended production pretrained checkpoint — see docs/SEMANTIC_EMBEDDING.md's "Evaluation methodology" section for why, and what a real deployment should expect to do differently (download and evaluate an actual pretrained sentence-transformers model before relying on this provider in production).
- No threshold in this report has been tuned or manufactured to make either provider look better; both are reported as measured.

