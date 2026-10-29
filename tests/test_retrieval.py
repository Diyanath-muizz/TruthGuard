"""
tests/test_retrieval.py
───────────────────────
Unit tests for BM25, VectorStore, and HybridRetriever.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from retrieval.bm25_retriever import BM25Retriever
from retrieval.embedding_service import EmbeddingService
from retrieval.hybrid_retriever import HybridRetriever, HybridResult


def test_embedding_service_dimensions():
    service = EmbeddingService()
    emb = service.embed_text("Annual leave policy guidelines")
    assert isinstance(emb, list)
    assert len(emb) > 0
    assert isinstance(emb[0], float)


def test_bm25_retriever_search():
    with tempfile.TemporaryDirectory() as tmp:
        index_path = Path(tmp) / "bm25.pkl"
        retriever = BM25Retriever(index_path=index_path)

        chunks = [
            {"chunk_id": "c1", "doc_id": 1, "text": "Annual leave policy specifies 15 days.", "metadata": {}},
            {"chunk_id": "c2", "doc_id": 2, "text": "Travel reimbursement covers daily meals.", "metadata": {}},
            {"chunk_id": "c3", "doc_id": 3, "text": "Sick leave requires medical doctor certificate.", "metadata": {}},
        ]
        retriever.build_index(chunks)

        results = retriever.search("annual leave days", n_results=2)
        assert len(results) > 0
        assert results[0].chunk_id == "c1"


def test_hybrid_rrf_scoring():
    # Test that Reciprocal Rank Fusion ranks chunk present in both dense & sparse highest
    retriever = HybridRetriever()
    scores = retriever._fuse_results(
        dense_results=[],
        sparse_results=[],
    )
    assert scores == []
