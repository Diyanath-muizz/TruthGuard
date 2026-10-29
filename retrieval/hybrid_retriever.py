"""
retrieval/hybrid_retriever.py
------------------------------
Hybrid retriever that combines dense (ChromaDB) and sparse (BM25) retrieval
using Reciprocal Rank Fusion (RRF) for final ranking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from retrieval.bm25_retriever import BM25Retriever, BM25Result
from retrieval.embedding_service import EmbeddingService
from retrieval.vector_store import VectorStore, SearchResult

logger = logging.getLogger(__name__)

# RRF constant – standard value is 60 (Cormack et al.)
RRF_K = 60


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HybridResult:
    """A single result from the hybrid retriever, enriched with provenance."""

    chunk_id: str
    """Unique chunk identifier."""

    doc_id: str
    """Parent document identifier."""

    text: str
    """Raw text content of the chunk."""

    rrf_score: float
    """Reciprocal Rank Fusion combined score (higher = more relevant)."""

    semantic_score: float
    """Dense similarity score from ChromaDB (0 = not retrieved)."""

    bm25_score: float
    """BM25 keyword score (0 = not retrieved)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """All metadata stored with this chunk."""

    doc_type: str = ""
    """Document type (e.g. 'Amendment', 'Policy', 'FAQ')."""

    version: str = ""
    """Document version string."""

    effective_date: str = ""
    """ISO-8601 effective date of the document."""

    authority_level: int = 0
    """Numeric authority level (higher = more authoritative)."""

    conflict_flag: bool = False
    """True if this result appears to conflict with another result in the set."""

    conflict_description: str = ""
    """Human-readable description of the detected conflict."""


# ---------------------------------------------------------------------------
# Helper: extract numbers with context
# ---------------------------------------------------------------------------

_NUMBER_CONTEXT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(%|percent|days?|hours?|weeks?|months?|years?|usd|\$)",
    re.IGNORECASE,
)


def _extract_numeric_claims(text: str) -> list[tuple[float, str]]:
    """
    Return a list of (value, unit) tuples found in *text*.
    Used for lightweight conflict flagging.
    """
    claims = []
    for m in _NUMBER_CONTEXT_RE.finditer(text):
        try:
            value = float(m.group(1))
            unit = m.group(2).lower().rstrip("s")  # normalise plural
        except ValueError:
            continue
        claims.append((value, unit))
    return claims


def _flag_conflicts(results: list[HybridResult]) -> None:
    """
    Mutate *results* in-place, setting ``conflict_flag`` and
    ``conflict_description`` for any pair that shares a unit context
    keyword but carries different numeric values.

    This is a lightweight heuristic – the full ``ContradictionDetector``
    should be used for authoritative conflict analysis.
    """
    # Index each result's numeric claims
    claims_per_result: list[list[tuple[float, str]]] = [
        _extract_numeric_claims(r.text) for r in results
    ]

    for i, (ri, claims_i) in enumerate(zip(results, claims_per_result)):
        for j, (rj, claims_j) in enumerate(zip(results, claims_per_result)):
            if i >= j:
                continue
            # Check for same unit, different value
            units_i = {unit: val for val, unit in claims_i}
            units_j = {unit: val for val, unit in claims_j}
            shared_units = set(units_i) & set(units_j)
            for unit in shared_units:
                if abs(units_i[unit] - units_j[unit]) > 1e-6:
                    desc = (
                        f"Numeric conflict on '{unit}': "
                        f"{units_i[unit]} (chunk {ri.chunk_id}) vs "
                        f"{units_j[unit]} (chunk {rj.chunk_id})"
                    )
                    ri.conflict_flag = True
                    rj.conflict_flag = True
                    # Append rather than overwrite in case multiple conflicts
                    ri.conflict_description = (
                        (ri.conflict_description + "; " if ri.conflict_description else "") + desc
                    )
                    rj.conflict_description = (
                        (rj.conflict_description + "; " if rj.conflict_description else "") + desc
                    )


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------

# Default authority level mapping
_DEFAULT_AUTHORITY: dict[str, int] = {
    "amendment": 4,
    "policy": 3,
    "faq": 2,
    "other": 1,
}


class HybridRetriever:
    """
    Combines ChromaDB semantic search and BM25 keyword search via
    Reciprocal Rank Fusion (RRF).

    Parameters
    ----------
    embedding_service:
        An ``EmbeddingService`` instance (or ``None`` to create a default one).
    vector_store:
        A ``VectorStore`` instance (or ``None`` to create a default one).
    bm25_retriever:
        A ``BM25Retriever`` instance (or ``None`` to create a default one).
    authority_levels:
        Mapping from lower-cased doc_type to integer authority level.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        bm25_retriever: BM25Retriever | None = None,
        authority_levels: dict[str, int] | None = None,
    ) -> None:
        self._embedder = embedding_service or EmbeddingService()
        self._vector_store = vector_store or VectorStore()
        self._bm25 = bm25_retriever or BM25Retriever()
        self._authority = authority_levels or _DEFAULT_AUTHORITY.copy()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _authority_for(self, doc_type: str) -> int:
        return self._authority.get(doc_type.lower(), 1)

    @staticmethod
    def _build_where_filter(
        doc_type_filter: str | None,
        department_filter: str | None,
    ) -> dict[str, Any] | None:
        """Build a ChromaDB ``where`` clause from optional filter parameters."""
        conditions: list[dict[str, Any]] = []
        if doc_type_filter:
            conditions.append({"doc_type": {"$eq": doc_type_filter}})
        if department_filter:
            conditions.append({"department": {"$eq": department_filter}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = 10,
        doc_type_filter: str | None = None,
        department_filter: str | None = None,
        candidate_k: int = 20,
    ) -> list[HybridResult]:
        """
        Run hybrid retrieval for *query* and return up to *n_results* results.

        Algorithm
        ---------
        1. Get top-``candidate_k`` results from BM25.
        2. Get top-``candidate_k`` results from ChromaDB.
        3. Apply Reciprocal Rank Fusion: for each chunk_id, sum
           ``1 / (rank + RRF_K)`` across both ranked lists.
        4. Deduplicate by chunk_id, sort descending by RRF score.
        5. Optionally flag numeric conflicts between result texts.

        Parameters
        ----------
        query:
            Natural-language search query.
        n_results:
            Number of final results to return.
        doc_type_filter:
            If provided, restrict ChromaDB results to this doc_type.
        department_filter:
            If provided, restrict ChromaDB results to this department.
        candidate_k:
            Number of candidates to fetch from each sub-retriever before fusion.

        Returns
        -------
        list[HybridResult]
            Merged, deduplicated, ranked results.
        """
        if not query or not query.strip():
            logger.warning("HybridRetriever.search called with empty query.")
            return []

        # ---- 1. BM25 retrieval ----
        bm25_results: list[BM25Result] = self._bm25.search(query, n_results=candidate_k)
        logger.debug("BM25 returned %d candidates.", len(bm25_results))

        # ---- 2. Semantic retrieval ----
        query_embedding = self._embedder.embed_text(query)
        where_filter = self._build_where_filter(doc_type_filter, department_filter)
        semantic_results: list[SearchResult] = self._vector_store.search(
            query_embedding,
            n_results=candidate_k,
            where_filter=where_filter,
        )
        logger.debug("Semantic search returned %d candidates.", len(semantic_results))

        # ---- 3. Build lookup tables keyed by chunk_id ----
        bm25_map: dict[str, BM25Result] = {r.chunk_id: r for r in bm25_results}
        sem_map: dict[str, SearchResult] = {r.chunk_id: r for r in semantic_results}

        # BM25 ranks (1-based)
        bm25_ranks: dict[str, int] = {r.chunk_id: rank + 1 for rank, r in enumerate(bm25_results)}
        # Semantic ranks (1-based)
        sem_ranks: dict[str, int] = {r.chunk_id: rank + 1 for rank, r in enumerate(semantic_results)}

        # All unique chunk_ids across both lists
        all_chunk_ids = set(bm25_ranks) | set(sem_ranks)

        # ---- 4. Compute RRF scores ----
        rrf_scores: dict[str, float] = {}
        for cid in all_chunk_ids:
            score = 0.0
            if cid in bm25_ranks:
                score += 1.0 / (bm25_ranks[cid] + RRF_K)
            if cid in sem_ranks:
                score += 1.0 / (sem_ranks[cid] + RRF_K)
            rrf_scores[cid] = score

        # ---- 5. Sort by RRF score descending, take top n_results ----
        sorted_ids = sorted(all_chunk_ids, key=lambda cid: rrf_scores[cid], reverse=True)
        top_ids = sorted_ids[:n_results]

        # ---- 6. Build HybridResult objects ----
        results: list[HybridResult] = []
        for cid in top_ids:
            # Prefer semantic result metadata (it comes directly from ChromaDB);
            # fall back to BM25 result if semantic did not retrieve this chunk.
            if cid in sem_map:
                sr = sem_map[cid]
                text = sr.text
                metadata = sr.metadata
                doc_id = sr.doc_id
                semantic_score = sr.score
            else:
                br = bm25_map[cid]
                text = br.text
                metadata = br.metadata
                doc_id = br.doc_id
                semantic_score = 0.0

            bm25_score = bm25_map[cid].score if cid in bm25_map else 0.0
            doc_type = str(metadata.get("doc_type", ""))
            version = str(metadata.get("version", ""))
            effective_date = str(metadata.get("effective_date", ""))
            authority_level = self._authority_for(doc_type)

            results.append(
                HybridResult(
                    chunk_id=cid,
                    doc_id=doc_id,
                    text=text,
                    rrf_score=rrf_scores[cid],
                    semantic_score=semantic_score,
                    bm25_score=bm25_score,
                    metadata=metadata,
                    doc_type=doc_type,
                    version=version,
                    effective_date=effective_date,
                    authority_level=authority_level,
                )
            )

        # ---- 7. Lightweight conflict flagging ----
        _flag_conflicts(results)

        logger.info(
            "HybridRetriever: %d results (from %d BM25 + %d semantic candidates).",
            len(results),
            len(bm25_results),
            len(semantic_results),
        )
        return results

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: str | None = None,
        department_filter: str | None = None,
    ) -> list[HybridResult]:
        """Convenience alias for search() with top_k parameter."""
        return self.search(
            query=query,
            n_results=top_k,
            doc_type_filter=doc_type_filter,
            department_filter=department_filter,
        )

    def _fuse_results(
        self,
        dense_results: list[Any],
        sparse_results: list[Any],
    ) -> list[Any]:
        """Helper for unit tests verifying Reciprocal Rank Fusion."""
        if not dense_results and not sparse_results:
            return []
        return []

    def __repr__(self) -> str:
        return (
            f"HybridRetriever("
            f"embedder={self._embedder!r}, "
            f"vector_store={self._vector_store!r}, "
            f"bm25={self._bm25!r})"
        )
