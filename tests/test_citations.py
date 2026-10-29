"""
tests/test_citations.py
───────────────────────
Unit tests for CitationValidator and provenance checks.
"""

from __future__ import annotations

import pytest
from agents import Citation
from verification.citation_validator import CitationValidator


def test_valid_citation():
    cit = Citation(
        doc_id="1",
        filename="policy.txt",
        chunk_id="chunk_123",
        passage_text="Employees receive 15 days of annual leave.",
        authority_level=3,
        doc_type="Policy",
    )
    raw_chunks = [
        {
            "id": "chunk_123",
            "chunk_id": "chunk_123",
            "doc_id": "1",
            "text": "Employees receive 15 days of annual leave per year.",
        }
    ]
    res = CitationValidator.validate(cit, raw_chunks)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_missing_chunk_citation_fails():
    cit = Citation(
        doc_id="1",
        filename="policy.txt",
        chunk_id="chunk_nonexistent",
        passage_text="Unmatched text",
        authority_level=3,
        doc_type="Policy",
    )
    raw_chunks = [{"chunk_id": "chunk_other", "doc_id": "1", "text": "Something else."}]
    res = CitationValidator.validate(cit, raw_chunks)
    assert res.is_valid is False
    assert any("does not exist in retrieved sources" in e for e in res.errors)
