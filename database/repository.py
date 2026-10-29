"""
database/repository.py
──────────────────────
Repository layer for TruthGuard – thin, typed wrappers around SQLAlchemy
queries.  All functions accept an open ``Session`` so callers control
transaction boundaries via ``get_db()``.

Usage::

    from database.initialization import get_db
    from database import repository as repo

    with get_db() as session:
        doc = repo.create_document(session, {...})
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    AuditEvent,
    ConflictReport,
    Document,
    DocumentChunk,
    DocumentRelationship,
    HumanReviewCase,
    QASession,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────


def _apply_updates(obj: Any, updates: Dict[str, Any]) -> None:
    """Apply a dict of field→value updates to an ORM object in place."""
    for key, value in updates.items():
        if hasattr(obj, key):
            setattr(obj, key, value)
        else:
            logger.warning("Ignoring unknown field '%s' on %s", key, type(obj).__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Document CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_document(session: Session, doc_data: Dict[str, Any]) -> Document:
    """
    Persist a new Document row and return it.

    ``doc_data`` should contain the column values to set.  Unknown keys are
    ignored with a warning.
    """
    doc = Document()
    _apply_updates(doc, doc_data)
    session.add(doc)
    session.flush()  # obtain the auto-generated id without committing
    logger.debug("Created Document id=%s filename=%s", doc.id, doc.filename)
    return doc


def get_document(session: Session, doc_id: int) -> Optional[Document]:
    """Return a Document by primary key, or None if not found."""
    return session.get(Document, doc_id)


def get_document_by_hash(session: Session, content_hash: str) -> Optional[Document]:
    """Return a Document by its content_hash, or None if not found."""
    stmt = select(Document).where(Document.content_hash == content_hash)
    return session.scalars(stmt).first()


def get_all_documents(session: Session) -> List[Document]:
    """Return all documents ordered by upload_timestamp descending."""
    stmt = select(Document).order_by(Document.upload_timestamp.desc())
    return list(session.scalars(stmt).all())


def update_document(session: Session, doc_id: int, updates: Dict[str, Any]) -> Document:
    """
    Apply ``updates`` to the Document with ``doc_id`` and return it.

    Raises ``ValueError`` if the document does not exist.
    """
    doc = get_document(session, doc_id)
    if doc is None:
        raise ValueError(f"Document id={doc_id} not found.")
    _apply_updates(doc, updates)
    session.flush()
    return doc


def delete_document(session: Session, doc_id: int) -> bool:
    """
    Delete the document and all cascade-deleted children (chunks, relationships).

    Returns True if a row was deleted, False if the document was not found.
    """
    doc = get_document(session, doc_id)
    if doc is None:
        return False
    session.delete(doc)
    session.flush()
    logger.debug("Deleted Document id=%s", doc_id)
    return True


def get_documents_by_type(session: Session, doc_type: str) -> List[Document]:
    """Return all documents matching the given doc_type."""
    stmt = select(Document).where(Document.doc_type == doc_type).order_by(Document.id)
    return list(session.scalars(stmt).all())


def search_documents(session: Session, query: str) -> List[Document]:
    """
    Simple full-text substring search across ``title``, ``filename``, and
    ``original_filename``.  For production use this should be replaced with
    an FTS5 query or a vector search.
    """
    pattern = f"%{query}%"
    stmt = select(Document).where(
        (Document.title.ilike(pattern))
        | (Document.filename.ilike(pattern))
        | (Document.original_filename.ilike(pattern))
    )
    return list(session.scalars(stmt).all())


# ─────────────────────────────────────────────────────────────────────────────
# DocumentChunk CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_chunk(session: Session, chunk_data: Dict[str, Any]) -> DocumentChunk:
    """Persist a new DocumentChunk row."""
    chunk = DocumentChunk()
    _apply_updates(chunk, chunk_data)
    session.add(chunk)
    session.flush()
    return chunk


def get_chunks_for_document(session: Session, doc_id: int) -> List[DocumentChunk]:
    """Return all chunks for a document, ordered by chunk_index."""
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(session.scalars(stmt).all())


def get_all_chunks(session: Session) -> List[DocumentChunk]:
    """Return all chunks across all documents, ordered by id."""
    stmt = select(DocumentChunk).order_by(DocumentChunk.id)
    return list(session.scalars(stmt).all())


def get_relationships_for_document(session: Session, doc_id: int) -> List[DocumentRelationship]:
    """Alias for get_relationships."""
    return get_relationships(session, doc_id)


def delete_chunks_for_document(session: Session, doc_id: int) -> None:
    """Delete all chunks belonging to ``doc_id``."""
    chunks = get_chunks_for_document(session, doc_id)
    for chunk in chunks:
        session.delete(chunk)
    session.flush()
    logger.debug("Deleted %d chunks for Document id=%s", len(chunks), doc_id)


# ─────────────────────────────────────────────────────────────────────────────
# DocumentRelationship CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_relationship(
    session: Session, rel_data: Dict[str, Any]
) -> DocumentRelationship:
    """Persist a new DocumentRelationship."""
    rel = DocumentRelationship()
    _apply_updates(rel, rel_data)
    session.add(rel)
    session.flush()
    logger.debug(
        "Created relationship %s -[%s]-> %s",
        rel.source_doc_id,
        rel.relationship_type,
        rel.target_doc_id,
    )
    return rel


def get_relationships(session: Session, doc_id: int) -> List[DocumentRelationship]:
    """
    Return all relationships where ``doc_id`` is either the source or the
    target, ordered by creation date.
    """
    stmt = (
        select(DocumentRelationship)
        .where(
            (DocumentRelationship.source_doc_id == doc_id)
            | (DocumentRelationship.target_doc_id == doc_id)
        )
        .order_by(DocumentRelationship.created_at)
    )
    return list(session.scalars(stmt).all())


# ─────────────────────────────────────────────────────────────────────────────
# ConflictReport CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_conflict_report(session: Session, data: Dict[str, Any]) -> ConflictReport:
    """Persist a new ConflictReport."""
    report = ConflictReport()
    _apply_updates(report, data)
    session.add(report)
    session.flush()
    logger.debug(
        "Created ConflictReport id=%s type=%s severity=%s",
        report.id,
        report.conflict_type,
        report.severity,
    )
    return report


def get_conflict_reports(
    session: Session, filters: Optional[Dict[str, Any]] = None
) -> List[ConflictReport]:
    """
    Return conflict reports, optionally filtered.

    Supported filter keys (all optional):
    - ``severity``          – e.g. "confirmed"
    - ``conflict_type``     – e.g. "version_mismatch"
    - ``resolution_status`` – e.g. "pending"
    - ``doc_id``            – match reports that include this document ID
    """
    stmt = select(ConflictReport).order_by(ConflictReport.created_at.desc())

    if filters:
        if "severity" in filters:
            stmt = stmt.where(ConflictReport.severity == filters["severity"])
        if "conflict_type" in filters:
            stmt = stmt.where(ConflictReport.conflict_type == filters["conflict_type"])
        if "resolution_status" in filters:
            stmt = stmt.where(
                ConflictReport.resolution_status == filters["resolution_status"]
            )
        # JSON list membership is done in Python for SQLite portability
    results = list(session.scalars(stmt).all())

    if filters and "doc_id" in filters:
        target = int(filters["doc_id"])
        results = [r for r in results if target in (r.document_ids or [])]

    return results


def update_conflict_report(
    session: Session, report_id: int, updates: Dict[str, Any]
) -> ConflictReport:
    """Apply updates to a ConflictReport and return it."""
    report = session.get(ConflictReport, report_id)
    if report is None:
        raise ValueError(f"ConflictReport id={report_id} not found.")
    _apply_updates(report, updates)
    session.flush()
    return report


# ─────────────────────────────────────────────────────────────────────────────
# QASession CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_qa_session(session: Session, data: Dict[str, Any]) -> QASession:
    """Persist a new QASession."""
    qa = QASession()
    _apply_updates(qa, data)
    session.add(qa)
    session.flush()
    logger.debug("Created QASession id=%s", qa.id)
    return qa


def get_qa_sessions(session: Session, limit: int = 50) -> List[QASession]:
    """Return the most recent QA sessions up to ``limit``."""
    stmt = select(QASession).order_by(QASession.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def update_qa_session(
    session: Session, session_id: int, updates: Dict[str, Any]
) -> QASession:
    """Apply updates to a QASession and return it."""
    qa = session.get(QASession, session_id)
    if qa is None:
        raise ValueError(f"QASession id={session_id} not found.")
    _apply_updates(qa, updates)
    session.flush()
    return qa


# ─────────────────────────────────────────────────────────────────────────────
# HumanReviewCase CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_human_review(session: Session, data: Dict[str, Any]) -> HumanReviewCase:
    """Persist a new HumanReviewCase."""
    case = HumanReviewCase()
    _apply_updates(case, data)
    session.add(case)
    session.flush()
    logger.debug("Created HumanReviewCase id=%s", case.id)
    return case


def get_human_reviews(
    session: Session, status: Optional[str] = None
) -> List[HumanReviewCase]:
    """Return human review cases, optionally filtered by status."""
    stmt = select(HumanReviewCase).order_by(HumanReviewCase.created_at.desc())
    if status is not None:
        stmt = stmt.where(HumanReviewCase.status == status)
    return list(session.scalars(stmt).all())


def update_human_review(
    session: Session, review_id: int, updates: Dict[str, Any]
) -> HumanReviewCase:
    """Apply updates to a HumanReviewCase and return it."""
    case = session.get(HumanReviewCase, review_id)
    if case is None:
        raise ValueError(f"HumanReviewCase id={review_id} not found.")
    _apply_updates(case, updates)
    session.flush()
    return case


# ─────────────────────────────────────────────────────────────────────────────
# AuditEvent
# ─────────────────────────────────────────────────────────────────────────────


def create_audit_event(
    session: Session,
    event_type: str,
    entity_type: Optional[str],
    entity_id: Optional[str],
    description: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """
    Append an immutable audit log entry.

    This should be called inside the same transaction as the action being
    audited so both commit or roll back together.
    """
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        event_metadata=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    return event


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard / Statistics aggregation
# ─────────────────────────────────────────────────────────────────────────────


def get_dashboard_stats(session: Session) -> Dict[str, Any]:
    """
    Return a snapshot of system-wide statistics suitable for a dashboard.

    Returns a dict with keys:
    - ``total_documents``
    - ``documents_by_type``    – {doc_type: count}
    - ``documents_by_status``  – {status: count}
    - ``total_chunks``
    - ``total_conflicts``
    - ``conflicts_by_severity`` – {severity: count}
    - ``pending_conflicts``
    - ``total_qa_sessions``
    - ``escalated_qa_sessions``
    - ``avg_qa_latency_ms``
    - ``pending_human_reviews``
    - ``resolved_human_reviews``
    - ``recent_audit_events``  – last 10 events as dicts
    """
    stats: Dict[str, Any] = {}

    # ── Documents ──────────────────────────────────────────────────────────
    stats["total_documents"] = session.scalar(
        select(func.count()).select_from(Document)
    )

    by_type_rows = session.execute(
        select(Document.doc_type, func.count().label("n"))
        .group_by(Document.doc_type)
    ).all()
    stats["documents_by_type"] = {row[0]: row[1] for row in by_type_rows}

    by_status_rows = session.execute(
        select(Document.status, func.count().label("n"))
        .group_by(Document.status)
    ).all()
    stats["documents_by_status"] = {row[0]: row[1] for row in by_status_rows}

    stats["total_chunks"] = session.scalar(
        select(func.count()).select_from(DocumentChunk)
    )

    # ── Conflicts ──────────────────────────────────────────────────────────
    stats["total_conflicts"] = session.scalar(
        select(func.count()).select_from(ConflictReport)
    )

    by_sev_rows = session.execute(
        select(ConflictReport.severity, func.count().label("n"))
        .group_by(ConflictReport.severity)
    ).all()
    stats["conflicts_by_severity"] = {row[0]: row[1] for row in by_sev_rows}

    stats["pending_conflicts"] = session.scalar(
        select(func.count())
        .select_from(ConflictReport)
        .where(ConflictReport.resolution_status == "pending")
    )

    # ── QA Sessions ────────────────────────────────────────────────────────
    stats["total_qa_sessions"] = session.scalar(
        select(func.count()).select_from(QASession)
    )
    stats["escalated_qa_sessions"] = session.scalar(
        select(func.count())
        .select_from(QASession)
        .where(QASession.escalated.is_(True))
    )
    avg_latency = session.scalar(
        select(func.avg(QASession.latency_ms)).select_from(QASession)
    )
    stats["avg_qa_latency_ms"] = round(avg_latency, 2) if avg_latency is not None else None

    # ── Human Reviews ──────────────────────────────────────────────────────
    stats["pending_human_reviews"] = session.scalar(
        select(func.count())
        .select_from(HumanReviewCase)
        .where(HumanReviewCase.status == "pending")
    )
    stats["resolved_human_reviews"] = session.scalar(
        select(func.count())
        .select_from(HumanReviewCase)
        .where(HumanReviewCase.status == "resolved")
    )

    # ── Recent Audit Events ────────────────────────────────────────────────
    recent_events = session.scalars(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10)
    ).all()
    stats["recent_audit_events"] = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "description": e.description,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in recent_events
    ]

    return stats
