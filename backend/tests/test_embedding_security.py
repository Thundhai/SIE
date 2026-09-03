"""SIE Milestone 21: Real Semantic Embedding & Retrieval Productionization
v0.1, item 15 — security checks specific to the real embedding provider
and the batching this milestone adds.

Checks not covered here because they are already true by construction,
verified by direct code inspection rather than a runtime test:

  * **Model configuration is server-side; no API request can supply a
    model name/path.** No router anywhere in `app/api/` calls
    `build_embedding_provider()`, `get_embedding_provider()`, or
    constructs `SentenceTransformerEmbeddingProvider` directly — the only
    caller is `app/embeddings/provider.py` itself, reading exclusively
    from `app.core.config.settings`. `app/schemas/retrieval.py`'s own
    `model_name` field is a *response* field (`EmbeddingModelRead`,
    describing which model produced a result), never a request field —
    nothing under `app/schemas/` accepts a model name or filesystem path
    as request input for embeddings.
  * **Model files are not executable as uploaded content.** SIE has no
    endpoint anywhere that accepts a model-file upload; the ingestion
    upload path (`app/ingestion/`) only ever handles document content
    (PDF/DOCX/XLSX/...), never a model artifact.
"""

from __future__ import annotations

import logging

from app.embeddings.embedding_service import embedding_service
from app.models.enums import QualityStatus, ScopeType
from app.schemas.knowledge_chunk import KnowledgeChunkCreate
from app.schemas.knowledge_document import KnowledgeDocumentCreate
from app.schemas.knowledge_document_version import KnowledgeDocumentVersionCreate
from app.schemas.knowledge_source import KnowledgeSourceCreate
from app.services.knowledge_chunk_service import knowledge_chunk_service
from app.services.knowledge_document_service import knowledge_document_service
from app.services.knowledge_document_version_service import (
    knowledge_document_version_service,
)
from app.services.knowledge_source_service import knowledge_source_service

SENSITIVE_CONTENT = "The confidential incident involved employee Jane Doe at Site 4B, badge 88213."


def make_chunk(db_session, content: str):
    source = knowledge_source_service.create(
        db_session,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL, publisher="Test", name="Security Test Source", source_type="regulation"
        ),
    )
    document = knowledge_document_service.create(
        db_session,
        obj_in=KnowledgeDocumentCreate(source_id=source.id, title="Doc", document_type="regulation_text"),
    )
    version = knowledge_document_version_service.create(
        db_session,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1", content_hash="hash-security-test", storage_reference="ref"
        ),
    )
    (chunk,) = knowledge_chunk_service.create_many(
        db_session,
        document_version=version,
        chunks_in=[
            KnowledgeChunkCreate(
                chunk_index=0,
                content=content,
                character_count=len(content),
                document_id=document.id,
                source_id=source.id,
                organization_id=None,
                quality_status=QualityStatus.HIGH,
            )
        ],
    )
    return chunk


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _record_text(record: logging.LogRecord) -> str:
    """Every string this log record could possibly surface -- the
    formatted message, plus every value in `extra` (accessed via
    `record.__dict__`, since `logging` merges `extra` keys directly into
    the record's own `__dict__`)."""
    parts = [record.getMessage()]
    for key, value in record.__dict__.items():
        if key not in logging.LogRecord.__dict__ and key != "args":
            parts.append(str(value))
    return " ".join(parts)


def test_single_chunk_embedding_failure_log_never_contains_chunk_content(db_session):
    chunk = make_chunk(db_session, SENSITIVE_CONTENT)

    class BrokenProvider:
        provider_name = "broken"
        model_name = "broken-model"
        model_version = "v1"
        dimensions = 256

        def embed_text(self, text):
            raise RuntimeError("simulated failure")

        def embed_texts(self, texts):
            return [self.embed_text(t) for t in texts]

    handler = _RecordingHandler()
    embedding_logger = logging.getLogger("app.embeddings.embedding_service")
    embedding_logger.addHandler(handler)
    embedding_logger.setLevel(logging.DEBUG)
    try:
        outcome = embedding_service.embed_chunk(db_session, chunk=chunk, provider=BrokenProvider())
    finally:
        embedding_logger.removeHandler(handler)

    assert outcome.status.value == "failed"
    assert handler.records, "Expected at least one log record for the failure."
    for record in handler.records:
        assert SENSITIVE_CONTENT not in _record_text(record)
        assert "Jane Doe" not in _record_text(record)


def test_batch_isolation_failure_log_never_contains_chunk_content(db_session):
    good_chunk = make_chunk(db_session, "Ordinary safety text about ladders.")
    bad_chunk = make_chunk(db_session, SENSITIVE_CONTENT)

    class SometimesBrokenProvider:
        provider_name = "sometimes-broken"
        model_name = "m"
        model_version = "v1"
        dimensions = 256

        def embed_text(self, text):
            if text == SENSITIVE_CONTENT:
                raise RuntimeError("simulated failure")
            return [0.1] * 256

        def embed_texts(self, texts):
            return [self.embed_text(t) for t in texts]

    handler = _RecordingHandler()
    embedding_logger = logging.getLogger("app.embeddings.embedding_service")
    embedding_logger.addHandler(handler)
    embedding_logger.setLevel(logging.DEBUG)
    try:
        report = embedding_service.embed_chunks_batch(
            db_session, chunks=[good_chunk, bad_chunk], provider=SometimesBrokenProvider()
        )
    finally:
        embedding_logger.removeHandler(handler)

    assert report.created == 1
    assert report.failed == 1
    assert handler.records
    for record in handler.records:
        assert SENSITIVE_CONTENT not in _record_text(record)
        assert "Jane Doe" not in _record_text(record)
        assert "Ordinary safety text about ladders." not in _record_text(record)
