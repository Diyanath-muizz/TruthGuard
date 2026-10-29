"""
documents/versioning.py
───────────────────────
Document versioning, relationship tracking, and supersession detection.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


class VersionGraph:
    """
    In-memory and DB-backed graph of document relationships.
    Tracks supersession, amendment, contradiction, and lineage.
    """

    def __init__(self) -> None:
        # doc_id -> list of relationships dicts
        self._edges: Dict[str, List[Dict[str, Any]]] = {}

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        evidence: Optional[str] = None,
        is_explicit: bool = True,
        detection_method: str = "auto",
        human_verified: bool = False,
    ) -> Dict[str, Any]:
        """
        Record that source_id relates to target_id (e.g. source supersedes target).
        """
        rel = {
            "source_doc_id": str(source_id),
            "target_doc_id": str(target_id),
            "relationship_type": relationship_type,
            "evidence": evidence or "",
            "is_explicit": is_explicit,
            "detection_method": detection_method,
            "human_verified": human_verified,
        }
        if str(source_id) not in self._edges:
            self._edges[str(source_id)] = []
        self._edges[str(source_id)].append(rel)
        return rel

    def get_superseded_by(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Find any documents that supersede this document.
        (Where doc_id is the target of a 'supersedes' or 'replaces' relation)
        """
        superseded_by = []
        target_str = str(doc_id)
        for src, rels in self._edges.items():
            for r in rels:
                if r["target_doc_id"] == target_str and r["relationship_type"] in {"supersedes", "replaces"}:
                    superseded_by.append(r)
        return superseded_by

    def get_supersedes(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Find documents that this document supersedes.
        """
        rels = self._edges.get(str(doc_id), [])
        return [r for r in rels if r["relationship_type"] in {"supersedes", "replaces"}]

    def is_superseded(self, doc_id: str) -> bool:
        """
        Returns True if any document supersedes doc_id.
        """
        return len(self.get_superseded_by(doc_id)) > 0

    @staticmethod
    def detect_supersession_from_text(text: str, candidate_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans text for explicit supersession keywords:
        "supersedes [Doc Title/Version]", "replaces policy...", "this amendment supersedes..."
        """
        detected: List[Dict[str, Any]] = []
        lower_text = text.lower()

        patterns = [
            r"supersedes\s+([^\.\n;]+)",
            r"replaces\s+([^\.\n;]+)",
            r"amends\s+([^\.\n;]+)",
            r"overrides\s+([^\.\n;]+)",
            r"in\s+lieu\s+of\s+([^\.\n;]+)",
        ]

        found_mentions: List[str] = []
        for pat in patterns:
            for match in re.finditer(pat, lower_text):
                found_mentions.append(match.group(1).strip())

        for doc in candidate_docs:
            doc_id = str(doc.get("id"))
            title = (doc.get("title") or "").lower()
            filename = (doc.get("filename") or "").lower()
            version = (doc.get("version") or "").lower()

            for mention in found_mentions:
                matched = False
                if title and (title in mention or mention in title):
                    matched = True
                elif filename and (filename in mention or mention in filename):
                    matched = True
                elif version and version in mention:
                    matched = True

                if matched:
                    detected.append({
                        "target_doc_id": doc_id,
                        "target_title": doc.get("title") or doc.get("filename"),
                        "relationship_type": "supersedes",
                        "evidence": f"Explicit text reference found: '{mention}'",
                        "is_explicit": True,
                        "detection_method": "auto",
                    })
                    break

        return detected

    @staticmethod
    def compare_versions(doc_a: Dict[str, Any], doc_b: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two documents for version precedence.
        """
        ver_a = doc_a.get("version") or ""
        ver_b = doc_b.get("version") or ""
        eff_a = doc_a.get("effective_date") or ""
        eff_b = doc_b.get("effective_date") or ""
        auth_a = doc_a.get("authority_level", 1)
        auth_b = doc_b.get("authority_level", 1)

        result = {
            "doc_a_id": doc_a.get("id"),
            "doc_b_id": doc_b.get("id"),
            "doc_a_authority": auth_a,
            "doc_b_authority": auth_b,
            "newer_by_effective_date": None,
            "higher_authority": None,
        }

        if auth_a > auth_b:
            result["higher_authority"] = "doc_a"
        elif auth_b > auth_a:
            result["higher_authority"] = "doc_b"

        if eff_a and eff_b:
            if eff_a > eff_b:
                result["newer_by_effective_date"] = "doc_a"
            elif eff_b > eff_a:
                result["newer_by_effective_date"] = "doc_b"

        return result
