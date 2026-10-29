"""
documents/parsers.py
────────────────────
Unified document parser for TruthGuard.

Supported formats:
- PDF  – via PyPDF2 (page-level text extraction)
- DOCX – via python-docx
- TXT  – plain UTF-8 / latin-1 read

Returns a ``ParseResult`` dataclass that carries the full text, per-page
content, extracted metadata, warnings, and any error message.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParseResult:
    """
    Output of a document parse operation.

    Attributes:
        text:      Full concatenated text of the document.
        pages:     List of per-page dicts ``{"page_num": int, "text": str}``.
        metadata:  Extracted document properties (title, author, dates, …).
        warnings:  Non-fatal issues discovered during parsing.
        error:     If parsing failed, a human-readable error message; else None.
        content_hash: SHA-256 hex digest of the raw file bytes.
        file_size_bytes: Size of the source file in bytes.
    """

    text: str = ""
    pages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    content_hash: str = ""
    file_size_bytes: int = 0

    @property
    def success(self) -> bool:
        """True when parsing produced usable text with no fatal error."""
        return self.error is None and bool(self.text.strip())


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    """Return the hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _check_file_size(path: Path, raw: bytes) -> Optional[str]:
    """
    Return an error string if the file exceeds the configured size limit,
    otherwise return None.
    """
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        return (
            f"File size {size_mb:.1f} MB exceeds the limit of "
            f"{settings.max_file_size_mb} MB."
        )
    return None


def _clean_text(text: str) -> str:
    """
    Lightly normalise extracted text:
    - Collapse runs of whitespace within a line (preserve newlines)
    - Strip trailing whitespace per line
    - Remove control characters (except common whitespace)
    """
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Remove non-printable control chars except tab/space
        line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)
        line = re.sub(r"[ \t]+", " ", line).rstrip()
        cleaned.append(line)
    return "\n".join(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# PDF parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_pdf(raw: bytes, filename: str) -> ParseResult:
    """Extract text and metadata from a PDF file using PyPDF2."""
    result = ParseResult(
        content_hash=_sha256(raw),
        file_size_bytes=len(raw),
    )

    try:
        import io

        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(io.BytesIO(raw), strict=False)
    except Exception as exc:  # noqa: BLE001
        result.error = f"Failed to open PDF '{filename}': {exc}"
        logger.error(result.error)
        return result

    # ── Metadata ──────────────────────────────────────────────────────────
    try:
        pdf_meta = reader.metadata or {}
        for key, value in pdf_meta.items():
            # PyPDF2 keys look like "/Title", "/Author", etc.
            clean_key = key.lstrip("/").lower()
            result.metadata[clean_key] = str(value) if value else ""
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Could not read PDF metadata: {exc}")

    # ── Page text ─────────────────────────────────────────────────────────
    if len(reader.pages) == 0:
        result.error = f"PDF '{filename}' has no pages."
        return result

    all_texts: List[str] = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
            page_text = _clean_text(page_text)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Could not extract text from page {page_num}: {exc}")
            page_text = ""

        result.pages.append({"page_num": page_num, "text": page_text})
        all_texts.append(page_text)

    result.text = "\n\n".join(t for t in all_texts if t)

    if not result.text.strip():
        result.warnings.append(
            f"PDF '{filename}' appears to contain no extractable text "
            "(it may be scanned or image-only)."
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# DOCX parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_docx(raw: bytes, filename: str) -> ParseResult:
    """Extract text and metadata from a DOCX file using python-docx."""
    result = ParseResult(
        content_hash=_sha256(raw),
        file_size_bytes=len(raw),
    )

    try:
        import io

        import docx  # type: ignore

        doc = docx.Document(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        result.error = f"Failed to open DOCX '{filename}': {exc}"
        logger.error(result.error)
        return result

    # ── Core properties (metadata) ─────────────────────────────────────────
    try:
        props = doc.core_properties
        result.metadata = {
            "title": props.title or "",
            "author": props.author or "",
            "subject": props.subject or "",
            "keywords": props.keywords or "",
            "description": props.description or "",
            "last_modified_by": props.last_modified_by or "",
            "created": str(props.created) if props.created else "",
            "modified": str(props.modified) if props.modified else "",
            "revision": str(props.revision) if props.revision else "",
        }
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Could not read DOCX core properties: {exc}")

    # ── Paragraph text ─────────────────────────────────────────────────────
    # DOCX does not natively expose page numbers; we treat the whole document
    # as page 1 and note this as a limitation.
    paragraphs: List[str] = []
    for para in doc.paragraphs:
        text = para.text
        if text.strip():
            paragraphs.append(_clean_text(text))

    # Also extract text from tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    paragraphs.append(_clean_text(cell_text))

    result.text = "\n\n".join(paragraphs)
    result.pages = [{"page_num": 1, "text": result.text}]

    if not result.text.strip():
        result.warnings.append(f"DOCX '{filename}' contains no extractable text.")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# TXT parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_txt(raw: bytes, filename: str) -> ParseResult:
    """Read a plain-text file with graceful encoding fallback."""
    result = ParseResult(
        content_hash=_sha256(raw),
        file_size_bytes=len(raw),
    )

    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = raw.decode(encoding)
            if encoding != "utf-8":
                result.warnings.append(
                    f"File '{filename}' decoded with fallback encoding '{encoding}'."
                )
            break
        except UnicodeDecodeError:
            continue
    else:
        result.error = f"Could not decode '{filename}' with any supported encoding."
        return result

    result.text = _clean_text(text)
    result.pages = [{"page_num": 1, "text": result.text}]
    result.metadata = {}

    if not result.text.strip():
        result.warnings.append(f"TXT file '{filename}' is empty.")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def parse_document(file_path: str | Path) -> ParseResult:
    """
    Parse a document file and return a ``ParseResult``.

    Supported extensions: ``.pdf``, ``.docx``, ``.txt``

    Args:
        file_path: Absolute or relative path to the document on disk.

    Returns:
        A populated ``ParseResult``.  Check ``.success`` and ``.error``
        before using the result.
    """
    path = Path(file_path)

    if not path.exists():
        return ParseResult(error=f"File not found: {path}")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return ParseResult(error=f"Cannot read file '{path}': {exc}")

    # ── File size guard ───────────────────────────────────────────────────
    size_error = _check_file_size(path, raw)
    if size_error:
        return ParseResult(
            content_hash=_sha256(raw),
            file_size_bytes=len(raw),
            error=size_error,
        )

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        result = _parse_pdf(raw, path.name)
    elif suffix == ".docx":
        result = _parse_docx(raw, path.name)
    elif suffix in (".txt", ".text", ".md"):
        result = _parse_txt(raw, path.name)
    else:
        return ParseResult(
            content_hash=_sha256(raw),
            file_size_bytes=len(raw),
            error=(
                f"Unsupported file type '{suffix}'. "
                "Supported types: .pdf, .docx, .txt"
            ),
        )

    logger.info(
        "Parsed '%s' (%s): %d chars, %d pages, %d warning(s), error=%s",
        path.name,
        suffix,
        len(result.text),
        len(result.pages),
        len(result.warnings),
        result.error,
    )
    return result


def parse_document_bytes(
    raw: bytes, filename: str, extension: Optional[str] = None
) -> ParseResult:
    """
    Parse a document from raw bytes (useful when the file is uploaded in
    memory, e.g. via Streamlit's ``st.file_uploader``).

    Args:
        raw:       Raw file bytes.
        filename:  Original filename (used for logging and extension detection).
        extension: Override the extension if it cannot be inferred from
                   ``filename`` (e.g. ``".pdf"``).
    """
    import tempfile

    suffix = extension or Path(filename).suffix.lower()
    if not suffix:
        return ParseResult(error=f"Cannot determine file type from filename '{filename}'.")

    # Write to a temp file so the existing per-format functions can be reused
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    try:
        return parse_document(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


class DocumentParser:
    """
    Object-oriented wrapper providing a consistent parse() interface.
    """

    def parse(self, raw: bytes, filename: str) -> ParseResult:
        if not raw or len(raw) == 0:
            return ParseResult(
                content_hash=_sha256(b""),
                file_size_bytes=0,
                error=f"File '{filename}' is empty.",
            )
        suffix = Path(filename).suffix.lower()
        if suffix not in (".pdf", ".docx", ".txt", ".text", ".md"):
            return ParseResult(
                content_hash=_sha256(raw),
                file_size_bytes=len(raw),
                error=f"Unsupported file extension '{suffix}'. Supported types: .pdf, .docx, .txt",
            )
        return parse_document_bytes(raw, filename)


