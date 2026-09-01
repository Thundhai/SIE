"""RAG evaluation harness — milestone items 30-31. "Prototype RAG
evaluation" per the same honesty standard `tests/evaluation/harness.py`
(the Recall@K harness) already establishes: a small, synthetic,
regression-catching check against a real PostgreSQL + pgvector database
(see tests/postgres_support.py), never a production/enterprise accuracy
claim.

    seed_rag_evaluation_fixtures() -> real KnowledgeChunk +
        KnowledgeChunkEmbedding rows (the existing Recall@K corpus, plus
        a conflicting source pair and an injected document)
        -> run_rag_evaluation() -> RAGEvaluationReport, with separate
           metrics per dimension (milestone item 31: "do not invent a
           single AI accuracy score that hides these dimensions")

Every number this harness produces comes from actually running
`RAGService.query()` — through the same production
`EvidenceSelectionService`/`evaluate_sufficiency`/`detect_conflicts`/
citation-validation code path every other RAG request in this codebase
goes through — with `FakeLLMProvider` (the same deterministic, offline,
non-real-model test provider every other RAG test in this codebase
uses). Nothing here is fabricated or extrapolated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.llm.provider import FakeLLMProvider, LLMProvider
from app.models.enums import QualityStatus, ScopeType
from app.rag.rag_service import RAGService, rag_service as default_rag_service
from app.rag.results import RAGOutcome
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
from tests.evaluation.harness import seed_evaluation_corpus
from tests.fixtures.evaluation.rag_questions import (
    ALL_RAG_QUESTIONS,
    CONFLICT_SOURCE_A_NAME,
    CONFLICT_SOURCE_A_TEXT,
    CONFLICT_SOURCE_B_NAME,
    CONFLICT_SOURCE_B_TEXT,
    INJECTION_DOCUMENT_NAME,
    INJECTION_DOCUMENT_TEXT,
)

LABEL = "Prototype RAG evaluation result on synthetic fixture dataset — not a production benchmark."


def _seed_single_chunk(db: Session, *, text: str, source_name: str, provider: EmbeddingProvider) -> None:
    from app.embeddings.embedding_service import embedding_service

    source = knowledge_source_service.create(
        db,
        obj_in=KnowledgeSourceCreate(
            scope_type=ScopeType.GLOBAL,
            publisher="SIE Evaluation Fixtures",
            name=source_name,
            source_type="evaluation_fixture",
        ),
    )
    document = knowledge_document_service.create(
        db,
        obj_in=KnowledgeDocumentCreate(
            source_id=source.id, title=source_name, document_type="evaluation_fixture"
        ),
    )
    version = knowledge_document_version_service.create(
        db,
        document=document,
        obj_in=KnowledgeDocumentVersionCreate(
            version_label="v1", content_hash=f"rag-eval-{source_name}", storage_reference="fixture://rag-eval"
        ),
    )
    (chunk,) = knowledge_chunk_service.create_many(
        db,
        document_version=version,
        chunks_in=[
            KnowledgeChunkCreate(
                chunk_index=0,
                content=text,
                character_count=len(text),
                document_id=document.id,
                source_id=source.id,
                organization_id=None,
                quality_status=QualityStatus.HIGH,
            )
        ],
    )
    outcome = embedding_service.embed_chunk(db, chunk=chunk, provider=provider, force=True)
    if outcome.status.value not in ("created", "skipped_existing"):
        raise RuntimeError(f"Failed to embed RAG evaluation fixture chunk: {outcome.status.value}")


def seed_rag_evaluation_fixtures(db: Session, *, provider: EmbeddingProvider | None = None) -> None:
    """Seeds the existing Recall@K corpus (unchanged, reused as-is) plus
    two small RAG-specific fixtures: a conflicting source pair and one
    document containing a prompt-injection attempt."""
    provider = provider or get_embedding_provider()
    seed_evaluation_corpus(db, provider=provider)
    _seed_single_chunk(db, text=CONFLICT_SOURCE_A_TEXT, source_name=CONFLICT_SOURCE_A_NAME, provider=provider)
    _seed_single_chunk(db, text=CONFLICT_SOURCE_B_TEXT, source_name=CONFLICT_SOURCE_B_NAME, provider=provider)
    _seed_single_chunk(db, text=INJECTION_DOCUMENT_TEXT, source_name=INJECTION_DOCUMENT_NAME, provider=provider)


@dataclass
class RAGEvaluationReport:
    """Separate metrics per dimension — milestone item 31: never one
    combined "AI accuracy score". Each is `None` when its category has no
    questions in the fixture set (never a fabricated 0.0/1.0)."""

    label: str = LABEL
    question_count: int = 0
    per_question: list[dict] = field(default_factory=list)

    answerable_grounding_rate: float | None = None
    partial_evidence_rate: float | None = None
    abstention_correctness: float | None = None
    conflict_detection_rate: float | None = None
    injection_resistance_rate: float | None = None
    citation_validity_rate: float | None = None
    unsupported_claim_rate: float | None = None
    tenant_leakage_count: int = 0

    def summary(self) -> str:
        parts = [
            f"answerable_grounding_rate={self.answerable_grounding_rate}",
            f"partial_evidence_rate={self.partial_evidence_rate}",
            f"abstention_correctness={self.abstention_correctness}",
            f"conflict_detection_rate={self.conflict_detection_rate}",
            f"injection_resistance_rate={self.injection_resistance_rate}",
            f"citation_validity_rate={self.citation_validity_rate}",
            f"unsupported_claim_rate={self.unsupported_claim_rate}",
            f"tenant_leakage_count={self.tenant_leakage_count}",
        ]
        return f"{self.label} " + ", ".join(parts) + f" (n={self.question_count} questions)"


def run_rag_evaluation(
    db: Session,
    *,
    service: RAGService | None = None,
    llm_provider: LLMProvider | None = None,
) -> RAGEvaluationReport:
    """Run every question in tests/fixtures/evaluation/rag_questions.py
    through the real `RAGService.query()` path and compute per-dimension
    metrics. `llm_provider` defaults to a fresh `FakeLLMProvider()` (the
    deterministic test provider — see app/llm/provider.py) so this
    evaluation never requires a real model or network access."""
    service = service or default_rag_service
    llm_provider = llm_provider or FakeLLMProvider()

    per_question: list[dict] = []
    from app.rag.prompt import SYSTEM_PROMPT_V1

    for question in ALL_RAG_QUESTIONS:
        response = service.query(
            db,
            query_text=question.query,
            allowed_organization_id=None,
            llm_provider=llm_provider,
        )
        invalid_citation_warnings = [w for w in response.warnings if w.startswith("INVALID_CITATION_REMOVED")]
        leaked_organizations = [c.organization_id for c in response.citations if c.organization_id is not None]
        per_question.append(
            {
                "category": question.category,
                "query": question.query,
                "outcome": response.outcome.value,
                "evidence_state": response.evidence_state.value,
                "citation_count": len(response.citations),
                "invalid_citation_count": len(invalid_citation_warnings),
                "system_prompt_leaked": SYSTEM_PROMPT_V1 in (response.answer or ""),
                "leaked_organization_count": len(leaked_organizations),
            }
        )

    report = RAGEvaluationReport(question_count=len(per_question), per_question=per_question)

    def _rate(category: str, predicate) -> float | None:
        rows = [r for r in per_question if r["category"] == category]
        if not rows:
            return None
        return sum(1 for r in rows if predicate(r)) / len(rows)

    report.answerable_grounding_rate = _rate(
        "answerable", lambda r: r["outcome"] == RAGOutcome.ANSWERED.value and r["citation_count"] >= 1
    )
    report.partial_evidence_rate = _rate(
        "partial",
        lambda r: r["evidence_state"] == "PARTIAL"
        or r["outcome"] in (RAGOutcome.INSUFFICIENT_EVIDENCE.value, RAGOutcome.ANSWERED.value),
    )
    report.abstention_correctness = _rate(
        "unanswerable", lambda r: r["outcome"] == RAGOutcome.INSUFFICIENT_EVIDENCE.value
    )
    report.conflict_detection_rate = _rate(
        "conflict", lambda r: r["outcome"] == RAGOutcome.SOURCE_CONFLICT.value
    )
    report.injection_resistance_rate = _rate("injection", lambda r: not r["system_prompt_leaked"])

    answered_or_rejected = [
        r
        for r in per_question
        if r["outcome"] in (RAGOutcome.ANSWERED.value, RAGOutcome.UNSUPPORTED_CLAIM_REJECTED.value)
    ]
    report.citation_validity_rate = (
        sum(1 for r in answered_or_rejected if r["invalid_citation_count"] == 0) / len(answered_or_rejected)
        if answered_or_rejected
        else None
    )
    report.unsupported_claim_rate = (
        sum(1 for r in per_question if r["outcome"] == RAGOutcome.UNSUPPORTED_CLAIM_REJECTED.value)
        / len(per_question)
        if per_question
        else None
    )
    report.tenant_leakage_count = sum(r["leaked_organization_count"] for r in per_question)

    return report
