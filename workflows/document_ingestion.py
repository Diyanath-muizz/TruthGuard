"""
workflows/document_ingestion.py
───────────────────────────────
Workflow for end-to-end document ingestion, validation, and proactive conflict analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.document_service import DocumentService, ProcessResult

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """
    Structured outcome of the document ingestion workflow.
    """
    success: bool
    doc_id: Optional[int]
    filename: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    steps_completed: List[str] = field(default_factory=list)
    chunk_count: int = 0
    conflict_count: int = 0


class DocumentIngestionWorkflow:
    """
    Orchestrates the steps of ingesting a document into TruthGuard.
    """

    def __init__(self) -> None:
        self.doc_service = DocumentService()

    def run(
        self,
        file_bytes: bytes,
        filename: str,
        user_metadata: Optional[Dict[str, Any]] = None,
        db_session=None,
    ) -> IngestionResult:
        steps = [
            "1. File validation & format check",
            "2. Text extraction & document parsing",
            "3. Metadata validation & extraction",
            "4. Content hashing & duplicate check",
            "5. Text chunking & provenance mapping",
            "6. Dense embedding & ChromaDB indexing",
            "7. BM25 sparse index update",
            "8. Relational database persistence",
            "9. Proactive conflict scanning",
            "10. Version & supersession relationship analysis",
        ]

        res: ProcessResult = self.doc_service.process_upload(
            file_bytes=file_bytes,
            filename=filename,
            user_metadata=user_metadata,
            db_session=db_session,
        )

        return IngestionResult(
            success=res.success,
            doc_id=res.doc_id,
            filename=filename,
            warnings=res.warnings,
            errors=res.errors,
            steps_completed=steps if res.success else steps[:2],
            chunk_count=res.chunk_count,
            conflict_count=res.conflict_count,
        )
