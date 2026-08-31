"""Content hashing.

Every ingested file's identity is its content, never its filename — two
files with the same name can differ, two files with different names can
be byte-identical. SHA-256 is used everywhere a file's bytes need a
stable, secure identifier: `IngestedFile.content_hash`,
`KnowledgeDocumentVersion.content_hash` (reused directly — see
app/services/knowledge_document_version_service.py's existing dedup),
and duplicate-file detection in the ingestion service.
"""

import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
