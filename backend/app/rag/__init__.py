"""Evidence-Grounded RAG v0.1 — a controlled reasoning layer over SIE's
existing retrieval evidence.

    User Question
        -> Authorization / Tenant Context (existing, reused unchanged)
        -> RetrievalService (existing, reused unchanged)
        -> EvidenceSelectionService (app/rag/evidence_selection.py)
        -> evaluate_sufficiency (app/rag/sufficiency.py)
        -> detect_conflicts (app/rag/conflict.py)
        -> build_grounded_context (app/rag/context_builder.py)
        -> LLMProvider (app/llm/provider.py)
        -> citation validation (app/rag/citations.py)
        -> RAGResponse (app/rag/results.py), with citations/provenance

See `app/rag/rag_service.py`'s module docstring for the full orchestration
and every deterministic gate that can end the flow *before* an LLM is ever
called (insufficient evidence, a detected source conflict, or a privacy
boundary) — none of those decisions is ever delegated to the LLM itself.

**The LLM is not the source of truth.** SIE's knowledge sources are the
evidence; the LLM is a reasoning/language-generation layer operating over
retrieved evidence — never a fact source in its own right. See the
README's "Evidence-Grounded RAG" section.
"""
