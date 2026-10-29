"""
retrieval/vector_store.py
--------------------------
ChromaDB-backed persistent vector store for TruthGuard.
Stores document chunks with their embeddings and metadata.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from documents.chunking import TextChunk  # pragma: no cover

logger = logging.getLogger(__name__)

COLLECTION_NAME = "truthguard_chunks"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single result returned from a vector similarity search."""

    chunk_id: str
    """Unique identifier of the chunk (matches the ID used in ChromaDB)."""

    doc_id: str
    """Identifier of the parent document this chunk belongs to."""

    text: str
    """The raw text content of the chunk."""

    score: float
    """Cosine similarity / distance score returned by ChromaDB.
    ChromaDB returns *distance* (lower = more similar) when using
    ``cosine`` space.  We convert to a similarity score in [0, 1]."""

    metadata: dict[str, Any]
    """All metadata fields stored alongside this chunk."""


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """
    Thin wrapper around a persistent ChromaDB collection.

    The underlying ChromaDB client and collection are initialised lazily
    on the first operation, so constructing a ``VectorStore`` is cheap
    and does not open any file handles.

    Configuration
    -------------
    ``persist_directory`` is resolved in this order:
      1. Constructor argument.
      2. ``CHROMA_PERSIST_DIR`` environment variable.
      3. Default ``"data/chroma"``.
    """

    DEFAULT_PERSIST_DIR = "data/chroma"

    def __init__(self, persist_directory: str | None = None) -> None:
        self._persist_dir: str = (
            persist_directory
            or os.getenv("CHROMA_PERSIST_DIR", self.DEFAULT_PERSIST_DIR)
        )
        self._client = None
        self._collection = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_collection(self):
        """Lazily initialise the ChromaDB client and collection."""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb  # type: ignore
            from chromadb.config import Settings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "chromadb is required. Install it with: pip install chromadb"
            ) from exc

        os.makedirs(self._persist_dir, exist_ok=True)
        logger.info("Initialising ChromaDB at '%s'.", self._persist_dir)

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # get_or_create handles the "already exists" case on restart.
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection '%s' ready (%d chunks).",
            COLLECTION_NAME,
            self._collection.count(),
        )
        return self._collection

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        """
        Convert ChromaDB cosine *distance* in [0, 2] to similarity in [0, 1].
        ChromaDB cosine distance = 1 - cosine_similarity, so:
            similarity = 1 - distance
        Values are clamped to [0, 1] for safety.
        """
        return max(0.0, min(1.0, 1.0 - distance))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        chunks: list[Any],  # list[TextChunk] at runtime
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """
        Upsert chunks into the collection.

        Using ``upsert`` prevents duplicate entries when the same document
        is ingested more than once (e.g. after a re-upload).

        Parameters
        ----------
        chunks:
            ``TextChunk`` objects (from ``documents.chunking``).
            Must expose ``.chunk_id`` and ``.text`` attributes.
        embeddings:
            Parallel list of dense embedding vectors.
        metadatas:
            Parallel list of metadata dicts (must be flat: str/int/float/bool
            values only – ChromaDB does not support nested objects).
        """
        if not chunks:
            logger.debug("add_chunks called with empty list – nothing to do.")
            return

        if len(chunks) != len(embeddings) or len(chunks) != len(metadatas):
            raise ValueError(
                "chunks, embeddings, and metadatas must have the same length. "
                f"Got {len(chunks)}, {len(embeddings)}, {len(metadatas)}."
            )

        collection = self._ensure_collection()

        ids = [str(c.chunk_id) for c in chunks]
        documents = [c.text for c in chunks]

        # Sanitise metadata: ChromaDB requires flat dicts with scalar values.
        clean_metas: list[dict[str, Any]] = []
        for meta in metadatas:
            clean: dict[str, Any] = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                elif v is None:
                    clean[k] = ""
                else:
                    clean[k] = str(v)
            clean_metas.append(clean)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=clean_metas,
        )
        logger.info("Upserted %d chunks into ChromaDB.", len(ids))

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Search for the most similar chunks to ``query_embedding``.

        Parameters
        ----------
        query_embedding:
            Dense query vector (same dimensionality as stored embeddings).
        n_results:
            Maximum number of results to return.
        where_filter:
            Optional ChromaDB ``where`` clause for metadata pre-filtering.
            Example: ``{"doc_type": {"$eq": "Policy"}}``

        Returns
        -------
        list[SearchResult]
            Results sorted by descending similarity score.
        """
        collection = self._ensure_collection()
        total = collection.count()
        if total == 0:
            logger.debug("search: collection is empty, returning [].")
            return []

        # Clamp n_results to available documents.
        effective_n = min(n_results, total)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": effective_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            kwargs["where"] = where_filter

        try:
            raw = collection.query(**kwargs)
        except Exception as exc:
            logger.error("ChromaDB query failed: %s", exc, exc_info=True)
            return []

        results: list[SearchResult] = []
        ids_list = raw.get("ids", [[]])[0]
        docs_list = raw.get("documents", [[]])[0]
        metas_list = raw.get("metadatas", [[]])[0]
        distances_list = raw.get("distances", [[]])[0]

        for chunk_id, document, meta, distance in zip(
            ids_list, docs_list, metas_list, distances_list
        ):
            doc_id = str(meta.get("doc_id", ""))
            score = self._distance_to_similarity(distance)
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=document,
                    score=score,
                    metadata=meta,
                )
            )

        return results

    def delete_document(self, doc_id: str) -> int:
        """
        Delete all chunks belonging to ``doc_id`` from the collection.

        Parameters
        ----------
        doc_id:
            The document identifier whose chunks should be removed.

        Returns
        -------
        int
            Number of chunks deleted.
        """
        collection = self._ensure_collection()
        try:
            existing = collection.get(
                where={"doc_id": {"$eq": doc_id}},
                include=["documents"],
            )
            ids_to_delete = existing.get("ids", [])
            if not ids_to_delete:
                logger.info("delete_document: no chunks found for doc_id=%r.", doc_id)
                return 0
            collection.delete(ids=ids_to_delete)
            logger.info(
                "delete_document: deleted %d chunks for doc_id=%r.",
                len(ids_to_delete),
                doc_id,
            )
            return len(ids_to_delete)
        except Exception as exc:
            logger.error(
                "delete_document failed for doc_id=%r: %s", doc_id, exc, exc_info=True
            )
            return 0

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """
        Retrieve a single chunk by its ID.

        Returns
        -------
        dict or None
            A dict with keys ``chunk_id``, ``text``, ``metadata``,
            or ``None`` if not found.
        """
        collection = self._ensure_collection()
        try:
            result = collection.get(
                ids=[chunk_id],
                include=["documents", "metadatas"],
            )
            ids = result.get("ids", [])
            if not ids:
                return None
            return {
                "chunk_id": ids[0],
                "text": result["documents"][0],
                "metadata": result["metadatas"][0],
            }
        except Exception as exc:
            logger.error("get_chunk failed for chunk_id=%r: %s", chunk_id, exc, exc_info=True)
            return None

    def count(self) -> int:
        """Return total number of chunks stored in the collection."""
        try:
            collection = self._ensure_collection()
            return collection.count()
        except Exception as exc:
            logger.error("count() failed: %s", exc, exc_info=True)
            return 0

    def reset(self) -> None:
        """Delete all chunks from the collection."""
        try:
            client = self._ensure_client()
            client.delete_collection(COLLECTION_NAME)
            self._collection = None
            logger.info("VectorStore collection '%s' reset successfully.", COLLECTION_NAME)
        except Exception as exc:
            logger.warning("VectorStore reset failed: %s", exc)

    def __repr__(self) -> str:
        return (
            f"VectorStore(persist_dir={self._persist_dir!r}, "
            f"collection={COLLECTION_NAME!r})"
        )
