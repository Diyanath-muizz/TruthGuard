"""
tests/test_workflows.py
───────────────────────
Integration tests for LangGraph Question-Answering Graph.
"""

from __future__ import annotations

import pytest
from agents import VerificationStatus
from database.initialization import get_db, initialize_database
from workflows.question_answering_graph import run_qa_workflow


def test_qa_workflow_runs_end_to_end():
    initialize_database()
    with get_db() as session:
        state = run_qa_workflow(
            question="What is the non-existent policy for lunar vacations?",
            db_session=session,
            max_revisions=2,
        )
        assert state.resolution_output is not None
        assert state.resolution_output.status == VerificationStatus.ABSTAINED
        assert len(state.workflow_log) >= 4


def test_max_revision_limit_enforced():
    initialize_database()
    with get_db() as session:
        state = run_qa_workflow(
            question="Check revision count boundary",
            db_session=session,
            max_revisions=2,
        )
        assert state.revision_count <= 2
