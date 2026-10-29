"""
services/question_service.py
────────────────────────────
High-level question answering service coordinating LangGraph execution
and session management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database import repository
from database.models import QASession
class QuestionService:
    """
    Coordinates asking questions, invoking LangGraph verification pipeline,
    and retrieving historical session queries.
    """

    @classmethod
    def answer_question(cls, question: str, db_session=None) -> Any:
        from workflows.question_answering_graph import run_qa_workflow
        return run_qa_workflow(question=question, db_session=db_session)

    @classmethod
    def get_session_history(cls, db_session, limit: int = 50) -> List[QASession]:
        if not db_session:
            return []
        return repository.get_qa_sessions(db_session, limit=limit)
