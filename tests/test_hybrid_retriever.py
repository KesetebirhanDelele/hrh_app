"""Tests for app.retrieve.retriever.HybridRetriever."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.retrieve.bm25 import BM25Index
from app.retrieve.retriever import HybridRetriever
from app.retrieve.vector import VectorIndex


def _snip(source_id: str, text: str, embedding: List[float], locator: str = "p.1") -> Dict[str, Any]:
    return {
        "source_id": source_id,
        "source_title": f"Source {source_id}",
        "locator": locator,
        "text": text,
        "type": "text",
        "embedding": embedding,
    }


def _build_retriever(snippets: List[Dict[str, Any]], api_key: str = "fake") -> HybridRetriever:
    vec = VectorIndex(snippets)
    bm25 = BM25Index(snippets)
    return HybridRetriever(vec, bm25, api_key=api_key)


class TestRRFMerge:
    def test_snippet_top_in_both_ranks_highest(self) -> None:
        # SRC1 is rank-1 in both lists; SRC2 only in vector; SRC3 only in BM25
        vec_results = [
            {"source_id": "SRC1", "locator": "p.1", "text": "a", "score": 0.9},
            {"source_id": "SRC2", "locator": "p.2", "text": "b", "score": 0.5},
        ]
        bm25_results = [
            {"source_id": "SRC1", "locator": "p.1", "text": "a", "score": 10.0},
            {"source_id": "SRC3", "locator": "p.3", "text": "c", "score": 5.0},
        ]
        merged = HybridRetriever._rrf_merge(vec_results, bm25_results, rrf_k=60, top_n=3)
        assert merged[0]["source_id"] == "SRC1"

    def test_rrf_score_field_present(self) -> None:
        vec = [{"source_id": "SRC1", "locator": "p.1", "text": "x", "score": 1.0}]
        bm25: List[Dict] = []
        merged = HybridRetriever._rrf_merge(vec, bm25, rrf_k=60, top_n=5)
        assert "score" in merged[0]

    def test_deduplication_across_lists(self) -> None:
        # Same snippet appears in both lists — should appear only once in merged output
        vec = [{"source_id": "SRC1", "locator": "p.1", "text": "x", "score": 0.9}]
        bm25 = [{"source_id": "SRC1", "locator": "p.1", "text": "x", "score": 5.0}]
        merged = HybridRetriever._rrf_merge(vec, bm25, rrf_k=60, top_n=5)
        assert len(merged) == 1

    def test_top_n_limit(self) -> None:
        vec = [{"source_id": f"SRC{i}", "locator": "p.1", "text": f"t{i}", "score": 1.0} for i in range(5)]
        bm25: List[Dict] = []
        merged = HybridRetriever._rrf_merge(vec, bm25, rrf_k=60, top_n=3)
        assert len(merged) == 3


class TestMMR:
    def _unit_vec(self, dim: int, idx: int) -> List[float]:
        v = [0.0] * dim
        v[idx] = 1.0
        return v

    def test_mmr_removes_near_duplicate(self) -> None:
        # SRC1 and SRC2 are nearly identical; SRC3 is orthogonal (different topic).
        # With lambda_=0.3 (diversity-dominant) MMR should penalise SRC2 and prefer SRC3.
        snippets = [
            _snip("SRC1", "health workforce retention", [1.0, 0.0, 0.0, 0.0]),
            _snip("SRC2", "health workforce retention similar", [0.99, 0.14, 0.0, 0.0]),
            _snip("SRC3", "hospital budget finance", [0.0, 0.0, 1.0, 0.0]),
        ]
        candidates = [
            {**s, "score": 1.0 - i * 0.01} for i, s in enumerate(snippets)
        ]
        query_embedding = [1.0, 0.0, 0.0, 0.0]

        # lambda_=0.3 → diversity weighted at 70%; near-duplicate SRC2 gets penalised
        selected = HybridRetriever._mmr(candidates, query_embedding, top_k=2, lambda_=0.3)
        ids = [s["source_id"] for s in selected]
        assert "SRC1" in ids
        assert "SRC3" in ids
        assert "SRC2" not in ids

    def test_mmr_top_k_respected(self) -> None:
        snippets = [
            _snip(f"SRC{i}", f"text {i}", [float(i == j) for j in range(5)])
            for i in range(5)
        ]
        candidates = [{**s, "score": 1.0} for s in snippets]
        query_embedding = [1.0, 0.0, 0.0, 0.0, 0.0]
        selected = HybridRetriever._mmr(candidates, query_embedding, top_k=3, lambda_=0.7)
        assert len(selected) == 3

    def test_mmr_without_embeddings_uses_score_proxy(self) -> None:
        # When candidates have no 'embedding' key, MMR falls back to score-based selection
        candidates = [
            {"source_id": f"SRC{i}", "locator": "p.1", "text": f"t{i}", "score": float(5 - i)}
            for i in range(5)
        ]
        query_embedding = [1.0, 0.0]
        selected = HybridRetriever._mmr(candidates, query_embedding, top_k=3, lambda_=0.7)
        assert len(selected) == 3


class TestHybridRetrieverIntegration:
    """Integration tests using mocked OpenAI embedding calls."""

    def _snippets(self) -> List[Dict[str, Any]]:
        return [
            _snip("SRC1", "community health worker CHW training incentives", [1.0, 0.0, 0.0, 0.0]),
            _snip("SRC2", "hospital budget finance allocation reform", [0.0, 1.0, 0.0, 0.0]),
            _snip("SRC3", "nurse retention rural posting allowance", [0.0, 0.0, 1.0, 0.0]),
            _snip("SRC4", "health data quality HMIS reporting system", [0.0, 0.0, 0.0, 1.0]),
        ]

    @patch("app.ingest.indexer._embed_texts")
    def test_retrieve_returns_top_k(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        retriever = _build_retriever(self._snippets())
        results = retriever.retrieve("CHW training", top_k=2)
        assert len(results) == 2

    @patch("app.ingest.indexer._embed_texts")
    def test_vector_dominant_query_finds_correct_snippet(self, mock_embed: MagicMock) -> None:
        # Query embedding aligned with SRC1
        mock_embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        retriever = _build_retriever(self._snippets())
        results = retriever.retrieve("CHW community", top_k=4)
        ids = [r["source_id"] for r in results]
        assert ids[0] == "SRC1"

    @patch("app.ingest.indexer._embed_texts")
    def test_bm25_dominant_query_elevates_keyword_match(self, mock_embed: MagicMock) -> None:
        # Orthogonal embedding (so vector search is uninformative), but query has
        # a rare keyword that only SRC4 contains (HMIS)
        mock_embed.return_value = [[0.0, 0.0, 0.0, 0.0]]
        retriever = _build_retriever(self._snippets())
        results = retriever.retrieve("HMIS reporting", top_k=4)
        ids = [r["source_id"] for r in results]
        # BM25 should surface SRC4 (contains HMIS, reporting)
        assert "SRC4" in ids

    @patch("app.ingest.indexer._embed_texts")
    def test_no_embedding_key_in_results(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        retriever = _build_retriever(self._snippets())
        results = retriever.retrieve("health worker", top_k=2)
        for r in results:
            assert "embedding" not in r

    @patch("app.ingest.indexer._embed_texts")
    def test_score_field_present(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        retriever = _build_retriever(self._snippets())
        results = retriever.retrieve("health", top_k=2)
        for r in results:
            assert "score" in r


class TestVectorIndex:
    def test_search_ranks_correct_snippet_first(self) -> None:
        snippets = [
            _snip("SRC1", "staffing", [0.0, 1.0, 0.0, 0.0]),
            _snip("SRC2", "budget", [1.0, 0.0, 0.0, 0.0]),
            _snip("SRC3", "training", [0.5, 0.5, 0.0, 0.0]),
        ]
        idx = VectorIndex(snippets)
        results = idx.search([1.0, 0.0, 0.0, 0.0], top_k=3)
        assert results[0]["source_id"] == "SRC2"

    def test_no_embedding_in_results(self) -> None:
        snippets = [_snip("SRC1", "text", [1.0, 0.0])]
        idx = VectorIndex(snippets)
        results = idx.search([1.0, 0.0], top_k=1)
        assert "embedding" not in results[0]

    def test_top_k_limit(self) -> None:
        snippets = [_snip(f"SRC{i}", f"text {i}", [float(i == 0), float(i != 0)]) for i in range(10)]
        idx = VectorIndex(snippets)
        results = idx.search([1.0, 0.0], top_k=4)
        assert len(results) == 4

    def test_empty_snippets_raises(self) -> None:
        with pytest.raises(ValueError):
            VectorIndex([])
