"""
agents/retriever_agent.py
─────────────────────────
Retriever Agent for TruthGuard.
Executes hybrid semantic + BM25 retrieval, extracts provenance metadata,
and flags preliminary conflicts across retrieved passages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agents import (
    ConflictDetail,
    DocumentSource,
    RetrieverOutput,
    WorkflowState,
)
from retrieval.hybrid_retriever import HybridRetriever, HybridResult
from verification.contradiction_detector import ContradictionDetector

logger = logging.getLogger(__name__)


class RetrieverAgent:
    """
    Agent responsible for searching the multi-version document corpus,
    retaining document provenance, and returning structured evidence.
    """

    def __init__(self, hybrid_retriever: Optional[HybridRetriever] = None) -> None:
        self.retriever = hybrid_retriever or HybridRetriever()
        self.contradiction_detector = ContradictionDetector()

    def run(self, state: WorkflowState, db_session=None) -> WorkflowState:
        """
        Executes hybrid retrieval and initial conflict detection for the user question.
        """
        question = state.question
        log_entry = f"[RetrieverAgent] Querying corpus for: '{question}'"
        state.workflow_log.append(log_entry)
        logger.info(log_entry)

        try:
            raw_results: List[HybridResult] = self.retriever.retrieve(question, top_k=15)
        except Exception as e:
            logger.exception("Retrieval failed: %s", e)
            raw_results = []

        sources: List[DocumentSource] = []
        passages_for_detector: List[Dict[str, Any]] = []

        for r in raw_results:
            meta = r.metadata or {}
            source = DocumentSource(
                doc_id=str(r.doc_id),
                filename=meta.get("filename") or f"doc_{r.doc_id}",
                doc_type=r.doc_type or meta.get("doc_type", "Policy"),
                version=r.version or meta.get("version"),
                effective_date=r.effective_date or meta.get("effective_date"),
                authority_level=r.authority_level or meta.get("authority_level", 1),
                chunk_id=str(r.chunk_id),
                passage_text=r.text,
                page_number=meta.get("page_number"),
                rrf_score=round(r.rrf_score, 4),
                is_superseded=bool(meta.get("is_superseded", False)),
                superseded_by=meta.get("superseded_by"),
            )
            sources.append(source)
            passages_for_detector.append({
                "chunk_id": str(r.chunk_id),
                "doc_id": str(r.doc_id),
                "filename": source.filename,
                "text": r.text,
                "authority_level": source.authority_level,
                "doc_type": source.doc_type,
            })

        # Run contradiction detector across retrieved passages
        potential_conflicts: List[ConflictDetail] = []
        try:
            potential_conflicts = self.contradiction_detector.detect_conflicts(sources)
        except Exception as e:
            logger.warning("Contradiction detection failed: %s", e)

        state.retriever_output = RetrieverOutput(
            question=question,
            sources=sources,
            potential_conflicts=potential_conflicts,
            retrieval_metadata={
                "total_chunks_retrieved": len(sources),
                "unique_documents": len({s.doc_id for s in sources}),
            },
        )

        state.workflow_log.append(
            f"[RetrieverAgent] Retrieved {len(sources)} passages from {len({s.doc_id for s in sources})} documents. "
            f"Flagged {len(potential_conflicts)} potential conflicts."
        )
        return state
