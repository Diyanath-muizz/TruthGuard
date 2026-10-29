"""
ui/__init__.py
──────────────
Streamlit UI pages for TruthGuard.
"""

from ui.dashboard import render_dashboard
from ui.document_management import render_document_management
from ui.chat import render_chat
from ui.conflict_explorer import render_conflict_explorer
from ui.admin_review import render_admin_review
from ui.evaluation import render_evaluation

__all__ = [
    "render_dashboard",
    "render_document_management",
    "render_chat",
    "render_conflict_explorer",
    "render_admin_review",
    "render_evaluation",
]
