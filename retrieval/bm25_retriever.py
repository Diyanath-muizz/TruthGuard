"""
retrieval/bm25_retriever.py
----------------------------
BM25 sparse retriever backed by rank_bm25.
The index is persisted to disk as a pickle file so it survives restarts.
"""

from __future__ import annotations

import logging
import os
import pickle
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INDEX_PATH = os.path.join("data", "bm25_index.pkl")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BM25Result:
    """A single result from a BM25 keyword search."""

    chunk_id: str
    """Unique chunk identifier."""

    doc_id: str
    """Parent document identifier."""

    text: str
    """Raw text of the chunk."""

    score: float
    """BM25 relevance score (higher = more relevant)."""

    metadata: dict[str, Any]
    """Metadata associated with this chunk."""


# ---------------------------------------------------------------------------
# Internal index state (what we pickle to disk)
# ---------------------------------------------------------------------------

@dataclass
class _IndexState:
    """Serialisable state for the BM25 index."""

    chunks: list[dict[str, Any]] = field(default_factory=list)
    """All indexed chunks.  Each dict must have: chunk_id, doc_id, text, metadata."""

    tokenized_corpus: list[list[str]] = field(default_factory=list)
    """Pre-tokenised corpus (parallel to chunks)."""


# ---------------------------------------------------------------------------
# BM25Retriever
# ---------------------------------------------------------------------------

class BM25Retriever:
    """
    BM25-based keyword retriever with disk persistence.

    The retriever stores its entire corpus in a pickle file so the index
    survives service restarts without re-ingesting documents.

    Configuration
    -------------
    ``index_path`` is resolved in this order:
      1. Constructor argument.
      2. ``BM25_INDEX_PATH`` environment variable.
      3. Default ``"data/bm25_index.pkl"``.
    """

    def __init__(self, index_path: str | None = None) -> None:
        self._index_path: str = (
            index_path
            or os.getenv("BM25_INDEX_PATH", DEFAULT_INDEX_PATH)
        )
        self._state: _IndexState | None = None
        self._bm25 = None  # rank_bm25.BM25Okapi instance

    # ------------------------------------------------------------------
    # Tokenisation
    # ------------------------------------------------------------------

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """
        Simple whitespace + lowercasing tokeniser.
        Strips punctuation to improve recall.
        """
        text = text.lower()
        # Replace non-alphanumeric characters (except apostrophes) with spaces.
        text = re.sub(r"[^a-z0-9'\s]", " ", text)
        tokens = text.split()
        return tokens

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_index(self) -> None:
        """Load index state from disk if it exists."""
        if not os.path.exists(self._index_path):
            logger.debug("BM25 index file not found at '%s'. Starting fresh.", self._index_path)
            self._state = _IndexState()
            self._bm25 = None
            return

        try:
            with open(self._index_path, "rb") as fh:
                self._state = pickle.load(fh)
            logger.info(
                "Loaded BM25 index from '%s' (%d chunks).",
                self._index_path,
                len(self._state.chunks),
            )
            self._rebuild_bm25()
        except Exception as exc:
            logger.error(
                "Failed to load BM25 index from '%s': %s. Starting fresh.",
                self._index_path,
                exc,
                exc_info=True,
            )
            self._state = _IndexState()
            self._bm25 = None

    def _save_index(self) -> None:
        """Persist the current index state to disk."""
        if self._state is None:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self._index_path)), exist_ok=True)
        try:
            with open(self._index_path, "wb") as fh:
                pickle.dump(self._state, fh, protocol=pickle.HIGHEST_PROTOCOL)
            logger.debug(
                "Saved BM25 index to '%s' (%d chunks).",
                self._index_path,
                len(self._state.chunks),
            )
        except Exception as exc:
            logger.error("Failed to save BM25 index: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # BM25 model rebuild
    # ------------------------------------------------------------------

    def _rebuild_bm25(self) -> None:
        """Reconstruct the BM25Okapi model from the current corpus."""
        if not self._state or not self._state.tokenized_corpus:
            self._bm25 = None
            return

        try:
            from rank_bm25 import BM25Okapi  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required. Install it with: pip install rank-bm25"
            ) from exc

        self._bm25 = BM25Okapi(self._state.tokenized_corpus)
        logger.debug("BM25 model rebuilt with %d documents.", len(self._state.tokenized_corpus))

    # ------------------------------------------------------------------
    # Ensure state is loaded
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._state is None:
            self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[dict[str, Any]]) -> None:
        """
        Build the BM25 index from scratch from a list of chunk dicts.

        Each dict must contain: ``chunk_id``, ``doc_id``, ``text``,
        and optionally ``metadata``.

        This *replaces* any existing index.
        """
        state = _IndexState()
        for chunk in chunks:
            tokens = self.tokenize(chunk.get("text", ""))
            state.chunks.append(chunk)
            state.tokenized_corpus.append(tokens)

        self._state = state
        self._rebuild_bm25()
        self._save_index()
        logger.info("Built BM25 index with %d chunks.", len(state.chunks))

    def add_documents(self, chunks: list[dict[str, Any]]) -> None:
        """
        Incrementally add chunks to the existing index.

        Internally the BM25 model is rebuilt because rank_bm25 does not
        support incremental updates.  Duplicate chunk_ids are overwritten.

        Parameters
        ----------
        chunks:
            New chunk dicts to add.  Each must have ``chunk_id``, ``doc_id``,
            ``text``, and optionally ``metadata``.
        """
        self._ensure_loaded()
        assert self._state is not None

        # Build a map of existing chunks for dedup
        existing: dict[str, int] = {
            c["chunk_id"]: i for i, c in enumerate(self._state.chunks)
        }

        for chunk in chunks:
            tokens = self.tokenize(chunk.get("text", ""))
            cid = chunk.get("chunk_id", "")
            if cid in existing:
                idx = existing[cid]
                self._state.chunks[idx] = chunk
                self._state.tokenized_corpus[idx] = tokens
            else:
                existing[cid] = len(self._state.chunks)
                self._state.chunks.append(chunk)
                self._state.tokenized_corpus.append(tokens)

        self._rebuild_bm25()
        self._save_index()
        logger.info("BM25 index updated: total %d chunks.", len(self._state.chunks))

    def remove_document(self, doc_id: str) -> int:
        """
        Remove all chunks belonging to ``doc_id`` and rebuild the index.

        Returns
        -------
        int
            Number of chunks removed.
        """
        self._ensure_loaded()
        assert self._state is not None

        original_count = len(self._state.chunks)
        filtered_chunks = []
        filtered_corpus = []

        for chunk, tokens in zip(self._state.chunks, self._state.tokenized_corpus):
            if chunk.get("doc_id") != doc_id:
                filtered_chunks.append(chunk)
                filtered_corpus.append(tokens)

        self._state.chunks = filtered_chunks
        self._state.tokenized_corpus = filtered_corpus

        removed = original_count - len(filtered_chunks)
        if removed:
            self._rebuild_bm25()
            self._save_index()
            logger.info("Removed %d chunks for doc_id=%r from BM25 index.", removed, doc_id)
        else:
            logger.info("remove_document: no chunks found for doc_id=%r.", doc_id)

        return removed

    def search(self, query: str, n_results: int = 10) -> list[BM25Result]:
        """
        Search the BM25 index for chunks relevant to ``query``.

        Parameters
        ----------
        query:
            The search query string.
        n_results:
            Maximum number of results to return.

        Returns
        -------
        list[BM25Result]
            Results sorted by descending BM25 score.  Returns ``[]`` if
            the index is empty or the query is blank.
        """
        self._ensure_loaded()

        if not query or not query.strip():
            logger.debug("BM25 search called with empty query.")
            return []

        if self._bm25 is None or not self._state or not self._state.chunks:
            logger.debug("BM25 index is empty; returning [].")
            return []

        tokens = self.tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Pair (score, index), sort descending, take top n_results
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:n_results]

        results: list[BM25Result] = []
        for idx, score in ranked:
            if score <= 0.0:
                break  # BM25 score of 0 means no keyword overlap
            chunk = self._state.chunks[idx]
            results.append(
                BM25Result(
                    chunk_id=str(chunk.get("chunk_id", "")),
                    doc_id=str(chunk.get("doc_id", "")),
                    text=str(chunk.get("text", "")),
                    score=float(score),
                    metadata=dict(chunk.get("metadata", {})),
                )
            )

        return results

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._state.chunks) if self._state else 0

    def __repr__(self) -> str:
        n = len(self._state.chunks) if self._state else "?"
        return f"BM25Retriever(index_path={self._index_path!r}, chunks={n})"
