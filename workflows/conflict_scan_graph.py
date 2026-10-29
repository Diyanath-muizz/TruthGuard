"""
workflows/conflict_scan_graph.py
────────────────────────────────
Proactive conflict scanning graph workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from database.models import ConflictReport
from services.conflict_service import ConflictService

logger = logging.getLogger(__name__)


class ConflictScanWorkflow:
    """
    Coordinates multi-step proactive conflict scanning for a given document.
    """

    @classmethod
    def run(cls, doc_id: int, db_session) -> List[ConflictReport]:
        return ConflictService.scan_new_document(doc_id, db_session)
