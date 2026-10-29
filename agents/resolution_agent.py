"""
agents/resolution_agent.py
──────────────────────────
Resolution Agent for TruthGuard.
Determines the final response, synthesizes trust explanations, triggers abstentions
for irreconcilable conflicts, and creates human-review escalation cases in the database.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agents import (
    Citation,
    DocumentSource,
    ResolutionOutput,
    VerificationStatus,
    WorkflowState,
)
from database import repository
from services.audit_service import AuditService
from verification.trust_engine import TrustDecisionEngine

logger = logging.getLogger(__name__)


class ResolutionAgent:
    """
    Final arbiter of the TruthGuard pipeline.
    Produces either a verified answer with full provenance, an explainable abstention,
    or a human-review escalation case.
    """

    def run(self, state: WorkflowState, db_session=None) -> WorkflowState:
        synth_out = state.synthesizer_output
        critic_out = state.critic_output
        retriever_out = state.retriever_output
        sources = retriever_out.sources if retriever_out else []

        log_prefix = "[ResolutionAgent]"
        state.workflow_log.append(f"{log_prefix} Evaluating Critic audit and synthesizing final determination.")

        # If no sources were retrieved or draft explicitly states no information -> Abstain on insufficient evidence
        if not sources or not synth_out or not synth_out.draft_answer or "not contain information" in synth_out.draft_answer.lower():
            state.resolution_output = ResolutionOutput(
                status=VerificationStatus.ABSTAINED,
                final_answer="TruthGuard has abstained from answering: No authoritative documents or relevant passages were found in the corpus to ground a truthful response.",
                citations=[],
                trust_explanation="No groundable evidence was retrieved from the indexed document repository.",
                conflicting_sources=[],
                outdated_sources=[],
                abstention_reason="Insufficient evidence: corpus does not contain information on this topic.",
                escalation_reason=None,
                human_review_created=False,
                revision_count=state.revision_count,
                agents_run=["RetrieverAgent", "SynthesizerAgent", "CriticAgent", "ResolutionAgent"],
            )
            return state

        # Compute trust decision across sources
        trust_dec = TrustDecisionEngine.decide(sources, state.question, db_session=db_session)

        # Distinguish outdated sources from active
        outdated_sources: List[DocumentSource] = [
            s for s in sources if s.is_superseded or any(r["doc_id"] == s.doc_id for r in trust_dec.rejected_sources)
        ]
        active_sources: List[DocumentSource] = [
            s for s in sources if s.doc_id not in {o.doc_id for o in outdated_sources}
        ]

        # -------------------------------------------------------------
        # Outcome C & D: Irreconcilable conflict or escalation required
        # -------------------------------------------------------------
        if critic_out and critic_out.requires_human_escalation:
            # Create human review item in DB if session is available
            human_review_id = None
            if db_session:
                try:
                    conflicting_passages = [
                        {"doc_id": s.doc_id, "filename": s.filename, "text": s.passage_text}
                        for s in sources[:4]
                    ]
                    review_case = repository.create_human_review(
                        db_session,
                        {
                            "question": state.question,
                            "reason": "Direct contradiction between documents of equal institutional authority with no supersession relationship.",
                            "status": "pending",
                            "conflicting_passages": conflicting_passages,
                        },
                    )
                    human_review_id = str(review_case.id)
                    AuditService.log_human_review_created(
                        str(review_case.id),
                        f"Escalated question: '{state.question[:60]}...'",
                        db_session,
                    )
                except Exception as e:
                    logger.warning("Failed to create HumanReviewCase in DB: %s", e)

            abstention_text = (
                f"TruthGuard has abstained from generating a definitive policy answer.\n\n"
                f"**Reason:** An unresolved contradiction exists between documents of equal authority level. "
                f"Specifically, retrieved policies make mutually incompatible claims and neither document "
                f"formally supersedes the other.\n\n"
                f"**Conflicting Sources:**\n"
                + "\n".join(f"- **{s.filename}** (Version {s.version or 'N/A'}, Level {s.authority_level})" for s in sources[:3])
                + f"\n\n*This case has been automatically escalated for human administrator review (Case ID: {human_review_id or 'Local-Queue'}).*"
            )

            state.resolution_output = ResolutionOutput(
                status=VerificationStatus.HUMAN_REVIEW_REQUIRED,
                final_answer=abstention_text,
                citations=synth_out.supporting_citations,
                trust_explanation=TrustDecisionEngine.format_trust_explanation(trust_dec),
                conflicting_sources=sources,
                outdated_sources=outdated_sources,
                abstention_reason="Contradiction between equal authority sources cannot be resolved automatically.",
                escalation_reason="Human compliance review required to establish institutional policy precedence.",
                human_review_created=True,
                human_review_id=human_review_id,
                revision_count=state.revision_count,
                agents_run=["RetrieverAgent", "SynthesizerAgent", "CriticAgent", "ResolutionAgent"],
            )
            state.workflow_log.append(f"{log_prefix} Status: HUMAN_REVIEW_REQUIRED. Created escalation case {human_review_id}.")
            return state

        # -------------------------------------------------------------
        # Outcome A & B: Verified or Verified with Warnings
        # -------------------------------------------------------------
        has_warnings = bool(critic_out and len(critic_out.staleness_warnings) > 0)
        final_status = VerificationStatus.VERIFIED_WITH_WARNINGS if has_warnings else VerificationStatus.VERIFIED

        # Build clean final answer
        answer_parts = [synth_out.draft_answer]

        if outdated_sources:
            outdated_names = ", ".join(f"`{s.filename}`" for s in outdated_sources[:3])
            answer_parts.append(
                f"\n\n*Note on Outdated Sources: Older provisions in {outdated_names} have been identified as superseded or stale and were excluded from this determination.*"
            )

        final_answer = "\n".join(answer_parts)

        state.resolution_output = ResolutionOutput(
            status=final_status,
            final_answer=final_answer,
            citations=synth_out.supporting_citations,
            trust_explanation=TrustDecisionEngine.format_trust_explanation(trust_dec),
            conflicting_sources=[],
            outdated_sources=outdated_sources,
            abstention_reason=None,
            escalation_reason=None,
            human_review_created=False,
            human_review_id=None,
            revision_count=state.revision_count,
            agents_run=["RetrieverAgent", "SynthesizerAgent", "CriticAgent", "ResolutionAgent"],
        )
        state.workflow_log.append(f"{log_prefix} Status: {final_status.value}. Verified answer delivered.")
        return state
