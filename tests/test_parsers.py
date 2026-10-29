"""
tests/test_parsers.py
─────────────────────
Unit tests for documents/parsers.py and metadata extraction.
"""

from __future__ import annotations

import io
import pytest
from documents.parsers import DocumentParser, ParseResult
from documents.metadata import extract_metadata_from_text, validate_metadata


def test_txt_parser_success():
    parser = DocumentParser()
    raw = b"DOCUMENT TITLE: Annual Leave Policy 2024\nVERSION: 2024\nEmployees receive 12 days of leave."
    result = parser.parse(raw, "leave.txt")
    assert result.success is True
    assert "12 days of leave" in result.text
    assert len(result.pages) >= 1


def test_empty_file_rejected():
    parser = DocumentParser()
    result = parser.parse(b"", "empty.txt")
    assert result.success is False
    assert result.error is not None


def test_unsupported_format_rejected():
    parser = DocumentParser()
    result = parser.parse(b"dummy bytes", "document.exe")
    assert result.success is False
    assert "Unsupported file extension" in result.error


def test_metadata_extraction_from_headers():
    text = (
        "DOCUMENT TITLE: Travel Expense Standard 2025\n"
        "TYPE: Policy\n"
        "VERSION: 2.1\n"
        "PUBLICATION DATE: 2025-01-01\n"
        "EFFECTIVE DATE: 2025-02-01\n"
        "EXPIRATION DATE: 2026-02-01\n"
        "DEPARTMENT: Sales\n"
        "SUPERSEDES: Travel Expense Standard 2024\n"
        "AUTHORITY LEVEL: 3\n"
    )
    meta = extract_metadata_from_text(text)
    assert meta["title"] == "Travel Expense Standard 2025"
    assert meta["doc_type"] == "Policy"
    assert meta["version"] == "2.1"
    assert meta["effective_date"] == "2025-02-01"
    assert meta["department"] == "Sales"
    assert meta["supersedes"] == "Travel Expense Standard 2024"
    assert meta["authority_level"] == 3


def test_validate_metadata_warnings():
    incomplete_data = {"doc_type": "Amendment"}
    val_meta, warnings = validate_metadata(incomplete_data)
    assert val_meta.doc_type == "Amendment"
    assert any("Effective date is missing" in w for w in warnings)
    assert any("does not explicitly specify which policy it supersedes" in w for w in warnings)
