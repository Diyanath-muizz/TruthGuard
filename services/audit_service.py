"""
services/audit_service.py
-------------------------
Append-only audit logging service for TruthGuard.
All methods are static and write AuditEvent rows via SQLAlchemy session.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.models import AuditEvent

logger = logging.getLogger(__name__)


class AuditService:
    """Append-only audit logging service.

    All methods are static; callers are responsible for providing an active
    SQLAlchemy *db_session*.  Each method creates an :class:`AuditEvent`,
    persists it, and returns the committed instance.
    """

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    @staticmethod
    def _commit(event: AuditEvent, db_session: Any) -> AuditEvent:
        """Add *event* to *db_session* and commit, re-raising on failure."""
        try:
            db_session.add(event)
            db_session.commit()
            db_session.refresh(event)
            return event
        except Exception:
            logger.exception(
                "Failed to persist AuditEvent(event_type=%s, entity_id=%s)",
                event.event_type,
                event.entity_id,
            )
            db_session.rollback()
            raise

    # ------------------------------------------------------------------
    # Document lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def log_upload(doc_id: str, filename: str, db_session: Any) -> AuditEvent:
        """Record that a document was uploaded."""
        event = AuditEvent(
            event_type="document_uploaded",
            entity_type="document",
            entity_id=doc_id,
            description=f"Document '{filename}' uploaded (id={doc_id})",
            event_metadata={"filename": filename},
        )
        return AuditService._commit(event, db_session)

    @staticmethod
    def log_delete(doc_id: str, filename: str, db_session: Any) -> AuditEvent:
        """Record that a document was deleted."""
        event = AuditEvent(
            event_type="document_deleted",
            entity_type="document",
            entity_id=doc_id,
            description=f"Document '{filename}' deleted (id={doc_id})",
        )
        return AuditService._commit(event, db_session)

    @staticmethod
    def log_metadata_update(
        doc_id: str, changes: Dict[str, Any], db_session: Any
    ) -> AuditEvent:
        """Record that document metadata was updated."""
        event = AuditEvent(
            event_type="metadata_updated",
            entity_type="document",
            entity_id=doc_id,
            description=f"Metadata updated for document id={doc_id}",
            event_metadata={"changes": changes},
        )
        return AuditService._commit(event, db_session)

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    @staticmethod
    def log_conflict_detected(
        report_id: str, conflict_type: str, db_session: Any
    ) -> AuditEvent:
        """Record that a conflict was detected."""
        event = AuditEvent(
            event_type="conflict_detected",
            entity_type="conflict",
            entity_id=str(report_id),
            description=(
                f"Conflict detected: type={conflict_type}, report_id={report_id}"
            ),
        )
        return AuditService._commit(event, db_session)

    # ------------------------------------------------------------------
    # Question-answering
    # ------------------------------------------------------------------

    @staticmethod
    def log_question_answered(
        session_id: str, status: str, db_session: Any
    ) -> AuditEvent:
        """Record that a question was answered."""
        event = AuditEvent(
            event_type="qa_answered",
            entity_type="qa_session",
            entity_id=str(session_id),
            description=(
                f"Question answered with status={status} (session_id={session_id})"
            ),
        )
        return AuditService._commit(event, db_session)

    @staticmethod
    def log_abstention(
        session_id: str, reason: str, db_session: Any
    ) -> AuditEvent:
        """Record that the system abstained from answering a question."""
        event = AuditEvent(
            event_type="qa_abstained",
            entity_type="qa_session",
            entity_id=str(session_id),
            description=(
                f"System abstained from answering (session_id={session_id}): {reason}"
            ),
        )
        return AuditService._commit(event, db_session)

    # ------------------------------------------------------------------
    # Human review
    # ------------------------------------------------------------------

    @staticmethod
    def log_human_review_created(
        review_id: str, reason: str, db_session: Any
    ) -> AuditEvent:
        """Record that a human review case was created."""
        event = AuditEvent(
            event_type="review_escalated",
            entity_type="review",
            entity_id=str(review_id),
            description=f"Human review case created (id={review_id}): {reason}",
        )
        return AuditService._commit(event, db_session)

    @staticmethod
    def log_human_review_resolved(
        review_id: str, resolved_by: str, db_session: Any
    ) -> AuditEvent:
        """Record that a human review case was resolved."""
        event = AuditEvent(
            event_type="review_resolved",
            entity_type="review",
            entity_id=str(review_id),
            description=(
                f"Human review case resolved (id={review_id}) by {resolved_by}"
            ),
        )
        return AuditService._commit(event, db_session)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_recent_events(db_session: Any, limit: int = 100) -> List[AuditEvent]:
        """Return the most recent *limit* audit events, newest first."""
        try:
            return (
                db_session.query(AuditEvent)
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
                .all()
            )
        except Exception:
            logger.exception("Failed to retrieve recent AuditEvents (limit=%d)", limit)
            raise
