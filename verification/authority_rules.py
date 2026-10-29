"""
verification/authority_rules.py
───────────────────────────────
Configurable authority rule engine for resolving document precedence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import AUTHORITY_HIERARCHY, settings

logger = logging.getLogger(__name__)


@dataclass
class AuthorityDecision:
    """
    Detailed, explainable decision on document authority and precedence.
    """
    preferred_doc_id: Optional[str]
    rejected_doc_id: Optional[str]
    reason: str
    confidence: str  # "high", "medium", "low", "none"
    factors_considered: List[str] = field(default_factory=list)
    winner_authority_level: int = 1
    loser_authority_level: int = 1
    is_explicit_supersession: bool = False
    is_irreconcilable: bool = False


class AuthorityRules:
    """
    Determines which document takes precedence between conflicting sources.
    Strictly avoids naive timestamp-only or embedding-similarity-only ranking.
    """

    @classmethod
    def get_authority_level(cls, doc_meta: Dict[str, Any]) -> int:
        if "authority_level" in doc_meta and doc_meta["authority_level"] is not None:
            return int(doc_meta["authority_level"])
        doc_type = doc_meta.get("doc_type", "Other")
        cleaned = doc_type.strip().capitalize()
        if cleaned.upper() == "FAQ":
            cleaned = "FAQ"
        return AUTHORITY_HIERARCHY.get(cleaned, settings.default_authority_level)

    @classmethod
    def compare_authority(
        cls,
        doc_a: Dict[str, Any],
        doc_b: Dict[str, Any],
        question_context: Optional[str] = None,
    ) -> AuthorityDecision:
        """
        Compares two conflicting documents and returns an explainable decision.
        """
        factors: List[str] = []
        id_a = str(doc_a.get("id", doc_a.get("doc_id", "A")))
        id_b = str(doc_b.get("id", doc_b.get("doc_id", "B")))
        title_a = doc_a.get("title") or doc_a.get("filename") or f"Doc {id_a}"
        title_b = doc_b.get("title") or doc_b.get("filename") or f"Doc {id_b}"

        # 1. Check revocation / expiration status
        status_a = (doc_a.get("status") or "active").lower()
        status_b = (doc_b.get("status") or "active").lower()

        if status_a in {"revoked", "expired"} and status_b not in {"revoked", "expired"}:
            factors.append(f"Doc {title_a} is {status_a}")
            return AuthorityDecision(
                preferred_doc_id=id_b,
                rejected_doc_id=id_a,
                reason=f"{title_b} is preferred because {title_a} is {status_a}.",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=cls.get_authority_level(doc_b),
                loser_authority_level=cls.get_authority_level(doc_a),
            )
        if status_b in {"revoked", "expired"} and status_a not in {"revoked", "expired"}:
            factors.append(f"Doc {title_b} is {status_b}")
            return AuthorityDecision(
                preferred_doc_id=id_a,
                rejected_doc_id=id_b,
                reason=f"{title_a} is preferred because {title_b} is {status_b}.",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=cls.get_authority_level(doc_a),
                loser_authority_level=cls.get_authority_level(doc_b),
            )

        # 2. Check explicit supersession
        supersedes_a = (doc_a.get("supersedes") or "").lower()
        supersedes_b = (doc_b.get("supersedes") or "").lower()

        target_b_names = [title_b.lower(), (doc_b.get("filename") or "").lower()]
        target_a_names = [title_a.lower(), (doc_a.get("filename") or "").lower()]

        if supersedes_a and any(name in supersedes_a for name in target_b_names if name):
            factors.append(f"{title_a} explicitly supersedes {title_b}")
            return AuthorityDecision(
                preferred_doc_id=id_a,
                rejected_doc_id=id_b,
                reason=f"{title_a} is formally designated to supersede {title_b}.",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=cls.get_authority_level(doc_a),
                loser_authority_level=cls.get_authority_level(doc_b),
                is_explicit_supersession=True,
            )

        if supersedes_b and any(name in supersedes_b for name in target_a_names if name):
            factors.append(f"{title_b} explicitly supersedes {title_a}")
            return AuthorityDecision(
                preferred_doc_id=id_b,
                rejected_doc_id=id_a,
                reason=f"{title_b} is formally designated to supersede {title_a}.",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=cls.get_authority_level(doc_b),
                loser_authority_level=cls.get_authority_level(doc_a),
                is_explicit_supersession=True,
            )

        # 3. Departmental scope check
        dept_a = (doc_a.get("department") or "All").lower()
        dept_b = (doc_b.get("department") or "All").lower()
        if dept_a != dept_b and dept_a != "all" and dept_b != "all":
            factors.append(f"Scope difference: {dept_a} vs {dept_b}")
            # Neither supersedes the other globally; scopes differ
            return AuthorityDecision(
                preferred_doc_id=None,
                rejected_doc_id=None,
                reason=f"Documents apply to different departmental scopes ({doc_a.get('department')} vs {doc_b.get('department')}). Scope-specific context is required.",
                confidence="medium",
                factors_considered=factors,
                is_irreconcilable=True,
            )

        # 4. Compare hierarchical authority level
        auth_a = cls.get_authority_level(doc_a)
        auth_b = cls.get_authority_level(doc_b)
        factors.append(f"Authority levels: {title_a}={auth_a}, {title_b}={auth_b}")

        if auth_a > auth_b:
            return AuthorityDecision(
                preferred_doc_id=id_a,
                rejected_doc_id=id_b,
                reason=f"{title_a} has higher institutional authority (level {auth_a}, {doc_a.get('doc_type')}) than {title_b} (level {auth_b}, {doc_b.get('doc_type')}).",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=auth_a,
                loser_authority_level=auth_b,
            )
        elif auth_b > auth_a:
            return AuthorityDecision(
                preferred_doc_id=id_b,
                rejected_doc_id=id_a,
                reason=f"{title_b} has higher institutional authority (level {auth_b}, {doc_b.get('doc_type')}) than {title_a} (level {auth_a}, {doc_a.get('doc_type')}).",
                confidence="high",
                factors_considered=factors,
                winner_authority_level=auth_b,
                loser_authority_level=auth_a,
            )

        # 5. Equal authority level: check effective dates if same lineage
        eff_a = doc_a.get("effective_date") or ""
        eff_b = doc_b.get("effective_date") or ""
        ver_a = doc_a.get("version") or ""
        ver_b = doc_b.get("version") or ""

        # If one document has a newer effective date and higher version of the same document lineage
        title_a_clean = title_a.lower().replace(ver_a.lower(), "").strip()
        title_b_clean = title_b.lower().replace(ver_b.lower(), "").strip()

        is_same_lineage = title_a_clean and (title_a_clean in title_b_clean or title_b_clean in title_a_clean)

        if is_same_lineage and eff_a and eff_b and eff_a != eff_b:
            if eff_a > eff_b:
                factors.append(f"Same lineage with newer effective date: {eff_a} vs {eff_b}")
                return AuthorityDecision(
                    preferred_doc_id=id_a,
                    rejected_doc_id=id_b,
                    reason=f"{title_a} is a newer effective version ({eff_a}) of the same policy lineage compared to {title_b} ({eff_b}).",
                    confidence="medium",
                    factors_considered=factors,
                    winner_authority_level=auth_a,
                    loser_authority_level=auth_b,
                )
            else:
                factors.append(f"Same lineage with newer effective date: {eff_b} vs {eff_a}")
                return AuthorityDecision(
                    preferred_doc_id=id_b,
                    rejected_doc_id=id_a,
                    reason=f"{title_b} is a newer effective version ({eff_b}) of the same policy lineage compared to {title_a} ({eff_a}).",
                    confidence="medium",
                    factors_considered=factors,
                    winner_authority_level=auth_b,
                    loser_authority_level=auth_a,
                )

        # Equal authority and cannot determine precedence! Irreconcilable conflict.
        factors.append("Equal authority with contradictory policy statements and no explicit supersession.")
        return AuthorityDecision(
            preferred_doc_id=None,
            rejected_doc_id=None,
            reason=f"Both {title_a} and {title_b} hold equal authority ({doc_a.get('doc_type')}, level {auth_a}) with contradictory positions and no formal supersession established.",
            confidence="none",
            factors_considered=factors,
            winner_authority_level=auth_a,
            loser_authority_level=auth_b,
            is_irreconcilable=True,
        )
