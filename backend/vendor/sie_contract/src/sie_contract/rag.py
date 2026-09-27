"""RAG boundary -- citation identity only, never retrieval/ranking policy.

See `../../docs/BOUNDARY_DECISIONS.md` Section 5 for the full RAG
classification. Summary: the *generic* retrieval interface and result
shape (Thundhai/SIE's existing `app/retrieval/*`, `app/embeddings/*`)
are already Public SIE infrastructure and need no new contract type --
they are not Commercial-Core-specific. What Commercial Core's private
RAG orchestration (`app/rag/*`: evidence selection, sufficiency policy,
conflict handling, citation validation) *produces* -- an answer with
citations -- is the one RAG-domain output worth a contract type, and
even that is redacted here: Thundhai/SIE's existing `CitationRead`
carries `similarity` (a retrieval-ranking signal) and
`source_authority_level`/`extraction_quality` (internal quality-scoring
detail) -- none of those are in `CitationReferenceDTO` below. A citation
is exposed as *what was cited*, never *how confidently or why it was
selected over alternatives*.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from sie_contract.common import AsOfWindow


class CitationReferenceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation_id: str = Field(..., description="Stable identifier used inline in the answer text, e.g. 'E1'.")
    document_id: uuid.UUID
    source: str = Field(..., description="Source name, e.g. '29 CFR 1910'.")
    document: str = Field(..., description="Document title.")
    version: str = Field(..., description="Document version label.")
    location: str | None = Field(default=None, description="A locator within the document, e.g. a section number, when available.")


class RAGAnswerDTO(BaseModel):
    """A completed RAG answer. `answer` is the generated natural-language
    text; `citations` is what supports it. Nothing here describes how
    evidence was selected, how sufficiency was judged, or how a conflict
    between sources was resolved -- see BOUNDARY_DECISIONS.md."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID | None = Field(default=None, description="None for a GLOBAL-scope query.")
    query: str
    answer: str
    citations: list[CitationReferenceDTO] = Field(default_factory=list)
    as_of: AsOfWindow
