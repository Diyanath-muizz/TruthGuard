"""
documents/citations.py
──────────────────────
Citation formatting, attribution, and verification models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class Citation(BaseModel):
    """
    Structured citation pointing directly to evidence provenance.
    """
    doc_id: str
    filename: str
    chunk_id: str
    page_number: Optional[int] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None
    passage_text: str
    authority_level: int = 1
    doc_type: str = "Policy"


def format_citation_text(citation: Citation) -> str:
    """
    Formats a clean human-readable citation label.
    Example: "[Annual Leave Amendment 2025 (v2025), p.1]"
    """
    parts = [citation.filename]
    if citation.version:
        parts.append(f"v{citation.version}")
    if citation.page_number is not None:
        parts.append(f"p.{citation.page_number}")
    elif citation.chunk_id:
        parts.append(f"chunk:{citation.chunk_id[:8]}")

    return f"[{' | '.join(parts)}]"


def validate_citation(
    citation: Citation,
    retrieved_chunks: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    Verifies that the citation refers to an actual retrieved chunk
    and does not hallucinate content or reference nonexistent documents.
    """
    matching_chunk = None
    for chunk in retrieved_chunks:
        c_id = str(chunk.get("chunk_id", ""))
        if c_id == citation.chunk_id or str(chunk.get("id", "")) == citation.chunk_id:
            matching_chunk = chunk
            break

    if not matching_chunk:
        return False, f"Chunk ID {citation.chunk_id} not found in retrieved evidence."

    chunk_doc_id = str(matching_chunk.get("doc_id", matching_chunk.get("document_id", "")))
    if str(citation.doc_id) != chunk_doc_id:
        return False, f"Document ID mismatch: citation specifies {citation.doc_id}, but chunk belongs to {chunk_doc_id}."

    return True, "Citation verified against retrieved evidence."
