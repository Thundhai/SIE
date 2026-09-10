# Semantic Embedding & Retrieval

**SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization
v0.1.** Moves SIE's semantic knowledge layer from the deterministic
`HashingEmbeddingProvider` foundation to a real, production-capable
semantic embedding architecture, while preserving the existing
evidence-grounded RAG, provenance, tenant isolation, and retrieval
contracts unchanged — **retrieval itself was not redesigned**; a real
`EmbeddingProvider` implementation was added behind the existing
abstraction, with model/version provenance and safe rollout controls.

## Architecture

```
EmbeddingService / RetrievalService / RAGService   (UNCHANGED contracts)
        |
        v
EmbeddingProvider                                   (app/embeddings/provider.py)
        |
   ┌────┴─────────────────────┐
   |                          |
HashingEmbeddingProvider   SentenceTransformerEmbeddingProvider
(deterministic, test/dev,   (real, production — a genuine
 the default)                sentence-transformers model)
```

`app.core.config.settings.EMBEDDING_PROVIDER` selects which one is
constructed — the same configuration-based-boundary shape
`app/ingestion/storage.py::get_storage_provider()` already uses
elsewhere in this codebase. Nothing above this boundary
(`EmbeddingService`, `RetrievalService`, `RAGService`, every router) ever
imports a concrete provider class directly.

### Provider implementations

- **`HashingEmbeddingProvider`** — deterministic, dependency-free feature
  hashing (the "hashing trick"). Not a trained semantic model; exists
  specifically so tests, CI, and local development never need network
  access or a downloaded model. Remains the default everywhere except a
  real deployment.
- **`SentenceTransformerEmbeddingProvider`** — the real, production
  implementation, wrapping `sentence_transformers.SentenceTransformer`.
  Selected via `EMBEDDING_PROVIDER=sentence_transformers`. See
  "Production deployment" below for exactly how to configure it.

`build_embedding_provider()` **fails closed**
(`HashingProviderInProductionError`) if it would resolve to
`HashingEmbeddingProvider` while `APP_ENV` is `production`/`prod` — a
real deployment cannot silently start serving semantically-meaningless
vectors just because someone forgot to set `EMBEDDING_PROVIDER`.

### Model identity

Every embedding row (`KnowledgeChunkEmbedding` —
`app/models/embedding.py`) carries its full model identity:
`provider`, `model_name`, `model_version`, `dimensions`. Retrieval
(`RetrievalService._model_clause`) always filters by the *exact* triple
of `(provider, model_name, model_version)` — vectors from different
models are never compared in one search, and never silently mixed.
Switching `EMBEDDING_PROVIDER` does not touch, delete, or overwrite a
previously-configured model's existing rows — see "Re-embedding" below.

### Model loading & lifecycle

```
application/process start
        |
        v
get_embedding_provider()        (@lru_cache — built once, reused for
        |                        every request in this process)
        v
SentenceTransformerEmbeddingProvider.__init__()
        |
        v
sentence_transformers.SentenceTransformer(model_name, device, cache_folder)
        |
        v
loaded model, held in memory for the life of the process
        |
        v
embed_texts([...])              (one real batched forward pass per call)
```

The model is loaded **once per process** (via `get_embedding_provider()`'s
`@lru_cache`), never per request, per chunk, or per document — loading a
real transformer model takes real time and memory; doing it once and
reusing it is the whole point of "a reusable model lifecycle" (item 6).
`build_embedding_provider()` (uncached) exists for tests/evaluation code
that deliberately wants an independent, differently-configured instance.

**Clean seam for a future worker.** `get_embedding_provider()` is a plain
function call with no request/response coupling — a future background
worker (explicitly out of this milestone's scope: no Celery, no Redis,
no queue) would call exactly the same function, in its own process, the
same way a request handler does today.

### Batching

`EmbeddingService.embed_chunks_batch()` (SIE Milestone 21) is the real
batching entry point: every chunk that needs embedding is resolved for
eligibility first (already embedded? empty? INSUFFICIENT quality?) purely
from the database, with **no provider call at all** for chunks that don't
need one — then every remaining chunk is sent to the provider in **one**
`embed_texts()` call, letting a real model batch its own forward pass
(`SentenceTransformer.encode(texts, batch_size=...)`) instead of running
one text at a time. `generate_embeddings_for_version()` (unchanged public
contract) is now a thin wrapper around this.

**Failure isolation, not all-or-nothing.** If the one batched
`embed_texts()` call itself raises, the batch is retried one chunk at a
time so a single bad input's failure is reported against *that* chunk
alone — every other chunk still gets embedded and `CREATED`, matching
this service's pre-existing per-chunk resilience contract (see
`tests/test_embedding_service.py::test_batch_embedding_continues_past_a_single_chunk_failure`).

`EmbeddingProvider.embed_texts()` itself preserves input order exactly
(`input[i] -> output[i]`) and validates its own output before returning:
vector count matches input count, every vector's length matches
`self.dimensions` — see `EmbeddingOutputValidationError`.

### Storage & retrieval

Unchanged. `KnowledgeChunkEmbedding` (pgvector `vector(N)` column, `N` =
`settings.EMBEDDING_DIMENSIONS`), `RetrievalService.search()`'s tenant
filter, GLOBAL/ORGANIZATION scope rule, model-identity filter, top-K
limit, minimum-similarity threshold, and provenance fields all work
identically regardless of which `EmbeddingProvider` produced the vectors
being searched — see `tests/test_retrieval_service_real_provider.py` for
the tests proving this directly against a real provider.

### Re-embedding & backfill

`app/embeddings/reembedding_service.py` (SIE Milestone 21) is the
explicit, service-level seam:

```
document
   |
   v
current KnowledgeDocumentVersion
   |
   v
eligible chunks
   |
   v
selected model identity        (an explicit EmbeddingProvider argument —
   |                            never an ambient default)
   v
batch embedding                 (EmbeddingService.embed_chunks_batch)
   |
   v
new embedding rows               (under the given provider's own
                                   (provider, model_name, model_version)
                                   identity — a different identity's rows
                                   are never touched)
```

`ReembeddingService.reembed_document_version()`/
`reembed_document_current_version()` always require the target
`EmbeddingProvider` explicitly — there is no default to
`get_embedding_provider()`'s ambient, settings-driven identity, so a
re-embedding call can never pick a model "by accident." Never
destructive: a re-embed under a *new* model identity always creates new
`KnowledgeChunkEmbedding` rows (the unique constraint scopes rows by
`(chunk, provider, model_name, model_version)`); an old identity's rows
are structurally untouched. Re-embedding under the *same* identity again
is governed by `EmbeddingService`'s existing idempotency rule: unchanged
content is left alone unless `force=True`.

**This is a synchronous, on-demand seam, not a background worker.**
Calling it re-embeds whatever chunks it's given in the calling
request/process and returns a report immediately. A queue-backed bulk
migration/backfill worker is explicitly out of this milestone's scope —
this module is the seam such a worker would call into later.

## Production deployment

### Recommended production model

`sentence-transformers/all-MiniLM-L6-v2`:

| | |
|---|---|
| Model identity | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimension | 384 |
| License | Apache 2.0 |
| Inference | Local (CPU or GPU) — no external API call, no data leaves the deployment |
| Download/cache | Downloaded once from the Hugging Face Hub on first load, then cached on disk (`EMBEDDING_MODEL_CACHE_DIR`, or sentence-transformers' own default cache directory) for every subsequent process start |
| Typical runtime footprint | ~80 MB model weights; CPU inference is fast enough for typical chunk-sized text (a few hundred tokens) at the batch sizes this deployment uses |

This is a well-established, widely-used general-purpose sentence-embedding
model — not a novel or unvetted choice — chosen as the *documented
recommendation*, not hardcoded: `EMBEDDING_MODEL_NAME` is a plain setting,
and any other real `sentence-transformers`-compatible model can be
substituted by changing it (and `EMBEDDING_DIMENSIONS` to match, plus a
migration if the pgvector column needs to widen — see
`EmbeddingDimensionMismatchError`'s own docstring in
`app/embeddings/embedding_service.py`).

### Configuration

See `.env.example`'s own "Semantic embeddings" section for the full list
with inline documentation. Summary:

| Setting | Purpose |
|---|---|
| `EMBEDDING_PROVIDER` | `hashing` (default, test/dev) or `sentence_transformers` (production) |
| `EMBEDDING_MODEL_NAME` | HF Hub model id, or a local filesystem path to an already-saved model |
| `EMBEDDING_MODEL_VERSION` | Free-form version label recorded on every embedding row |
| `EMBEDDING_DIMENSIONS` | Must exactly match the real model's output dimension |
| `EMBEDDING_DEVICE` | `cpu` / `cuda` / `cuda:0` / `mps`; unset auto-detects |
| `EMBEDDING_MODEL_CACHE_DIR` | Where downloaded weights are cached between process starts |
| `EMBEDDING_BATCH_SIZE` | Passed to `SentenceTransformer.encode(batch_size=...)` |
| `EMBEDDING_INFERENCE_TIMEOUT_SECONDS` | Documented, best-effort budget — **not currently enforced by preemption** (see that setting's own docstring in `app/core/config.py` for why a hard timeout on synchronous CPU/GPU inference isn't safely enforceable without process-level isolation, itself out of this milestone's scope) |

### Runtime requirements

- Real inference needs `sentence-transformers` and `torch` installed
  (**not** in `backend/requirements.txt` — see "CI strategy" below for
  why, and install them explicitly in a production image/environment
  alongside the rest of `requirements.txt`).
- CPU inference works for `all-MiniLM-L6-v2` at typical SIE ingestion
  volumes; a GPU (`EMBEDDING_DEVICE=cuda`) is optional, for higher
  throughput at larger ingestion volumes.
- Model weights are downloaded once (a few tens to low hundreds of MB
  depending on the chosen model) and cached on disk — plan for that disk
  space and for the one-time download during first startup/deployment
  (or pre-bake the cache into the deployment image, pointing
  `EMBEDDING_MODEL_CACHE_DIR` at it, so a running instance never needs
  outbound network access to a model hub at all).

### Security considerations

- **Server-side configuration only.** `EMBEDDING_MODEL_NAME`,
  `EMBEDDING_DEVICE`, and `EMBEDDING_MODEL_CACHE_DIR` are read exclusively
  from `app.core.config.settings`. No API request anywhere in this
  codebase can supply a model name or filesystem path — see
  `tests/test_embedding_security.py`'s own docstring for the exact code
  paths checked.
- **No model-file upload path exists.** SIE's ingestion upload endpoints
  only ever accept document content (PDF/DOCX/XLSX/...); there is no
  endpoint that accepts a model artifact, so "model files executable as
  uploaded content" does not apply to this codebase's actual attack
  surface.
- **No secrets involved.** A local/self-hosted `sentence-transformers`
  model needs no API key — unlike `app/llm/provider.py`'s
  `OpenAICompatibleLLMProvider`, there is nothing analogous to
  `LLM_API_KEY` here to accidentally log.
- **Document text is never logged during embedding.** Every log call in
  `app/embeddings/embedding_service.py` includes only `chunk_id`,
  `provider`, `model_name`, `model_version`, and an error
  type/message — never the chunk's own content. Verified directly by
  `tests/test_embedding_security.py`.
- **Tenant boundaries.** `EmbeddingService`/`ReembeddingService` perform
  no authorization themselves (the same "caller resolves and authorizes
  first" shape every other service in this codebase uses) — the caller
  is responsible for having already authorized the `KnowledgeChunk`/
  `KnowledgeDocumentVersion` being embedded. `RetrievalService`'s own
  tenant filter (an explicit SQL predicate on
  `KnowledgeChunkEmbedding.organization_id`, never inferred from vector
  similarity) is unchanged and applies identically regardless of which
  provider produced the vectors being searched.

## Evaluation

**Full details, methodology, and results:**
`docs/SEMANTIC_EVALUATION_REPORT.md`/`.json` (generated by
`tests/evaluation/test_semantic_embedding_evaluation.py`).

### Why a locally-trained model, not the recommended pretrained one

This development/CI environment's outbound network policy blocks
`huggingface.co` (and PyTorch's own CPU-wheel index,
`download.pytorch.org`) — there was no way to download
`sentence-transformers/all-MiniLM-L6-v2` (or any other pretrained
checkpoint) to personally exercise and evaluate it in this session. Two
things follow from that, and they are different claims:

1. **The `SentenceTransformerEmbeddingProvider` class itself is real,
   complete, and tested** — real batching, real dimension/output
   validation, real fail-closed error handling on load/inference
   failure — verified against a real (if small) `sentence-transformers`
   model in `tests/test_sentence_transformer_provider.py`.
2. **The recommended production pretrained model's actual semantic
   quality was not personally measured in this session.** Nothing in
   this codebase claims otherwise.

To still produce a genuine, honest "hashing vs. real semantic embedding"
comparison (item 11 of this milestone), `scripts/train_local_semantic_model.py`
trains a small sentence-embedding model **from scratch, entirely
offline** — a real `WordEmbeddings -> LSTM -> Pooling` `sentence_transformers`
model, trained via real backpropagation
(`MultipleNegativesRankingLoss`, AdamW) on
`tests/fixtures/evaluation/semantic_training_pairs.py` (36 synthetic
paraphrase pairs). This is genuinely real — a trained neural network, not
hashing, not TF-IDF, not a handcrafted score — but it is small and
narrowly trained, and evaluating it is **not** a substitute for
evaluating the actual recommended production model. Any real deployment
should download and independently evaluate its actual chosen pretrained
model before relying on it in production.

### Dataset

- Corpus: `tests/fixtures/evaluation/corpus.py` — 28 synthetic,
  non-confidential safety-domain chunks across 6 topics (working at
  height, lifting operations, permit to work, PPE, confined spaces,
  emergency response).
- Query sets:
  - `tests/fixtures/evaluation/queries.py` — the existing, lighter
    paraphrase set.
  - `tests/fixtures/evaluation/hard_paraphrase_queries.py` (SIE
    Milestone 21) — deliberately keyword-disjoint paraphrases, written
    to avoid literal vocabulary overlap with their correct chunk, so a
    purely lexical method has little to work with.
- Training data for the local model:
  `tests/fixtures/evaluation/semantic_training_pairs.py` — 36 paraphrase
  pairs, **disjoint** from both evaluation query sets (training on the
  evaluation set would make any measured recall memorization, not
  generalization).

### Methodology

Recall@1/3/5: per-query binary hit/miss (did any chunk from the query's
expected topic appear in the top-K results), averaged over all queries —
computed through the real, unmodified `RetrievalService.search()`. The
corpus is seeded once per provider (each provider embeds its own
independent copy, isolated by the existing model-identity filter), so
results are directly comparable without one provider's embeddings ever
being searched under another's identity.

### Results

See `docs/SEMANTIC_EVALUATION_REPORT.md` for the exact numbers from the
most recent run (regenerate by running
`scripts/train_local_semantic_model.py` then
`pytest tests/evaluation/test_semantic_embedding_evaluation.py`). Headline
finding, reported honestly: the hashing baseline does *better* on the
lighter query set (where genuine keyword overlap exists — exactly what a
bag-of-words method is designed to exploit) and *worse* on the
deliberately keyword-disjoint hard set, where the small trained model
holds up better. Neither number should be read as more than what it is —
a small-fixture, small-model comparison.

### Limitations

- The evaluation corpus and query sets are small (28 chunks, 12 queries
  per set) and synthetic — not statistically robust, not representative
  of real enterprise content or query distributions.
- The real model evaluated is a small, narrowly-trained demonstration
  model, not the recommended production pretrained checkpoint.
- No threshold anywhere in this evaluation was tuned or manufactured to
  make either provider look better.
- This is not a production accuracy benchmark and must not be presented
  as one.

## CI strategy

`sentence-transformers`/`torch` are **not** in `backend/requirements.txt`.
`torch`'s default PyPI wheel bundles a full CUDA runtime (500+ MB) with
no CPU-only build reachable from this environment's (or a similarly
locked-down CI's) allowed package sources — making it a hard requirement
would mean every CI run, even ones that never touch embeddings,
downloads 500+ MB. That is exactly what this milestone's own CI guidance
warns against.

So the split is explicit:

- **CI deterministic regression** — `backend/requirements.txt` installed
  as-is (unchanged by this milestone), `EMBEDDING_PROVIDER` stays
  `hashing` (the default), and the full test suite runs, including every
  hashing-provider retrieval/RAG/evaluation test. Real-provider tests
  (`tests/test_sentence_transformer_provider.py`,
  `tests/test_retrieval_service_real_provider.py`,
  `tests/test_rag_service_real_provider.py`) self-skip cleanly (never
  fail, never report as passed) via
  `tests/sentence_transformers_support.py`'s `requires_sentence_transformers`
  marker — the identical shape `tests/postgres_support.py`'s
  `requires_postgres` already uses for the identical reason. The
  semantic-evaluation report-writing test always runs (it only needs
  PostgreSQL, which CI already provisions) but honestly records
  `real_provider_available: false` and reports only the hashing half
  when the real model isn't present — never a fabricated real-model
  result.
- **Separate real-model validation** — performed locally, on demand:
  install `sentence-transformers`/`torch`, run
  `scripts/train_local_semantic_model.py`, then run the same test suite
  again — every one of the tests above now actually executes for real.
  This is what was done to produce `docs/SEMANTIC_EVALUATION_REPORT.md`
  and the completion report's own real-model results.

No `.github/workflows/ci.yml` change was needed for this milestone — the
existing `pip install -r requirements.txt` / `python -m pytest -q` /
`alembic check` steps are completely unchanged.
