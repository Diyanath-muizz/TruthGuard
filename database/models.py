"""
database/models.py
──────────────────
SQLAlchemy 2.0 ORM models for TruthGuard.

All tables use the modern ``DeclarativeBase`` style.  JSON columns are stored
as TEXT in SQLite (SQLAlchemy's JSON type handles serialisation transparently).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


# ─────────────────────────────────────────────────────────────────────────────
# Declarative base
# ─────────────────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Shared declarative base for all TruthGuard ORM models."""

    pass


def _now_utc() -> datetime:
    """Return timezone-aware UTC datetime (used as column default)."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Document
# ─────────────────────────────────────────────────────────────────────────────


class Document(Base):
    """
    Represents an ingested source document (Amendment, Policy, FAQ, etc.).

    ``metadata_source`` records how the metadata fields were populated:
    - ``user``     – the user filled them in via the UI
    - ``auto``     – automatically extracted from document content/properties
    - ``inferred`` – defaulted / inferred by the system
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # File info
    filename: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)

    # Document classification
    doc_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Other",
        comment="Amendment | Policy | FAQ | Other",
    )
    authority_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Derived from AUTHORITY_HIERARCHY"
    )

    # Bibliographic fields
    title: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    supersedes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dates
    publication_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    effective_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    expiration_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        comment="active | superseded | expired | revoked",
    )
    upload_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # Chunking stats
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Metadata provenance
    metadata_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user",
        comment="user | auto | inferred",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )
    outgoing_relationships: Mapped[List["DocumentRelationship"]] = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.source_doc_id",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[List["DocumentRelationship"]] = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.target_doc_id",
        back_populates="target_document",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} title={self.title!r} "
            f"type={self.doc_type} status={self.status}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. DocumentChunk
# ─────────────────────────────────────────────────────────────────────────────


class DocumentChunk(Base):
    """
    A single text chunk extracted from a Document.

    ``chroma_chunk_id`` links this row to the corresponding vector in ChromaDB.
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chroma_chunk_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # ── Relationship back to parent ───────────────────────────────────────────
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_doc_chunk"),
        Index("ix_doc_chunks_chroma", "chroma_chunk_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} doc_id={self.document_id} "
            f"chunk_index={self.chunk_index} page={self.page_number}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. DocumentRelationship
# ─────────────────────────────────────────────────────────────────────────────


class DocumentRelationship(Base):
    """
    Directed relationship between two documents.

    ``relationship_type``:
      - ``supersedes``  – source supersedes (replaces) target
      - ``amends``      – source amends target
      - ``contradicts`` – source contradicts target
      - ``related``     – generic / unclassified relation

    ``detection_method``:
      - ``user``     – asserted by a human via the UI
      - ``auto``     – detected by the agent pipeline
      - ``inferred`` – inferred via heuristics / metadata
    """

    __tablename__ = "document_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="supersedes | amends | contradicts | related",
    )
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detection_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="auto",
        comment="user | auto | inferred",
    )
    human_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # ── ORM relationships ─────────────────────────────────────────────────────
    source_document: Mapped["Document"] = relationship(
        "Document",
        foreign_keys=[source_doc_id],
        back_populates="outgoing_relationships",
    )
    target_document: Mapped["Document"] = relationship(
        "Document",
        foreign_keys=[target_doc_id],
        back_populates="incoming_relationships",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentRelationship {self.source_doc_id} "
            f"--[{self.relationship_type}]--> {self.target_doc_id}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. ConflictReport
# ─────────────────────────────────────────────────────────────────────────────


class ConflictReport(Base):
    """
    A detected or manually-raised conflict between two or more documents.

    ``conflict_type``:
      superseded_amendment | contradictory_faq | version_mismatch |
      unsupported_claim | numerical | date | scope | eligibility

    ``severity``:
      confirmed | potential | warning | none

    ``resolution_status``:
      pending | confirmed | resolved | false_positive | needs_review
    """

    __tablename__ = "conflict_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # JSON list of document IDs involved
    document_ids: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    conflict_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "superseded_amendment | contradictory_faq | version_mismatch | "
            "unsupported_claim | numerical | date | scope | eligibility"
        ),
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="potential",
        comment="confirmed | potential | warning | none",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON list of {doc_id, passage, page} objects
    passages: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    resolution_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        comment="pending | confirmed | resolved | false_positive | needs_review",
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # ── Back-reference from HumanReviewCase ───────────────────────────────────
    human_review_cases: Mapped[List["HumanReviewCase"]] = relationship(
        "HumanReviewCase",
        foreign_keys="HumanReviewCase.conflict_report_id",
        back_populates="conflict_report",
    )

    def __repr__(self) -> str:
        return (
            f"<ConflictReport id={self.id} type={self.conflict_type} "
            f"severity={self.severity} status={self.resolution_status}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. QASession
# ─────────────────────────────────────────────────────────────────────────────


class QASession(Base):
    """
    Stores the full trace of a single question-answer interaction through the
    multi-agent pipeline.

    ``verification_status``:
      verified | verified_with_warnings | conflict_detected |
      human_review_required | abstained
    """

    __tablename__ = "qa_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON list of {chunk_id, doc_id, score, passage} objects
    retrieval_results: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    draft_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON object returned by the Critic agent
    critic_report: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    final_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verification_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="verified",
        comment=(
            "verified | verified_with_warnings | conflict_detected | "
            "human_review_required | abstained"
        ),
    )
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # JSON list of Citation objects (serialised)
    citations: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Back-reference ────────────────────────────────────────────────────────
    human_review_cases: Mapped[List["HumanReviewCase"]] = relationship(
        "HumanReviewCase",
        foreign_keys="HumanReviewCase.qa_session_id",
        back_populates="qa_session",
    )

    def __repr__(self) -> str:
        return (
            f"<QASession id={self.id} status={self.verification_status} "
            f"revisions={self.revision_count} escalated={self.escalated}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. HumanReviewCase
# ─────────────────────────────────────────────────────────────────────────────


class HumanReviewCase(Base):
    """
    A case escalated to a human reviewer.

    A case may originate from either a QASession (when the agent cannot
    produce a confident answer) or a ConflictReport (when a conflict
    requires human adjudication).  Both foreign keys are nullable; at
    least one should be set.

    ``status``:
      pending | resolved | false_positive
    """

    __tablename__ = "human_review_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    qa_session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("qa_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conflict_report_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("conflict_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        comment="pending | resolved | false_positive",
    )

    # JSON list of {doc_id, passage, page} objects
    conflicting_passages: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    # ── ORM relationships ─────────────────────────────────────────────────────
    qa_session: Mapped[Optional["QASession"]] = relationship(
        "QASession", foreign_keys=[qa_session_id], back_populates="human_review_cases"
    )
    conflict_report: Mapped[Optional["ConflictReport"]] = relationship(
        "ConflictReport",
        foreign_keys=[conflict_report_id],
        back_populates="human_review_cases",
    )

    def __repr__(self) -> str:
        return (
            f"<HumanReviewCase id={self.id} status={self.status} "
            f"qa_session={self.qa_session_id} conflict={self.conflict_report_id}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. AuditEvent
# ─────────────────────────────────────────────────────────────────────────────


class AuditEvent(Base):
    """
    Append-only audit log for significant system events.

    ``event_type`` examples:
      document_uploaded | document_deleted | conflict_detected |
      conflict_resolved | qa_answered | review_escalated | review_resolved |
      settings_changed | login_attempt

    ``entity_type`` examples: document | chunk | conflict | qa_session | review
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Arbitrary JSON payload (agent name, IP, diff, etc.)
    event_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} type={self.event_type} "
            f"entity={self.entity_type}:{self.entity_id}>"
        )
