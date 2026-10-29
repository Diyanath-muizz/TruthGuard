"""
verification/staleness_checker.py
─────────────────────────────────
Staleness, expiration, and temporal validity detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StalenessResult:
    """
    Result of evaluating document temporal and supersession status.
    """
    is_stale: bool
    reason: str
    severity: str  # "critical", "warning", "info", "none"
    outdated_since: Optional[str] = None
    is_future_dated: bool = False
    is_superseded: bool = False
    is_expired: bool = False


class StalenessChecker:
    """
    Checks documents and passages for expiration, future effective dates,
    revocation, and supersession staleness.
    """

    @staticmethod
    def check_staleness(
        doc_metadata: Dict[str, Any],
        reference_date: Optional[str] = None,
    ) -> StalenessResult:
        """
        Evaluates doc_metadata against reference_date (defaults to today in UTC YYYY-MM-DD).
        """
        if not reference_date:
            reference_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        status = (doc_metadata.get("status") or "active").lower()
        if status == "superseded":
            return StalenessResult(
                is_stale=True,
                reason="Document is explicitly marked as superseded.",
                severity="critical",
                is_superseded=True,
            )
        if status == "revoked":
            return StalenessResult(
                is_stale=True,
                reason="Document has been formally revoked.",
                severity="critical",
            )
        if status == "expired":
            return StalenessResult(
                is_stale=True,
                reason="Document has expired.",
                severity="critical",
                is_expired=True,
            )

        exp_date = doc_metadata.get("expiration_date")
        if exp_date and exp_date.strip():
            if exp_date < reference_date:
                return StalenessResult(
                    is_stale=True,
                    reason=f"Document expired on {exp_date} (reference date: {reference_date}).",
                    severity="critical",
                    outdated_since=exp_date,
                    is_expired=True,
                )

        eff_date = doc_metadata.get("effective_date")
        if eff_date and eff_date.strip():
            if eff_date > reference_date:
                return StalenessResult(
                    is_stale=False,
                    reason=f"Document is not yet effective; effective date is in the future ({eff_date}).",
                    severity="warning",
                    is_future_dated=True,
                )

        return StalenessResult(
            is_stale=False,
            reason="Document is currently active and within valid dates.",
            severity="none",
        )

    @staticmethod
    def check_faq_vs_amendment(
        faq_meta: Dict[str, Any],
        amendment_meta: Dict[str, Any],
    ) -> bool:
        """
        Returns True if the FAQ is older than or superseded by the Amendment.
        """
        faq_date = faq_meta.get("publication_date") or faq_meta.get("effective_date") or ""
        amend_date = amendment_meta.get("effective_date") or amendment_meta.get("publication_date") or ""

        if faq_date and amend_date:
            return faq_date < amend_date
        return True  # By authority hierarchy, amendment supersedes FAQ on conflicting policy
