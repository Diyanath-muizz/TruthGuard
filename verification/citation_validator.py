"""
verification/citation_validator.py
──────────────────────────────────
Deterministic citation validation verifying evidence existence and scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents import Citation

logger = logging.getLogger(__name__)


@dataclass
class CitationValidationResult:
    """
    Detailed validation outcome for a single citation.
    """
    citation_id: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class CitationValidator:
    """
    Performs rigorous checks ensuring no fabricated citations or mismatched chunks.
    """

    @classmethod
    def validate(
        cls,
        citation: Citation,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> CitationValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        cit_id = f"{citation.doc_id}:{citation.chunk_id}"

        # 1. Match chunk_id
        matched_chunk = None
        for chunk in retrieved_chunks:
            c_id = str(chunk.get("chunk_id", chunk.get("id", "")))
            if c_id == citation.chunk_id or str(chunk.get("chroma_chunk_id", "")) == citation.chunk_id:
                matched_chunk = chunk
                break

        if not matched_chunk:
            errors.append(f"Citation references chunk '{citation.chunk_id}' which does not exist in retrieved sources.")
            return CitationValidationResult(citation_id=cit_id, is_valid=False, errors=errors)

        # 2. Match doc_id
        chunk_doc_id = str(matched_chunk.get("doc_id", matched_chunk.get("document_id", "")))
        if chunk_doc_id and str(citation.doc_id) != chunk_doc_id:
            errors.append(f"Document ID mismatch: citation specifies {citation.doc_id}, but chunk belongs to {chunk_doc_id}.")

        # 3. Verify text overlap
        chunk_text = matched_chunk.get("text", matched_chunk.get("passage_text", "")).lower()
        cit_text = citation.passage_text.lower()
        if cit_text:
            # Check if keywords in citation appear in chunk
            words = [w for w in cit_text.split() if len(w) > 3]
            if words:
                overlap = sum(1 for w in words if w in chunk_text) / len(words)
                if overlap < 0.4:
                    warnings.append("Cited text has low lexical overlap with the underlying chunk text.")

        return CitationValidationResult(
            citation_id=cit_id,
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
        )

    @classmethod
    def validate_all(
        cls,
        citations: List[Citation],
        retrieved_chunks: List[Dict[str, Any]],
    ) -> List[CitationValidationResult]:
        return [cls.validate(c, retrieved_chunks) for c in citations]
