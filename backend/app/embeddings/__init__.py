"""Semantic embeddings — turning a KnowledgeChunk's text into a vector.

    KnowledgeChunk -> EmbeddingService -> EmbeddingProvider -> Vector
        -> KnowledgeChunkEmbedding (pgvector storage)

See app/embeddings/provider.py for the provider abstraction and
app/embeddings/embedding_service.py for the generation/storage service.
Nothing in this package is aware of retrieval, ranking, or an LLM — see
app/retrieval/ for the layer built on top of this one.
"""
