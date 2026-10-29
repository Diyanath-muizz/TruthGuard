"""
services/conflict_service.py
────────────────────────────
Proactive conflict scanning service.
Compares newly ingested documents against existing documents to surface
contradictions, staleness, version mismatches, and supersessions proactively.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database import repository
from database.models import ConflictReport, Document
from documents.versioning import VersionGraph
from retrieval.bm25_retriever import BM25Retriever
from retrieval.vector_store import VectorStore
from services.audit_service import AuditService
from verification.authority_rules import AuthorityRules
from verification.contradiction_detector import ContradictionDetector
from verification.staleness_checker import StalenessChecker
from verification.supersession_graph import SupersessionGraph

logger = logging.getLogger(__name__)


class ConflictService:
    """
    Manages proactive conflict detection, lifecycle tracking, and resolution.
    """

    @classmethod
    def scan_new_document(
        cls,
        doc_id: int,
        db_session,
    ) -> List[ConflictReport]:
        """
        Executes proactive conflict scan for a newly ingested document against
        all previously stored documents in the repository.
        """
        doc = repository.get_document(db_session, doc_id)
        if not doc:
            logger.warning("Document id=%s not found for conflict scanning.", doc_id)
            return []

        all_docs = repository.get_all_documents(db_session)
        other_docs = [d for d in all_docs if d.id != doc.id]
        if not other_docs:
            logger.info("First document ingested; no existing corpus to conflict with.")
            return []

        reports_created: List[ConflictReport] = []
        detector = ContradictionDetector()
        supersession_graph = SupersessionGraph(db_session=db_session)

        # 1. Supersession & Version Analysis from Document Metadata
        doc_meta = {
            "id": str(doc.id),
            "title": doc.title,
            "filename": doc.filename,
            "version": doc.version,
            "doc_type": doc.doc_type,
            "authority_level": doc.authority_level,
            "effective_date": doc.effective_date,
            "supersedes": doc.supersedes if hasattr(doc, "supersedes") else None,
            "status": doc.status,
        }

        # Check for explicit supersession targets
        candidate_meta_list = [
            {
                "id": str(d.id),
                "title": d.title,
                "filename": d.filename,
                "version": d.version,
                "doc_type": d.doc_type,
                "authority_level": d.authority_level,
                "effective_date": d.effective_date,
                "status": d.status,
            }
            for d in other_docs
        ]

        # Scan document chunks to detect text-based supersession
        doc_chunks = repository.get_chunks_for_document(db_session, doc_id)
        full_text = " ".join([c.text for c in doc_chunks])

        # Check if new document supersedes any existing documents
        text_supersessions = supersession_graph.detect_from_text(full_text, candidate_meta_list)
        for s in text_supersessions:
            target_id = int(s["target_doc_id"])
            supersession_graph.add_supersession(
                source_id=doc.id,
                target_id=target_id,
                evidence=s.get("evidence", "Detected from text"),
                is_explicit=True,
                detection_method="auto",
            )
            report = repository.create_conflict_report(
                db_session,
                {
                    "document_ids": [doc.id, target_id],
                    "conflict_type": "superseded_amendment",
                    "severity": "supersession_detected",
                    "description": f"Document '{doc.filename}' explicitly supersedes '{s.get('target_title', target_id)}'.",
                    "passages": [{"source": doc.filename, "evidence": s.get("evidence")}],
                    "resolution_status": "confirmed",
                    "resolution_notes": "Explicit supersession relationship recorded.",
                },
            )
            reports_created.append(report)
            AuditService.log_conflict_detected(str(report.id), "superseded_amendment", db_session)

        # 2. Compare against existing documents for contradictory policies / numbers
        for target in other_docs:
            target_meta = {
                "id": str(target.id),
                "title": target.title,
                "filename": target.filename,
                "version": target.version,
                "doc_type": target.doc_type,
                "authority_level": target.authority_level,
                "effective_date": target.effective_date,
                "supersedes": target.supersedes if hasattr(target, "supersedes") else None,
                "status": target.status,
            }

            # Check authority decision
            auth_dec = AuthorityRules.compare_authority(doc_meta, target_meta)

            # Check target chunks for numerical contradictions
            target_chunks = repository.get_chunks_for_document(db_session, target.id)
            if not target_chunks or not doc_chunks:
                continue

            # Check if there is semantic topic overlap and numerical contradiction
            for dc in doc_chunks:
                for tc in target_chunks:
                    # Quick lexical similarity check
                    dc_words = set(dc.text.lower().split())
                    tc_words = set(tc.text.lower().split())
                    overlap = len(dc_words & tc_words)
                    if overlap >= 5:
                        # Compare passages
                        from agents import DocumentSource
                        src_a = DocumentSource(
                            doc_id=str(doc.id),
                            filename=doc.filename,
                            doc_type=doc.doc_type,
                            chunk_id=str(dc.id),
                            passage_text=dc.text,
                        )
                        src_b = DocumentSource(
                            doc_id=str(target.id),
                            filename=target.filename,
                            doc_type=target.doc_type,
                            chunk_id=str(tc.id),
                            passage_text=tc.text,
                        )
                        conflicts = detector.detect_conflicts([src_a, src_b])
                        for c in conflicts:
                            # Avoid duplicate reports for same document pair
                            existing = [
                                r for r in reports_created
                                if set(r.document_ids) == {doc.id, target.id}
                            ]
                            if not existing:
                                rep_type = "numerical" if c.conflict_type == "numerical" else "version_mismatch"
                                if doc.doc_type == "Amendment" or target.doc_type == "Amendment":
                                    rep_type = "superseded_amendment"
                                elif doc.doc_type == "FAQ" or target.doc_type == "FAQ":
                                    rep_type = "contradictory_faq"

                                rep = repository.create_conflict_report(
                                    db_session,
                                    {
                                        "document_ids": [doc.id, target.id],
                                        "conflict_type": rep_type,
                                        "severity": "potential" if not auth_dec.is_irreconcilable else "confirmed",
                                        "description": c.description,
                                        "passages": [
                                            {"doc": doc.filename, "text": dc.text},
                                            {"doc": target.filename, "text": tc.text},
                                        ],
                                        "resolution_status": "pending",
                                        "resolution_notes": auth_dec.reason,
                                    },
                                )
                                reports_created.append(rep)
                                AuditService.log_conflict_detected(str(rep.id), rep_type, db_session)

        try:
            db_session.commit()
        except Exception as e:
            logger.exception("Failed to commit conflict reports: %s", e)

        return reports_created

    @classmethod
    def get_conflict_summary(cls, db_session) -> Dict[str, Any]:
        reports = repository.get_conflict_reports(db_session)
        counts_by_type: Dict[str, int] = {}
        counts_by_status: Dict[str, int] = {}

        for r in reports:
            t = r.conflict_type or "other"
            s = r.resolution_status or "pending"
            counts_by_type[t] = counts_by_type.get(t, 0) + 1
            counts_by_status[s] = counts_by_status.get(s, 0) + 1

        return {
            "total_conflicts": len(reports),
            "by_type": counts_by_type,
            "by_status": counts_by_status,
        }

    @classmethod
    def update_conflict_status(
        cls,
        report_id: int,
        new_status: str,
        notes: str,
        resolved_by: str,
        db_session,
    ) -> Optional[ConflictReport]:
        rep = repository.update_conflict_report(
            db_session,
            report_id,
            {
                "resolution_status": new_status,
                "resolution_notes": notes,
                "resolved_by": resolved_by,
            },
        )
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
        return rep
