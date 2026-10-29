"""
verification/supersession_graph.py
──────────────────────────────────
Supersession and document relation graph.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database import repository
from documents.versioning import VersionGraph

logger = logging.getLogger(__name__)


class SupersessionGraph:
    """
    Manages directed edges of document supersession, amendment, and conflict.
    """

    def __init__(self, db_session=None) -> None:
        self.db_session = db_session
        self.inner_graph = VersionGraph()

    def add_supersession(
        self,
        source_id: int | str,
        target_id: int | str,
        evidence: str = "",
        is_explicit: bool = True,
        detection_method: str = "auto",
        human_verified: bool = False,
    ) -> Dict[str, Any]:
        rel = self.inner_graph.add_relationship(
            source_id=str(source_id),
            target_id=str(target_id),
            relationship_type="supersedes",
            evidence=evidence,
            is_explicit=is_explicit,
            detection_method=detection_method,
            human_verified=human_verified,
        )

        if self.db_session:
            try:
                repository.create_relationship(
                    self.db_session,
                    {
                        "source_doc_id": int(source_id),
                        "target_doc_id": int(target_id),
                        "relationship_type": "supersedes",
                        "evidence": evidence,
                        "is_explicit": is_explicit,
                        "detection_method": detection_method,
                        "human_verified": human_verified,
                    },
                )
            except Exception as e:
                logger.warning("Could not persist relationship to DB: %s", e)

        return rel

    def is_superseded(self, doc_id: int | str) -> bool:
        if self.db_session:
            try:
                rels = repository.get_relationships_for_document(self.db_session, int(doc_id))
                for r in rels:
                    if r.target_doc_id == int(doc_id) and r.relationship_type in {"supersedes", "replaces"}:
                        return True
            except Exception as e:
                logger.warning("DB error checking supersession: %s", e)
        return self.inner_graph.is_superseded(str(doc_id))

    def detect_from_text(self, text: str, candidate_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return VersionGraph.detect_supersession_from_text(text, candidate_docs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [],
            "edges": self.inner_graph._edges,
        }
