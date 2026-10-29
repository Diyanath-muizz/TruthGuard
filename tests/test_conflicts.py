"""
tests/test_conflicts.py
───────────────────────
Unit tests for contradiction detection, staleness checking, and supersession.
"""

from __future__ import annotations

import pytest
from agents import DocumentSource
from verification.contradiction_detector import ContradictionDetector
from verification.staleness_checker import StalenessChecker
from verification.supersession_graph import SupersessionGraph


def test_numeric_contradiction_detection():
    detector = ContradictionDetector()
    src_a = DocumentSource(
        doc_id="1",
        filename="leave_2024.txt",
        doc_type="Policy",
        chunk_id="c1",
        passage_text="Employees receive 12 days of annual leave per year.",
    )
    src_b = DocumentSource(
        doc_id="2",
        filename="leave_2025.txt",
        doc_type="Amendment",
        chunk_id="c2",
        passage_text="Employees receive 15 days of annual leave per year.",
    )

    conflicts = detector.detect_conflicts([src_a, src_b])
    assert len(conflicts) > 0
    assert any(c.conflict_type == "numerical" for c in conflicts)


def test_staleness_checker_expired():
    res = StalenessChecker.check_staleness(
        {"expiration_date": "2022-01-01", "status": "active"},
        reference_date="2025-01-01",
    )
    assert res.is_stale is True
    assert res.is_expired is True


def test_staleness_checker_future_effective():
    res = StalenessChecker.check_staleness(
        {"effective_date": "2029-01-01", "status": "active"},
        reference_date="2025-01-01",
    )
    assert res.is_future_dated is True


def test_supersession_graph_detection():
    graph = SupersessionGraph()
    text = "Section 1: Annual Leave. This amendment explicitly supersedes the Annual Leave Policy 2024."
    candidates = [
        {"id": "1", "title": "Annual Leave Policy 2024", "filename": "leave_2024.txt"}
    ]
    detected = graph.detect_from_text(text, candidates)
    assert len(detected) == 1
    assert detected[0]["target_doc_id"] == "1"
    assert detected[0]["relationship_type"] == "supersedes"
