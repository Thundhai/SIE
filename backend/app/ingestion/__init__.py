"""Universal Knowledge & Data Ingestion Engine.

Turns an uploaded file into KnowledgeDocument / KnowledgeDocumentVersion /
KnowledgeChunk rows (see app/services/knowledge_*) while preserving
source, ownership, tenant isolation, document/version identity, the
method used to extract content, structure, provenance, and — where
extraction is incomplete or uncertain — that uncertainty itself, rather
than silently pretending it succeeded.

This package is intentionally organized around one core idea: different
input formats are interpreted differently, not flattened into plain
text. A `DocumentAdapter` (adapters/base.py) per format is responsible for
turning its own raw bytes into the common `NormalizedContent`
representation (normalized_content.py) — the *common* part is the
representation extraction lands in, not the extraction itself.

Modules:
    normalized_content.py   The common representation every adapter produces.
    adapters/                One adapter class per format, plus the registry
                              that picks one by detected media type.
    detection.py             File/media-type detection (magic bytes + extension).
    hashing.py               SHA-256 content hashing.
    storage.py                StorageProvider interface + local filesystem impl.
    chunking.py              ChunkingStrategy interface + a simple default.
    ocr.py                   OCRProvider interface (no implementation yet).
    pipeline.py              Orchestrates the stages above into one call.

See the README's "Universal ingestion architecture" section for the full
picture, including what this milestone deliberately does not implement
(embeddings, semantic chunking, OCR execution, background workers,
production object storage).
"""
