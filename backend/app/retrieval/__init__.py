"""Semantic retrieval — metadata-filtered vector similarity search over
`KnowledgeChunkEmbedding`.

    TenantContext -> Authorization -> Allowed knowledge scope
        -> RetrievalService -> Metadata filter -> Vector similarity
        -> Ranked RetrievalResult -> Provenance

This package returns **evidence, not answers**. Nothing here calls an
LLM, assembles a prompt, or generates prose — see
app/retrieval/retrieval_service.py's own docstring, and the README's
"Semantic Knowledge Architecture" section, for the explicit statement
that RAG/LLM reasoning is not implemented anywhere in this codebase yet.
"""
