"""
tests/test_resolution.py
────────────────────────
Unit tests for Resolution Agent.
"""

from __future__ import annotations

import pytest
from agents import (
    Citation,
    CriticOutput,
    DocumentSource,
    FactualClaim,
    ResolutionOutput,
    RetrieverOutput,
    SynthesizerOutput,
    VerificationStatus,
    WorkflowState,
)
from agents.resolution_agent import ResolutionAgent


def test_resolution_verified_outcome():
    agent = ResolutionAgent()
    src = DocumentSource(
        doc_id="1",
        filename="leave_2025.txt",
        doc_type="Amendment",
        authority_level=4,
        chunk_id="c1",
        passage_text="Employees receive 15 days of annual leave.",
        effective_date="2025-01-01",
    )
    state = WorkflowState(
        question="How many days of leave?",
        retriever_output=RetrieverOutput(question="How many days?", sources=[src]),
        synthesizer_output=SynthesizerOutput(
            question="How many days?",
            draft_answer="Employees receive 15 days of annual leave.",
            supporting_citations=[
                Citation(
                    doc_id="1",
                    filename="leave_2025.txt",
                    chunk_id="c1",
                    passage_text="Employees receive 15 days.",
                    authority_level=4,
                    doc_type="Amendment",
                )
            ],
            sources_used=[src],
        ),
        critic_output=CriticOutput(
            passes_verification=True,
            overall_confidence="high",
            all_findings=[],
        ),
    )

    out = agent.run(state)
    assert out.resolution_output.status == VerificationStatus.VERIFIED
    assert "15 days" in out.resolution_output.final_answer


def test_resolution_abstains_on_insufficient_evidence():
    agent = ResolutionAgent()
    state = WorkflowState(
        question="What is the gym membership stipend?",
        retriever_output=RetrieverOutput(question="What is the gym membership stipend?", sources=[]),
        synthesizer_output=SynthesizerOutput(
            question="What is the gym membership stipend?",
            draft_answer="",
            sources_used=[],
        ),
    )
    out = agent.run(state)
    assert out.resolution_output.status == VerificationStatus.ABSTAINED
    assert "abstained" in out.resolution_output.final_answer.lower()
