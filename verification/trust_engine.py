"""
verification/trust_engine.py
────────────────────────────
Explainable trust decision engine. Computes grounded source priority
and explicit rationale without conflating embedding similarity with authority.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents import DocumentSource
from verification.authority_rules import AuthorityRules
from verification.staleness_checker import StalenessChecker

logger = logging.getLogger(__name__)


@dataclass
class TrustDecision:
    """
    Transparent outcome explaining which document was preferred and why.
    """
    primary_source_id: Optional[str]
    primary_source_title: str
    explanation: str
    ranked_sources: List[Dict[str, Any]] = field(default_factory=list)
    rejected_sources: List[Dict[str, Any]] = field(default_factory=list)
    uncertainty_flags: List[str] = field(default_factory=list)
    requires_human_review: bool = False
    confidence: str = "high"


class TrustDecisionEngine:
    """
    Evaluates retrieved sources using institutional authority, supersession,
    and temporal validity rules.
    """

    @classmethod
    def decide(
        cls,
        sources: List[DocumentSource],
        question: str,
        db_session=None,
    ) -> TrustDecision:
        if not sources:
            return TrustDecision(
                primary_source_id=None,
                primary_source_title="None",
                explanation="No relevant sources were retrieved to ground an answer.",
                uncertainty_flags=["Insufficient evidence"],
                requires_human_review=False,
                confidence="none",
            )

        # Deduplicate sources by doc_id
        unique_docs: Dict[str, DocumentSource] = {}
        for s in sources:
            if s.doc_id not in unique_docs:
                unique_docs[s.doc_id] = s

        doc_list = list(unique_docs.values())
        if len(doc_list) == 1:
            s = doc_list[0]
            st = StalenessChecker.check_staleness({
                "status": "superseded" if s.is_superseded else "active",
                "effective_date": s.effective_date,
            })
            if st.is_stale:
                return TrustDecision(
                    primary_source_id=s.doc_id,
                    primary_source_title=s.filename,
                    explanation=f"Source {s.filename} was retrieved, but it is stale: {st.reason}",
                    uncertainty_flags=[st.reason],
                    requires_human_review=True,
                    confidence="low",
                )
            return TrustDecision(
                primary_source_id=s.doc_id,
                primary_source_title=s.filename,
                explanation=f"Single source retrieved: {s.filename} (Type: {s.doc_type}, Level {s.authority_level}).",
                ranked_sources=[{"doc_id": s.doc_id, "filename": s.filename, "score": 100}],
                confidence="high",
            )

        # Multi-document trust evaluation
        ranked = []
        rejected = []
        uncertainties = []
        requires_review = False

        # Compare pair-wise
        # Check if there is an explicit superseder
        superseder = None
        for s in doc_list:
            if s.doc_type == "Amendment" and not s.is_superseded:
                superseder = s
                break

        if superseder:
            primary = superseder
            explanation = (
                f"{primary.filename} was selected because it is a formally identified {primary.doc_type} "
                f"(Authority Level {primary.authority_level}), is effective, and supersedes older policies."
            )
            for s in doc_list:
                if s.doc_id != primary.doc_id:
                    rejected.append({
                        "doc_id": s.doc_id,
                        "filename": s.filename,
                        "reason": f"Superseded or outdated by {primary.filename}",
                    })
        else:
            # Sort by authority level descending, then effective date
            sorted_docs = sorted(
                doc_list,
                key=lambda x: (x.authority_level, x.effective_date or ""),
                reverse=True,
            )
            top = sorted_docs[0]
            runner_up = sorted_docs[1]

            # Check if top two conflict with equal authority
            if top.authority_level == runner_up.authority_level and top.doc_id != runner_up.doc_id:
                requires_review = True
                uncertainties.append(
                    f"Conflicting sources {top.filename} and {runner_up.filename} hold equal authority level ({top.authority_level})."
                )
                explanation = (
                    f"Authority could not be definitively established between {top.filename} and {runner_up.filename} "
                    f"because both have equal authority level ({top.authority_level}) with contradictory statements."
                )
                primary = top
            else:
                primary = top
                explanation = (
                    f"{primary.filename} was prioritized based on highest institutional authority "
                    f"(Level {primary.authority_level}, {primary.doc_type})."
                )
                for s in sorted_docs[1:]:
                    rejected.append({
                        "doc_id": s.doc_id,
                        "filename": s.filename,
                        "reason": f"Lower authority level ({s.authority_level}) compared to {primary.filename}",
                    })

        return TrustDecision(
            primary_source_id=primary.doc_id,
            primary_source_title=primary.filename,
            explanation=explanation,
            ranked_sources=[{"doc_id": s.doc_id, "filename": s.filename} for s in doc_list],
            rejected_sources=rejected,
            uncertainty_flags=uncertainties,
            requires_human_review=requires_review,
            confidence="low" if requires_review else "high",
        )

    @classmethod
    def format_trust_explanation(cls, decision: TrustDecision) -> str:
        lines = [decision.explanation]
        if decision.rejected_sources:
            lines.append("\n**Outdated or Rejected Sources:**")
            for r in decision.rejected_sources:
                lines.append(f"- **{r['filename']}**: {r['reason']}")
        if decision.uncertainty_flags:
            lines.append("\n**Uncertainty / Warnings:**")
            for u in decision.uncertainty_flags:
                lines.append(f"- ⚠️ {u}")
        return "\n".join(lines)
