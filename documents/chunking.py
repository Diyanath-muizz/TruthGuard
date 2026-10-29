"""
documents/chunking.py
─────────────────────
Sentence-aware, overlap-supporting text chunker for TruthGuard.

Each chunk is a ``TextChunk`` dataclass carrying:
- a stable ``chunk_id``  (derived from document_id + chunk_index)
- positional information (char_start, char_end, page_number)

Token counting is performed with tiktoken so chunk boundaries respect the
configured token budget.

Usage::

    from documents.chunking import chunk_document

    chunks = chunk_document(
        text="...",
        document_id=42,
        pages=[{"page_num": 1, "text": "..."}, ...],
    )
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Optional tiktoken import (fall back to a whitespace-based word counter)
# ─────────────────────────────────────────────────────────────────────────────

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")  # GPT-4 / embedding model encoding

    def _count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text, disallowed_special=()))

except ImportError:  # pragma: no cover
    logger.warning("tiktoken not available – falling back to word-count token estimation.")

    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        """Approximate: 1 token ≈ 0.75 words (rough average across English text)."""
        words = len(text.split())
        return max(1, int(words / 0.75))


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TextChunk:
    """
    A single chunk of text extracted from a document.

    Attributes:
        chunk_id:     Stable hex identifier derived from document_id + chunk_index.
        document_id:  Primary key of the parent ``Document`` row.
        chunk_index:  Zero-based sequential index within the document.
        text:         The chunk text (may end on a sentence boundary).
        page_number:  Page where the majority of the chunk text originates.
                      None for single-page formats (DOCX, TXT).
        char_start:   Character offset of the first character in the full
                      document text string.
        char_end:     Character offset one past the last character.
    """

    chunk_id: str
    document_id: int
    chunk_index: int
    text: str
    page_number: Optional[int]
    char_start: int
    char_end: int


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

# Simple sentence-ending pattern: end after '.', '!', '?', or '…' followed
# by optional closing brackets/quotes and whitespace.
_SENTENCE_END = re.compile(
    r'(?<=[.!?…])["\'\)\]]*\s+',
    re.UNICODE,
)


def _make_chunk_id(document_id: int, chunk_index: int) -> str:
    """
    Derive a stable, collision-resistant ID for a chunk.

    The ID is a 16-character hex prefix of SHA-256(document_id:chunk_index).
    """
    raw = f"{document_id}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _split_into_sentences(text: str) -> List[Tuple[str, int, int]]:
    """
    Split ``text`` into sentences.

    Returns a list of ``(sentence_text, char_start, char_end)`` tuples where
    offsets are relative to the full ``text`` string.
    """
    sentences: List[Tuple[str, int, int]] = []
    last_end = 0

    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        sentence = text[last_end:end]
        if sentence.strip():
            sentences.append((sentence, last_end, end))
        last_end = end

    # Remainder after the last sentence boundary
    remainder = text[last_end:]
    if remainder.strip():
        sentences.append((remainder, last_end, len(text)))

    return sentences


def _build_page_index(pages: List[Dict]) -> Dict[Tuple[int, int], int]:
    """
    Build a mapping from (char_start, char_end) spans to page numbers based on
    reconstructing the concatenated text from the page list.

    Returns a list of ``(page_char_end, page_num)`` pairs sorted by char offset
    for quick bisect lookups.
    """
    index: List[Tuple[int, int]] = []  # (page_end_char, page_num)
    cursor = 0
    for page in pages:
        page_text = page.get("text", "")
        page_num = page.get("page_num", 1)
        end = cursor + len(page_text) + 2  # +2 for the \n\n separator
        index.append((end, page_num))
        cursor = end
    return index  # type: ignore[return-value]


def _find_page(char_pos: int, page_index: List[Tuple[int, int]]) -> Optional[int]:
    """
    Return the page number for ``char_pos`` using a linear scan of the
    page_index produced by ``_build_page_index``.
    """
    if not page_index:
        return None
    for end, page_num in page_index:
        if char_pos < end:
            return page_num
    return page_index[-1][1]  # Last page


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def chunk_document(
    text: str,
    document_id: int,
    pages: Optional[List[Dict]] = None,
    chunk_size: int = 512,
    overlap: int = 50,
) -> List[TextChunk]:
    """
    Split ``text`` into overlapping, sentence-aware chunks.

    Args:
        text:        Full document text (as returned by a parser).
        document_id: Database ID of the parent document.
        pages:       Optional list of ``{"page_num": int, "text": str}`` dicts
                     from the parser.  Used to attribute each chunk to a page.
        chunk_size:  Target chunk size in tokens (default 512).
        overlap:     Token overlap between successive chunks (default 50).

    Returns:
        List of ``TextChunk`` objects ordered by ``chunk_index``.
    """
    if not text or not text.strip():
        logger.warning("chunk_document called with empty text for document_id=%s", document_id)
        return []

    pages = pages or []
    page_index = _build_page_index(pages) if pages else []

    chunk_size = chunk_size or 512
    overlap = overlap if overlap is not None else 50

    # ── Handle very short documents ───────────────────────────────────────
    total_tokens = _count_tokens(text)
    if total_tokens <= chunk_size:
        logger.debug(
            "Document %s is short (%d tokens) – returning as single chunk.",
            document_id,
            total_tokens,
        )
        page_num = pages[0].get("page_num") if pages else None
        return [
            TextChunk(
                chunk_id=_make_chunk_id(document_id, 0),
                document_id=document_id,
                chunk_index=0,
                text=text.strip(),
                page_number=page_num,
                char_start=0,
                char_end=len(text),
            )
        ]

    # ── Split into sentences ──────────────────────────────────────────────
    sentences = _split_into_sentences(text)
    if not sentences:
        # Fallback: treat the whole text as one chunk
        return chunk_document(text, document_id, pages, chunk_size=chunk_size + 1, overlap=0)

    # ── Greedy chunk construction ─────────────────────────────────────────
    chunks: List[TextChunk] = []
    chunk_index = 0

    # Pointers into the sentences list
    window_start = 0  # inclusive sentence index for the current chunk
    overlap_token_budget = overlap

    while window_start < len(sentences):
        current_tokens = 0
        window_end = window_start  # will advance forward
        chunk_sentences: List[Tuple[str, int, int]] = []

        while window_end < len(sentences):
            sent_text, sent_start, sent_end = sentences[window_end]
            sent_tokens = _count_tokens(sent_text)

            # If a single sentence is larger than chunk_size, include it anyway
            if current_tokens + sent_tokens > chunk_size and chunk_sentences:
                break

            chunk_sentences.append((sent_text, sent_start, sent_end))
            current_tokens += sent_tokens
            window_end += 1

        if not chunk_sentences:
            # Safety: advance at least one sentence to avoid infinite loop
            chunk_sentences = [sentences[window_start]]
            window_end = window_start + 1

        chunk_text = "".join(s[0] for s in chunk_sentences).strip()
        char_start = chunk_sentences[0][1]
        char_end = chunk_sentences[-1][2]

        if chunk_text:
            page_num = _find_page(char_start, page_index) if page_index else (
                pages[0].get("page_num") if pages else None
            )
            chunks.append(
                TextChunk(
                    chunk_id=_make_chunk_id(document_id, chunk_index),
                    document_id=document_id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    page_number=page_num,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            chunk_index += 1

        # ── Compute overlap rollback ──────────────────────────────────────
        # Walk backward from window_end until we've consumed ``overlap`` tokens.
        overlap_consumed = 0
        rollback = window_end
        for i in range(window_end - 1, window_start, -1):
            sent_tokens = _count_tokens(sentences[i][0])
            if overlap_consumed + sent_tokens > overlap_token_budget:
                break
            overlap_consumed += sent_tokens
            rollback = i

        # Advance window; ensure progress even if overlap covers all
        next_start = max(rollback, window_start + 1)
        window_start = next_start

    logger.debug(
        "Chunked document %s into %d chunks (chunk_size=%d, overlap=%d).",
        document_id,
        len(chunks),
        chunk_size,
        overlap,
    )
    return chunks


class DocumentChunker:
    """
    Object-oriented wrapper around chunk_document.
    """

    def chunk_document(
        self,
        text: str,
        document_id: int,
        pages: Optional[List[Dict[str, Any]]] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[TextChunk]:
        return chunk_document(
            text=text,
            document_id=document_id,
            pages=pages,
            chunk_size=chunk_size,
            overlap=overlap,
        )

