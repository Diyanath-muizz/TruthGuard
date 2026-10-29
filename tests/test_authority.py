"""
tests/test_authority.py
────────────────────────
Unit tests for institutional authority rules.
"""

from __future__ import annotations

import pytest
from verification.authority_rules import AuthorityRules


def test_amendment_overrides_policy():
    doc_policy = {"id": "1", "title": "Leave Policy", "doc_type": "Policy", "authority_level": 3}
    doc_amend = {"id": "2", "title": "Leave Amendment", "doc_type": "Amendment", "authority_level": 4}

    dec = AuthorityRules.compare_authority(doc_policy, doc_amend)
    assert dec.preferred_doc_id == "2"
    assert "higher institutional authority" in dec.reason


def test_explicit_supersession_takes_precedence():
    doc_a = {
        "id": "1",
        "title": "Old Travel Policy",
        "doc_type": "Policy",
        "authority_level": 3,
        "filename": "travel_old.txt",
    }
    doc_b = {
        "id": "2",
        "title": "New Travel Policy",
        "doc_type": "Policy",
        "authority_level": 3,
        "supersedes": "Old Travel Policy",
        "filename": "travel_new.txt",
    }

    dec = AuthorityRules.compare_authority(doc_b, doc_a)
    assert dec.preferred_doc_id == "2"
    assert dec.is_explicit_supersession is True


def test_equal_authority_contradiction_triggers_abstention():
    doc_a = {"id": "1", "title": "Remote Work Policy A", "doc_type": "Policy", "authority_level": 3, "department": "All"}
    doc_b = {"id": "2", "title": "Remote Work Policy B", "doc_type": "Policy", "authority_level": 3, "department": "All"}

    dec = AuthorityRules.compare_authority(doc_a, doc_b)
    assert dec.preferred_doc_id is None
    assert dec.is_irreconcilable is True
