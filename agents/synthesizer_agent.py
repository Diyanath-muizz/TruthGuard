"""
agents/synthesizer_agent.py
───────────────────────────
Synthesizer Agent for TruthGuard.
Drafts an initial grounded answer, decomposes the answer into atomic factual claims,
maps claims to citations, and isolates contradictions without blending conflicting values.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agents import (
    Citation,
    ConflictDetail,
    DocumentSource,
    FactualClaim,
    SynthesizerOutput,
    WorkflowState,
)
from config.settings import settings
from services.llm_service import call_llm

logger = logging.getLogger(__name__)


class SynthesizerAgent:
    """
    Agent responsible for drafting evidence-grounded answers.
    Never blends contradictory policy values into misleading compromises.
    """

    def run(self, state: WorkflowState, db_session=None) -> WorkflowState:
        question = state.question
        retriever_out = state.retriever_output
        sources = retriever_out.sources if retriever_out else []

        log_prefix = f"[SynthesizerAgent (Pass {state.revision_count + 1})]"
        state.workflow_log.append(f"{log_prefix} Analyzing {len(sources)} retrieved passages.")

        if not sources:
            state.synthesizer_output = SynthesizerOutput(
                question=question,
                draft_answer="No relevant documents or policy statements were found to answer this question.",
                factual_claims=[],
                supporting_citations=[],
                conflicting_evidence=[],
                missing_evidence=["Corpus contains no relevant documents matching the question."],
                uncertainty_notes=["Complete absence of grounding evidence."],
                sources_used=[],
            )
            return state

        # If this is a revision loop, incorporate Critic feedback
        critic_guidance = ""
        if state.critic_output and state.critic_output.revision_suggestions:
            critic_guidance = (
                f"\nCRITIC FEEDBACK FROM PREVIOUS DRAFT:\n"
                + "\n".join(f"- {s}" for s in state.critic_output.revision_suggestions)
                + "\nPlease correct your answer to resolve these issues. Do not repeat the flagged errors."
            )

        if settings.llm_provider != "mock":
            output = self._run_llm_synthesis(question, sources, critic_guidance)
        else:
            output = self._run_deterministic_synthesis(question, sources, state.revision_count)

        state.synthesizer_output = output
        state.workflow_log.append(
            f"{log_prefix} Produced draft answer with {len(output.factual_claims)} claims "
            f"and {len(output.supporting_citations)} citations."
        )
        return state

    def _run_deterministic_synthesis(
        self,
        question: str,
        sources: List[DocumentSource],
        revision_count: int,
    ) -> SynthesizerOutput:
        """
        Deterministic, robust synthesis for mock mode and baseline testing.
        Identifies highest authority documents, detects conflicting numbers,
        and constructs transparent claims without hallucinating.
        """
        # Check topic grounding in retrieved passages
        stop_words = {"what", "when", "where", "which", "does", "have", "with", "from", "company", "policy", "limit", "amount", "many", "days", "employees", "entitled", "standard"}
        q_keywords = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", question.lower()) if w not in stop_words]
        corpus_text = " ".join(s.passage_text.lower() for s in sources)
        
        if q_keywords and not any(k in corpus_text for k in q_keywords):
            return SynthesizerOutput(
                question=question,
                draft_answer="The retrieved documents do not contain information regarding this topic.",
                factual_claims=[],
                supporting_citations=[],
                conflicting_evidence=[],
                missing_evidence=[f"No documentation found for: {', '.join(q_keywords)}"],
                uncertainty_notes=["Question topic is absent from the indexed corpus."],
                sources_used=[],
            )

        # Only consider sources relevant to this question's domain keywords
        domain_sources = [
            s for s in sources
            if any(k in (s.passage_text + " " + s.filename).lower() for k in q_keywords)
        ] if q_keywords else sources
        eval_sources = domain_sources if domain_sources else sources

        # Find explicit superseding amendment among relevant sources
        amendment = next((s for s in eval_sources if s.doc_type == "Amendment" and not s.is_superseded), None)
        active_policies = [s for s in eval_sources if s.doc_type in {"Policy", "Amendment"} and not s.is_superseded]
        all_faqs = [s for s in eval_sources if s.doc_type == "FAQ"]

        # Check for numeric mentions among relevant sources (ignoring years like 2023, 2024, 2025)
        values_found: Dict[str, List[DocumentSource]] = {}
        for s in eval_sources:
            nums = [n for n in re.findall(r"\b\d+(?:\.\d+)?\b", s.passage_text) if not (len(n) == 4 and n.startswith("20"))]
            for n in nums:
                if n not in values_found:
                    values_found[n] = []
                values_found[n].append(s)

        # Check if there are distinct numbers on the same topic
        has_numeric_conflict = len(values_found) > 1

        claims: List[FactualClaim] = []
        citations: List[Citation] = []
        conflicts: List[ConflictDetail] = []
        missing: List[str] = []
        uncertainties: List[str] = []

        # Case 1: An amendment exists that supersedes an older policy (Demo 1)
        if amendment:
            target_source = amendment
            draft_answer = (
                f"According to {amendment.filename} (effective {amendment.effective_date or 'currently'}), "
                f"{amendment.passage_text.strip()} This formally supersedes older policy versions."
            )
            claims.append(
                FactualClaim(
                    claim_id="claim-1",
                    claim_text=f"The current policy provision is defined by {amendment.filename}.",
                    supporting_sources=[amendment],
                    confidence="certain",
                    is_supported=True,
                )
            )
            citations.append(
                Citation(
                    doc_id=amendment.doc_id,
                    filename=amendment.filename,
                    chunk_id=amendment.chunk_id,
                    page_number=amendment.page_number,
                    version=amendment.version,
                    effective_date=amendment.effective_date,
                    passage_text=amendment.passage_text,
                    authority_level=amendment.authority_level,
                    doc_type=amendment.doc_type,
                )
            )
            # Mark conflicting older sources
            for s in sources:
                if s.doc_id != amendment.doc_id:
                    conflicts.append(
                        ConflictDetail(
                            conflict_type="superseded_amendment" if s.doc_type == "Policy" else "contradictory_faq",
                            doc_a_id=amendment.doc_id,
                            doc_b_id=s.doc_id,
                            passage_a=amendment.passage_text,
                            passage_b=s.passage_text,
                            description=f"Older source {s.filename} reflects prior terms superseded by {amendment.filename}.",
                            severity="warning",
                        )
                    )

        # Case 2: Conflicting documents of equal authority with no superseder (Demo 2)
        elif len(active_policies) >= 2 and has_numeric_conflict:
            doc_a = active_policies[0]
            doc_b = active_policies[1]
            draft_answer = (
                f"Conflicting policies exist regarding this matter. {doc_a.filename} states: "
                f"'{doc_a.passage_text.strip()}'. Conversely, {doc_b.filename} states: "
                f"'{doc_b.passage_text.strip()}'. Neither document formally supersedes the other."
            )
            uncertainties.append("Two documents of equal authority level make contradictory statements.")
            claims.append(
                FactualClaim(
                    claim_id="claim-1",
                    claim_text=f"Statement from {doc_a.filename}",
                    supporting_sources=[doc_a],
                    conflicting_sources=[doc_b],
                    confidence="conflicted",
                    is_supported=True,
                )
            )
            claims.append(
                FactualClaim(
                    claim_id="claim-2",
                    claim_text=f"Contradictory statement from {doc_b.filename}",
                    supporting_sources=[doc_b],
                    conflicting_sources=[doc_a],
                    confidence="conflicted",
                    is_supported=True,
                )
            )
            citations.extend([
                Citation(
                    doc_id=doc_a.doc_id,
                    filename=doc_a.filename,
                    chunk_id=doc_a.chunk_id,
                    page_number=doc_a.page_number,
                    version=doc_a.version,
                    effective_date=doc_a.effective_date,
                    passage_text=doc_a.passage_text,
                    authority_level=doc_a.authority_level,
                    doc_type=doc_a.doc_type,
                ),
                Citation(
                    doc_id=doc_b.doc_id,
                    filename=doc_b.filename,
                    chunk_id=doc_b.chunk_id,
                    page_number=doc_b.page_number,
                    version=doc_b.version,
                    effective_date=doc_b.effective_date,
                    passage_text=doc_b.passage_text,
                    authority_level=doc_b.authority_level,
                    doc_type=doc_b.doc_type,
                ),
            ])
            conflicts.append(
                ConflictDetail(
                    conflict_type="numerical" if has_numeric_conflict else "policy_mismatch",
                    doc_a_id=doc_a.doc_id,
                    doc_b_id=doc_b.doc_id,
                    passage_a=doc_a.passage_text,
                    passage_b=doc_b.passage_text,
                    description=f"Direct policy conflict between equal-authority documents {doc_a.filename} and {doc_b.filename}.",
                    severity="confirmed",
                )
            )

        # Case 3: Standard single or consensus source
        else:
            primary = sources[0]
            draft_answer = (
                f"Based on {primary.filename} (Version {primary.version or '1.0'}, {primary.doc_type}): "
                f"{primary.passage_text.strip()}"
            )
            claims.append(
                FactualClaim(
                    claim_id="claim-1",
                    claim_text=primary.passage_text.strip(),
                    supporting_sources=[primary],
                    confidence="certain",
                    is_supported=True,
                )
            )
            citations.append(
                Citation(
                    doc_id=primary.doc_id,
                    filename=primary.filename,
                    chunk_id=primary.chunk_id,
                    page_number=primary.page_number,
                    version=primary.version,
                    effective_date=primary.effective_date,
                    passage_text=primary.passage_text,
                    authority_level=primary.authority_level,
                    doc_type=primary.doc_type,
                )
            )

        return SynthesizerOutput(
            question=question,
            draft_answer=draft_answer,
            factual_claims=claims,
            supporting_citations=citations,
            conflicting_evidence=conflicts,
            missing_evidence=missing,
            uncertainty_notes=uncertainties,
            sources_used=sources,
        )

    def _run_llm_synthesis(
        self,
        question: str,
        sources: List[DocumentSource],
        critic_guidance: str,
    ) -> SynthesizerOutput:
        """
        Uses configured LLM with strict grounding instructions and JSON schema.
        """
        sources_text = "\n\n".join(
            f"SOURCE [{i+1}] (Doc ID: {s.doc_id}, File: {s.filename}, Type: {s.doc_type}, "
            f"Version: {s.version}, Effective: {s.effective_date}, Level: {s.authority_level}, "
            f"Chunk ID: {s.chunk_id}):\n{s.passage_text}"
            for i, s in enumerate(sources[:8])
        )

        system_prompt = (
            "You are TruthGuard's Synthesizer Agent. Your mandate is to draft a strictly evidence-grounded answer.\n"
            "CRITICAL RULES:\n"
            "1. NEVER blend contradictory values into a single compromise (e.g. NEVER say '12 to 15 days').\n"
            "2. If documents conflict, state the conflicting positions explicitly and cite both.\n"
            "3. Identify which source has higher authority or supersedes if specified in the text.\n"
            "4. Never invent policies, dates, numbers, or citations.\n"
            "5. Respond in valid JSON format with keys: 'draft_answer', 'claims' (list of text strings), "
            "'missing_evidence' (list of strings), 'uncertainty_notes' (list of strings)."
        )

        user_prompt = (
            f"QUESTION: {question}\n\n"
            f"RETRIEVED PASSAGES:\n{sources_text}\n"
            f"{critic_guidance}\n\n"
            f"Provide your structured synthesis in JSON format."
        )

        resp = call_llm(user_prompt, system_prompt=system_prompt)

        # Parse JSON from response
        try:
            # Extract json if wrapped in ```json
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", resp, re.DOTALL)
            raw_json = json_match.group(1) if json_match else resp
            data = json.loads(raw_json)
            draft_answer = data.get("draft_answer", resp)
            raw_claims = data.get("claims", [])
            missing = data.get("missing_evidence", [])
            uncertainties = data.get("uncertainty_notes", [])
        except Exception:
            draft_answer = resp
            raw_claims = [resp]
            missing = []
            uncertainties = []

        claims = []
        citations = []
        for i, c_text in enumerate(raw_claims):
            claims.append(
                FactualClaim(
                    claim_id=f"claim-{i+1}",
                    claim_text=str(c_text),
                    supporting_sources=sources[:1],
                    confidence="probable",
                    is_supported=True,
                )
            )

        for s in sources[:3]:
            citations.append(
                Citation(
                    doc_id=s.doc_id,
                    filename=s.filename,
                    chunk_id=s.chunk_id,
                    page_number=s.page_number,
                    version=s.version,
                    effective_date=s.effective_date,
                    passage_text=s.passage_text,
                    authority_level=s.authority_level,
                    doc_type=s.doc_type,
                )
            )

        return SynthesizerOutput(
            question=question,
            draft_answer=draft_answer,
            factual_claims=claims,
            supporting_citations=citations,
            conflicting_evidence=[],
            missing_evidence=missing,
            uncertainty_notes=uncertainties,
            sources_used=sources,
        )
