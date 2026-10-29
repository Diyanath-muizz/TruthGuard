"""
verification/contradiction_detector.py
────────────────────────────────────────
Detects numeric and semantic contradictions between retrieved passages.

Strategy
--------
1. Extract all numeric values (integers, floats, percentages, currency
   amounts) from each passage using a single regex.
2. Group passages by the document they belong to.
3. For every pair of documents that share at least one numeric pattern
   but disagree on the value → flag as a potential contradiction.
4. Additionally flag passages where explicit negation is present on the
   same topic keyword (simple heuristic for non-numeric contradictions).
"""

from __future__ import annotations

import logging
import re
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Regex that captures: integers, decimals, percentages, currency amounts
_NUM_PATTERN = re.compile(
    r"""
    (?:
        \$?                      # optional leading dollar sign
        \d{1,3}(?:,\d{3})*      # thousands-separated integer part
        (?:\.\d+)?               # optional decimal part
        \s*%?                    # optional trailing percent
    )
    """,
    re.VERBOSE,
)

# Negation words that can flip a statement
_NEGATION_WORDS = {"not", "no", "never", "cannot", "can't", "ineligible", "excluded"}


def _extract_numbers(text: str) -> Set[str]:
    """Return a set of normalised number strings found in *text*."""
    raw = _NUM_PATTERN.findall(text)
    return {r.strip().replace(",", "") for r in raw if r.strip() and r.strip() not in {"", "."}}


def _has_negation(text: str) -> bool:
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    return bool(tokens & _NEGATION_WORDS)


class ContradictionDetector:
    """
    Stateless helper used by RetrieverAgent and CriticAgent to surface
    potential numeric or semantic contradictions across retrieved passages.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_conflicts(
        self,
        sources: List,  # List[DocumentSource]
    ) -> List:           # List[ConflictDetail]
        """
        Compare all pairs of sources and return a list of ConflictDetail
        objects for every detected contradiction.

        Parameters
        ----------
        sources:
            List of ``DocumentSource`` objects from the retriever.
        """
        from agents import ConflictDetail  # lazy to avoid circular imports

        if len(sources) < 2:
            return []

        conflicts: List[ConflictDetail] = []
        seen_pairs: Set[Tuple[str, str]] = set()

        for src_a, src_b in combinations(sources, 2):
            if src_a.doc_id == src_b.doc_id:
                continue
            pair_key = tuple(sorted([src_a.chunk_id, src_b.chunk_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            conflict = self._compare(src_a, src_b)
            if conflict:
                conflicts.append(conflict)

        return conflicts

    def check_claim_against_sources(
        self,
        claim_text: str,
        supporting_sources: List,
        all_retrieved_sources: List,
    ) -> Optional[object]:  # Optional[ConflictDetail]
        """
        Check whether any source in *all_retrieved_sources* contradicts the
        *claim_text* (which is already supported by *supporting_sources*).

        Returns a ConflictDetail if a contradiction is found, else None.
        """
        from agents import ConflictDetail

        claim_numbers = _extract_numbers(claim_text)
        claim_negated = _has_negation(claim_text)
        supporting_ids = {s.doc_id for s in supporting_sources}

        for src in all_retrieved_sources:
            if src.doc_id in supporting_ids:
                continue

            src_numbers = _extract_numbers(src.passage_text)

            # If the claim has numbers and the source has different numbers
            # for the same topic → contradiction
            if claim_numbers and src_numbers and not (claim_numbers & src_numbers):
                return ConflictDetail(
                    conflict_type="numerical",
                    doc_a_id="claim",
                    doc_b_id=src.doc_id,
                    passage_a=claim_text,
                    passage_b=src.passage_text,
                    description=(
                        f"Claim asserts value(s) {claim_numbers} but source "
                        f"'{src.filename}' asserts value(s) {src_numbers}."
                    ),
                    severity="potential",
                )

            # Negation flip heuristic
            src_negated = _has_negation(src.passage_text)
            if claim_negated != src_negated:
                return ConflictDetail(
                    conflict_type="negation",
                    doc_a_id="claim",
                    doc_b_id=src.doc_id,
                    passage_a=claim_text,
                    passage_b=src.passage_text,
                    description=(
                        "Claim and retrieved source appear to state opposite positions "
                        "(one uses negation, the other does not)."
                    ),
                    severity="potential",
                )

        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compare(self, src_a, src_b) -> Optional[object]:
        """Compare two DocumentSource objects and return a ConflictDetail or None."""
        from agents import ConflictDetail

        nums_a = _extract_numbers(src_a.passage_text)
        nums_b = _extract_numbers(src_b.passage_text)

        # --- Numeric conflict ---
        if nums_a and nums_b and not (nums_a & nums_b):
            severity = "confirmed" if (src_a.is_superseded or src_b.is_superseded) else "potential"
            return ConflictDetail(
                conflict_type="numerical",
                doc_a_id=src_a.doc_id,
                doc_b_id=src_b.doc_id,
                passage_a=src_a.passage_text,
                passage_b=src_b.passage_text,
                description=(
                    f"'{src_a.filename}' states value(s) {nums_a}, "
                    f"but '{src_b.filename}' states value(s) {nums_b}."
                ),
                severity=severity,
            )

        # --- Explicit supersession conflict ---
        if src_a.is_superseded and src_a.superseded_by == src_b.doc_id:
            return ConflictDetail(
                conflict_type="supersession",
                doc_a_id=src_a.doc_id,
                doc_b_id=src_b.doc_id,
                passage_a=src_a.passage_text,
                passage_b=src_b.passage_text,
                description=(
                    f"'{src_a.filename}' has been superseded by '{src_b.filename}'. "
                    "The older document's content may no longer be valid."
                ),
                severity="confirmed",
            )

        if src_b.is_superseded and src_b.superseded_by == src_a.doc_id:
            return ConflictDetail(
                conflict_type="supersession",
                doc_a_id=src_b.doc_id,
                doc_b_id=src_a.doc_id,
                passage_a=src_b.passage_text,
                passage_b=src_a.passage_text,
                description=(
                    f"'{src_b.filename}' has been superseded by '{src_a.filename}'. "
                    "The older document's content may no longer be valid."
                ),
                severity="confirmed",
            )

        # --- Authority-backed negation conflict ---
        neg_a = _has_negation(src_a.passage_text)
        neg_b = _has_negation(src_b.passage_text)
        if neg_a != neg_b:
            return ConflictDetail(
                conflict_type="negation",
                doc_a_id=src_a.doc_id,
                doc_b_id=src_b.doc_id,
                passage_a=src_a.passage_text,
                passage_b=src_b.passage_text,
                description=(
                    f"'{src_a.filename}' and '{src_b.filename}' appear to make "
                    "opposing statements (one uses negation, the other does not)."
                ),
                severity="potential",
            )

        return None
