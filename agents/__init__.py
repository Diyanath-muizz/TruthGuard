"""
agents/__init__.py
──────────────────
Shared Pydantic v2 schemas for TruthGuard multi-agent pipeline.

All agents import their data models from this module so there is a single
source of truth for the inter-agent contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    VERIFIED_WITH_WARNINGS = "verified_with_warnings"
    CONFLICT_DETECTED = "conflict_detected"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    ABSTAINED = "abstained"
    PENDING = "pending"


# ─────────────────────────────────────────────────────────────────────────────
# Core data objects
# ─────────────────────────────────────────────────────────────────────────────


class DocumentSource(BaseModel):
    """A single retrieved passage together with its provenance metadata."""

    doc_id: str
    filename: str
    doc_type: str
    version: Optional[str] = None
    effective_date: Optional[str] = None
    authority_level: int = 1
    chunk_id: str
    passage_text: str
    page_number: Optional[int] = None
    rrf_score: float = 0.0
    is_superseded: bool = False
    superseded_by: Optional[str] = None


class FactualClaim(BaseModel):
    """A single factual assertion extracted from the synthesised draft answer."""

    claim_id: str
    claim_text: str
    supporting_sources: List[DocumentSource] = []
    conflicting_sources: List[DocumentSource] = []
    # "certain" | "probable" | "uncertain" | "conflicted"
    confidence: str = "uncertain"
    is_supported: bool = False


class Citation(BaseModel):
    """A citable reference to a specific passage inside a document."""

    doc_id: str
    filename: str
    chunk_id: str
    page_number: Optional[int] = None
    version: Optional[str] = None
    effective_date: Optional[str] = None
    passage_text: str
    authority_level: int = 1
    doc_type: str


class ConflictDetail(BaseModel):
    """Detailed description of a conflict found between two documents."""

    conflict_type: str
    doc_a_id: str
    doc_b_id: str
    passage_a: str
    passage_b: str
    description: str
    # "confirmed" | "potential" | "warning"
    severity: str


# ─────────────────────────────────────────────────────────────────────────────
# Agent outputs
# ─────────────────────────────────────────────────────────────────────────────


class RetrieverOutput(BaseModel):
    """Output produced by RetrieverAgent."""

    question: str
    sources: List[DocumentSource] = []
    potential_conflicts: List[ConflictDetail] = []
    retrieval_metadata: Dict[str, Any] = {}


class SynthesizerOutput(BaseModel):
    """Output produced by SynthesizerAgent."""

    question: str
    draft_answer: str
    factual_claims: List[FactualClaim] = []
    supporting_citations: List[Citation] = []
    conflicting_evidence: List[ConflictDetail] = []
    missing_evidence: List[str] = []
    uncertainty_notes: List[str] = []
    sources_used: List[DocumentSource] = []


class CriticFinding(BaseModel):
    """A single finding raised by the CriticAgent."""

    # "contradiction" | "staleness" | "unsupported_claim"
    # | "authority_violation" | "citation_error"
    finding_type: str
    description: str
    affected_claims: List[str] = []
    # "critical" | "warning" | "info"
    severity: str
    recommendation: str


class CriticOutput(BaseModel):
    """Output produced by CriticAgent."""

    passes_verification: bool
    # "high" | "medium" | "low" | "none"
    overall_confidence: str
    contradictions: List[CriticFinding] = []
    staleness_warnings: List[CriticFinding] = []
    unsupported_claims: List[CriticFinding] = []
    citation_errors: List[CriticFinding] = []
    authority_issues: List[CriticFinding] = []
    all_findings: List[CriticFinding] = []
    requires_revision: bool = False
    requires_human_escalation: bool = False
    revision_suggestions: List[str] = []
    verification_summary: str = ""


class ResolutionOutput(BaseModel):
    """Final output produced by ResolutionAgent."""

    status: VerificationStatus
    final_answer: str
    citations: List[Citation] = []
    trust_explanation: str = ""
    conflicting_sources: List[DocumentSource] = []
    outdated_sources: List[DocumentSource] = []
    abstention_reason: Optional[str] = None
    escalation_reason: Optional[str] = None
    human_review_created: bool = False
    human_review_id: Optional[str] = None
    revision_count: int = 0
    agents_run: List[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph shared state
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowState(BaseModel):
    """
    State object that flows through every node of the LangGraph pipeline.

    Each agent receives this object, enriches its designated output field,
    appends a log entry to ``workflow_log``, and returns the mutated state.
    """

    question: str
    session_id: str = ""

    retriever_output: Optional[RetrieverOutput] = None
    synthesizer_output: Optional[SynthesizerOutput] = None
    critic_output: Optional[CriticOutput] = None
    resolution_output: Optional[ResolutionOutput] = None

    revision_count: int = 0
    max_revisions: int = 2

    error: Optional[str] = None
    workflow_log: List[str] = []

    # Populated when the QASession row is created in SQLite
    db_session_id: Optional[str] = None
