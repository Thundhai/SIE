# Semantic retrieval evaluation fixtures

Synthetic, non-confidential safety-knowledge corpus and query set used by
the "Prototype retrieval evaluation" harness (`tests/evaluation/`) —
see the milestone spec's own item 19-21 and the README's "Semantic
Knowledge Architecture" section for what this evaluation is and, just as
importantly, is **not**: a real-world benchmark, a claim about
production retrieval accuracy, or anything beyond a regression check
against this one small fixture dataset.

| File          | Contents                                                          |
|----------------|--------------------------------------------------------------------|
| `corpus.py`    | 28 short synthetic chunks across six topics: working at height, lifting operations, permit to work, PPE, confined spaces, emergency response |
| `queries.py`   | 12 natural-language queries (two per topic), each with an `expected_topic` |

Every chunk and query was written fresh for this repository — generic,
textbook-level safety statements, not sourced from or resembling any
real organization's procedures, any specific regulation's exact
wording, or any copyrighted material.

`tests/evaluation/harness.py::seed_evaluation_corpus` loads this data
into the database as one synthetic `KnowledgeSource` /
`KnowledgeDocument` / `KnowledgeDocumentVersion` with 28 `KnowledgeChunk`
rows (each tagged with its topic in `chunk_metadata["eval_topic"]`),
then embeds them — real chunks and real embeddings, going through the
same `KnowledgeChunk`/`KnowledgeChunkEmbedding` tables and
`EmbeddingService` production code path as any other ingested content,
not a separate mock pipeline.
