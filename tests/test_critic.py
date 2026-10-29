"""
tests/test_critic.py
────────────────────
Unit tests for Adversarial Critic Agent.
"""

from __future__ import annotations

import pytest
from agents import (
    Citation,
    ConflictDetail,
    DocumentSource,
    FactualClaim,
    RetrieverOutput,
    SynthesizerOutput,
    WorkflowState,
)
from agents.critic_agent import CriticAgent


def test_critic_flags_blended_numeric_compromise():
    critic = CriticAgent()
    state = WorkflowState(question="How many days of leave?")
    state.retriever_output = RetrieverOutput(
        question="How many days of leave?",
        sources=[],
    )
    # Draft answer incorrectly blends values into "12 to 15 days"
    state.synthesizer_output = SynthesizerOutput(
        question="How many days of leave?",
        draft_answer="Employees are entitled to 12 to 15 days of annual leave.",
        factual_claims=[
            FactualClaim(claim_id="c1", claim_text="12 to 15 days", is_supported=False)
        ],
        supporting_citations=[],
    )

    result_state = critic.run(state)
    assert result_state.critic_output.passes_verification is False
    assert any(f.finding_type == "contradiction" for f in result_state.critic_output.contradictions)


def test_critic_flags_unsupported_claim():
    critic = CriticAgent()
    state = WorkflowState(question="What is the dental allowance?")
    state.retriever_output = RetrieverOutput(
        question="What is the dental allowance?",
        sources=[],
    )
    state.synthesizer_output = SynthesizerOutput(
        question="What is the dental allowance?",
        draft_answer="Dental coverage is $2,000 per year.",
        factual_claims=[
            FactualClaim(claim_id="c1", claim_text="Dental coverage is $2,000", supporting_sources=[])
        ],
        supporting_citations=[],
    )

    result_state = critic.run(state)
    assert result_state.critic_output.passes_verification is False
    assert any(f.finding_type == "unsupported_claim" for f in result_state.critic_output.unsupported_claims)
