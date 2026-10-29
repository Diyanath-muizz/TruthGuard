"""
verification/__init__.py
─────────────────────────
Exports all verification engines, detectors, and validators.
"""

from verification.contradiction_detector import ContradictionDetector
from verification.staleness_checker import StalenessChecker, StalenessResult
from verification.authority_rules import AuthorityRules, AuthorityDecision
from verification.citation_validator import CitationValidator, CitationValidationResult
from verification.trust_engine import TrustDecisionEngine, TrustDecision
from verification.supersession_graph import SupersessionGraph

__all__ = [
    "ContradictionDetector",
    "StalenessChecker",
    "StalenessResult",
    "AuthorityRules",
    "AuthorityDecision",
    "CitationValidator",
    "CitationValidationResult",
    "TrustDecisionEngine",
    "TrustDecision",
    "SupersessionGraph",
]
