"""
workflows/__init__.py
─────────────────────
Exports LangGraph and ingestion workflows.
"""

from workflows.question_answering_graph import create_qa_graph, run_qa_workflow
from workflows.document_ingestion import DocumentIngestionWorkflow, IngestionResult
from workflows.conflict_scan_graph import ConflictScanWorkflow

__all__ = [
    "create_qa_graph",
    "run_qa_workflow",
    "DocumentIngestionWorkflow",
    "IngestionResult",
    "ConflictScanWorkflow",
]
