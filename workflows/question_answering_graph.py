"""
workflows/question_answering_graph.py
─────────────────────────────────────
LangGraph workflow orchestrating TruthGuard's 4-agent verification pipeline.

Graph Topology:
START
  │
  ▼
Retriever Agent
  │
  ▼
Synthesizer Agent ◄────────────┐
  │                           │
  ▼                           │
Critic Agent                  │
  │                           │
  ├─ If revision required ────┘  (max_revisions = 2)
  │
  ├─ If conflict is resolvable ─┐
  │                             │
  ├─ If evidence insufficient ──┤
  │                             ▼
  └──────────────────────► Resolution Agent
                                │
                                ▼
                               END
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, StateGraph

from agents import (
    RetrieverOutput,
    SynthesizerOutput,
    CriticOutput,
    ResolutionOutput,
    VerificationStatus,
    WorkflowState,
)
from agents.critic_agent import CriticAgent
from agents.resolution_agent import ResolutionAgent
from agents.retriever_agent import RetrieverAgent
from agents.synthesizer_agent import SynthesizerAgent
from config.settings import settings
from database import repository
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def create_qa_graph(db_session=None):
    """
    Constructs and compiles the LangGraph verification pipeline.
    """
    retriever = RetrieverAgent()
    synthesizer = SynthesizerAgent()
    critic = CriticAgent()
    resolution = ResolutionAgent()

    # 1. Define Node Functions
    def retriever_node(state: WorkflowState) -> WorkflowState:
        return retriever.run(state, db_session=db_session)

    def synthesizer_node(state: WorkflowState) -> WorkflowState:
        return synthesizer.run(state, db_session=db_session)

    def critic_node(state: WorkflowState) -> WorkflowState:
        return critic.run(state, db_session=db_session)

    def revision_prep_node(state: WorkflowState) -> WorkflowState:
        state.revision_count += 1
        state.workflow_log.append(
            f"[WorkflowRouter] Revision triggered (Attempt {state.revision_count} of {state.max_revisions}). "
            f"Returning to Synthesizer with Critic feedback."
        )
        return state

    def resolution_node(state: WorkflowState) -> WorkflowState:
        return resolution.run(state, db_session=db_session)

    # 2. Define Conditional Router
    def route_critic_decision(state: WorkflowState) -> Literal["revision_prep", "resolution"]:
        critic_out = state.critic_output
        if not critic_out:
            return "resolution"

        if critic_out.requires_revision and state.revision_count < state.max_revisions:
            return "revision_prep"

        return "resolution"

    # 3. Assemble Graph
    builder = StateGraph(WorkflowState)

    builder.add_node("retriever", retriever_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("revision_prep", revision_prep_node)
    builder.add_node("resolution", resolution_node)

    # Set entry point
    builder.set_entry_point("retriever")

    # Connect nodes
    builder.add_edge("retriever", "synthesizer")
    builder.add_edge("synthesizer", "critic")

    builder.add_conditional_edges(
        "critic",
        route_critic_decision,
        {
            "revision_prep": "revision_prep",
            "resolution": "resolution",
        },
    )

    builder.add_edge("revision_prep", "synthesizer")
    builder.add_edge("resolution", END)

    return builder.compile()


def run_qa_workflow(
    question: str,
    db_session=None,
    max_revisions: int = 2,
) -> WorkflowState:
    """
    Executes the multi-agent question answering graph.
    Measures latency, updates SQLite records, and logs audit events.
    """
    session_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    initial_state = WorkflowState(
        question=question,
        session_id=session_id,
        max_revisions=max_revisions,
        workflow_log=[f"[System] Initiating TruthGuard verification graph for session '{session_id[:8]}'"],
    )

    graph = create_qa_graph(db_session=db_session)

    try:
        final_dict_or_state = graph.invoke(initial_state)
        # LangGraph may return state as dict or WorkflowState object
        if isinstance(final_dict_or_state, dict):
            final_state = WorkflowState(**final_dict_or_state)
        else:
            final_state = final_dict_or_state
    except Exception as exc:
        logger.exception("Error executing QA graph: %s", exc)
        initial_state.error = str(exc)
        final_state = initial_state

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    final_state.workflow_log.append(f"[System] Execution finished in {elapsed_ms} ms.")

    # Persist QASession in SQLite if db_session is provided
    if db_session and final_state.resolution_output:
        res = final_state.resolution_output
        qa_data = {
            "question": question,
            "draft_answer": final_state.synthesizer_output.draft_answer if final_state.synthesizer_output else "",
            "final_answer": res.final_answer,
            "verification_status": res.status.value,
            "revision_count": final_state.revision_count,
            "escalated": (res.status == VerificationStatus.HUMAN_REVIEW_REQUIRED),
            "latency_ms": elapsed_ms,
            "citations": [c.model_dump() for c in res.citations],
            "critic_report": final_state.critic_output.model_dump() if final_state.critic_output else {},
            "retrieval_results": [s.model_dump() for s in final_state.retriever_output.sources] if final_state.retriever_output else [],
        }
        try:
            qa_session_record = repository.create_qa_session(db_session, qa_data)
            final_state.db_session_id = str(qa_session_record.id)
            if res.status == VerificationStatus.ABSTAINED:
                AuditService.log_abstention(str(qa_session_record.id), res.abstention_reason or "Unknown", db_session)
            else:
                AuditService.log_question_answered(str(qa_session_record.id), res.status.value, db_session)
            db_session.commit()
        except Exception as e:
            logger.warning("Failed to persist QASession: %s", e)
            try:
                db_session.rollback()
            except Exception:
                pass

    return final_state
