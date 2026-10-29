"""
documents/metadata.py
─────────────────────
Metadata models, extraction, validation, and authority inference for TruthGuard.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from config.settings import AUTHORITY_HIERARCHY, settings


class DocumentMetadata(BaseModel):
    """
    Validated document metadata structure.
    """
    title: Optional[str] = None
    doc_type: str = Field(default="Other")
    version: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    department: Optional[str] = "All"
    authority_level: int = 1
    supersedes: Optional[str] = None
    status: str = Field(default="active")
    metadata_source: str = Field(default="user")  # 'user', 'auto', 'inferred'

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        standardized = v.strip().capitalize() if v else "Other"
        valid = {"Amendment", "Policy", "Faq", "FAQ", "Other"}
        if standardized == "Faq":
            standardized = "FAQ"
        if standardized not in valid:
            return "Other"
        return standardized

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        s = v.strip().lower() if v else "active"
        if s not in {"active", "superseded", "expired", "revoked"}:
            return "active"
        return s


def infer_authority_level(doc_type: str) -> int:
    """
    Returns authority level from hierarchy: Amendment(4) > Policy(3) > FAQ(2) > Other(1)
    """
    cleaned = doc_type.strip().capitalize() if doc_type else "Other"
    if cleaned.upper() == "FAQ":
        cleaned = "FAQ"
    return AUTHORITY_HIERARCHY.get(cleaned, 1)


def validate_metadata(data: Dict[str, Any]) -> Tuple[DocumentMetadata, List[str]]:
    """
    Validates metadata dict and produces warnings for missing critical fields.
    Does NOT invent values.
    """
    warnings: List[str] = []

    doc_type = data.get("doc_type") or "Other"
    authority = data.get("authority_level")
    if authority is None:
        authority = infer_authority_level(doc_type)

    meta = DocumentMetadata(
        title=data.get("title"),
        doc_type=doc_type,
        version=data.get("version"),
        publication_date=data.get("publication_date"),
        effective_date=data.get("effective_date"),
        expiration_date=data.get("expiration_date"),
        department=data.get("department") or "All",
        authority_level=authority,
        supersedes=data.get("supersedes"),
        status=data.get("status") or "active",
        metadata_source=data.get("metadata_source") or "user",
    )

    if not meta.effective_date:
        warnings.append("Effective date is missing; temporal applicability cannot be formally verified.")
    if not meta.version:
        warnings.append("Document version is unspecified.")
    if not meta.title:
        warnings.append("Document title is unspecified.")
    if meta.doc_type == "Amendment" and not meta.supersedes:
        warnings.append("Document is labeled 'Amendment' but does not explicitly specify which policy it supersedes or amends.")

    return meta, warnings


def extract_metadata_from_text(text: str) -> Dict[str, Any]:
    """
    Extracts structured metadata from text headers or standard patterns.
    Never invents dates or versions; only returns matched items.
    """
    extracted: Dict[str, Any] = {}

    # Check for header blocks like "DOCUMENT TITLE: ...", "TYPE: ...", etc.
    title_match = re.search(r"(?:DOCUMENT\s+TITLE|TITLE):\s*(.+)", text, re.IGNORECASE)
    if title_match:
        extracted["title"] = title_match.group(1).strip()

    type_match = re.search(r"(?:DOCUMENT\s+TYPE|TYPE):\s*(Amendment|Policy|FAQ|Other)", text, re.IGNORECASE)
    if type_match:
        extracted["doc_type"] = type_match.group(1).strip().capitalize()
        if extracted["doc_type"].upper() == "FAQ":
            extracted["doc_type"] = "FAQ"

    version_match = re.search(r"(?:VERSION|VER\.?):\s*([a-zA-Z0-9\.\-_]+)", text, re.IGNORECASE)
    if version_match:
        extracted["version"] = version_match.group(1).strip()

    pub_date_match = re.search(r"(?:PUBLICATION\s+DATE|PUBLISHED):\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    if pub_date_match:
        extracted["publication_date"] = pub_date_match.group(1).strip()

    eff_date_match = re.search(r"(?:EFFECTIVE\s+DATE|EFFECTIVE\s+FROM|EFFECTIVE):\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    if eff_date_match:
        extracted["effective_date"] = eff_date_match.group(1).strip()

    exp_date_match = re.search(r"(?:EXPIRATION\s+DATE|EXPIRES|VALID\s+UNTIL):\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    if exp_date_match:
        extracted["expiration_date"] = exp_date_match.group(1).strip()

    dept_match = re.search(r"(?:DEPARTMENT|DEPT|ORGANIZATIONAL\s+SCOPE|SCOPE):\s*(.+)", text, re.IGNORECASE)
    if dept_match:
        extracted["department"] = dept_match.group(1).strip()

    supersedes_match = re.search(r"(?:SUPERSEDES|REPLACES|AMENDS):\s*(.+)", text, re.IGNORECASE)
    if supersedes_match:
        val = supersedes_match.group(1).strip()
        if val.lower() not in {"none", "n/a", "nil"}:
            extracted["supersedes"] = val

    auth_match = re.search(r"AUTHORITY\s+LEVEL:\s*([1-4])", text, re.IGNORECASE)
    if auth_match:
        extracted["authority_level"] = int(auth_match.group(1))

    status_match = re.search(r"STATUS:\s*(Active|Superseded|Expired|Revoked)", text, re.IGNORECASE)
    if status_match:
        extracted["status"] = status_match.group(1).strip().lower()

    return extracted
