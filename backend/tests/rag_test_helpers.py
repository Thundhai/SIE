"""Shared test helper for constructing `RetrievalResult`/`SelectedEvidenceItem`
objects directly, without a database — used by every pure-unit RAG test
(evidence selection, sufficiency, conflict detection, citations, context
building, RAGService orchestration with retrieval stubbed out). Mirrors
the "build the domain object with sane defaults, override what the test
cares about" shape already used throughout this codebase's test suite.
"""

from __future__ import annotations

import uuid

from app.models.enums import ContentType, ExtractionMethod, QualityStatus, VerificationStatus
from app.rag.results import SelectedEvidenceItem
from app.retrieval.results import RelevanceLevel, RetrievalResult


def make_retrieval_result(**overrides) -> RetrievalResult:
    # Content defaults to something unique per call (a fresh uuid
    # fragment appended) so tests that build several results without
    # overriding `content` never accidentally collide with
    # EvidenceSelectionService's near-duplicate detection — a test that
    # actually wants two results to look like near-duplicates passes
    # matching `content=` explicitly instead.
    unique_suffix = uuid.uuid4().hex[:8]
    defaults = dict(
        rank=1,
        chunk_id=uuid.uuid4(),
        similarity=0.5,
        relevance=RelevanceLevel.HIGH,
        content=f"Workers must wear a full-body harness when working at height. ({unique_suffix})",
        content_type=ContentType.TEXT,
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        document_title="Working at Height Procedure",
        source_name="Company Working at Height Procedure",
        source_publisher="Acme Industrial",
        version_label="v1",
        location="Page 47, Section 6.2",
        page_number=47,
        sheet_name=None,
        row_number=None,
        slide_number=None,
        section_title="Fall Protection",
        section_path=["Fall Protection"],
        extraction_quality=QualityStatus.HIGH,
        extraction_method=ExtractionMethod.TEXT_EXTRACTION,
        source_authority_level="internal_procedure",
        verification_status=VerificationStatus.VERIFIED,
        scope="GLOBAL",
        organization_id=None,
        jurisdiction=None,
        industry_sector=None,
        publication_date=None,
        effective_date=None,
    )
    defaults.update(overrides)
    return RetrievalResult(**defaults)


def make_selected_item(citation_id: str = "E1", **overrides) -> SelectedEvidenceItem:
    return SelectedEvidenceItem(citation_id=citation_id, result=make_retrieval_result(**overrides))
