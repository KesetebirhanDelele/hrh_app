"""Hybrid retriever combining vector search and BM25 via Reciprocal Rank Fusion,
with optional Maximal Marginal Relevance deduplication."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.retrieve.bm25 import BM25Index
from app.retrieve.vector import VectorIndex


class HybridRetriever:
    """Two-stage retriever: RRF fusion of vector + BM25, then MMR deduplication.

    Parameters
    ----------
    vector_index : VectorIndex
        Pre-built numpy vector index.
    bm25_index : BM25Index
        Pre-built BM25 keyword index built from the same snippet list.
    api_key : str
        OpenAI API key used to embed queries.
    embedding_model : str
        OpenAI embedding model name (default: text-embedding-3-small).
    """

    def __init__(
        self,
        vector_index: VectorIndex,
        bm25_index: BM25Index,
        api_key: str,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self._vec = vector_index
        self._bm25 = bm25_index
        self._api_key = api_key
        self._model = embedding_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int,
        rrf_k: int = 60,
        mmr: bool = True,
        mmr_lambda: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Retrieve *top_k* snippets for *query*.

        Steps:
        1. Embed query via OpenAI.
        2. Vector search → ranked list (top_k * 3 candidates).
        3. BM25 search → ranked list (top_k * 3 candidates).
        4. RRF fusion — score = Σ 1 / (rrf_k + rank).
        5. Take top_k * 2 by RRF score.
        6. MMR deduplication (if *mmr* is True) to reduce redundant chunks.
        7. Return top_k results, each with a 'score' field.
        """
        from app.ingest.indexer import _embed_texts  # avoid circular import at module level

        # Step 1: embed query
        query_embedding: List[float] = _embed_texts([query], self._api_key, self._model)[0]

        pool_size = top_k * 3

        # Step 2: vector results
        vec_results = self._vec.search(query_embedding, top_k=pool_size)

        # Step 3: BM25 results
        bm25_results = self._bm25.search(query, top_k=pool_size)

        # Step 4: RRF fusion
        candidates = self._rrf_merge(vec_results, bm25_results, rrf_k=rrf_k, top_n=top_k * 2)

        if not candidates:
            return []

        # Step 5: MMR deduplication
        if mmr and len(candidates) > top_k:
            candidates = self._mmr(candidates, query_embedding, top_k=top_k, lambda_=mmr_lambda)
        else:
            candidates = candidates[:top_k]

        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_merge(
        vec_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        rrf_k: int,
        top_n: int,
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion over two ranked lists.

        Identifies snippets by (source_id, locator) to handle duplicates
        across the two lists. Attaches combined 'score' = RRF score.
        """
        rrf_scores: Dict[tuple, float] = {}
        # Map key → snippet dict (first occurrence wins for metadata)
        snippet_map: Dict[tuple, Dict[str, Any]] = {}

        def _key(s: Dict[str, Any]) -> tuple:
            return (s.get("source_id", ""), s.get("locator", ""), s.get("text", "")[:40])

        for rank, snip in enumerate(vec_results, start=1):
            k = _key(snip)
            rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (rrf_k + rank)
            snippet_map.setdefault(k, snip)

        for rank, snip in enumerate(bm25_results, start=1):
            k = _key(snip)
            rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (rrf_k + rank)
            snippet_map.setdefault(k, snip)

        sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)

        results: List[Dict[str, Any]] = []
        for k in sorted_keys[:top_n]:
            snip = {**snippet_map[k], "score": round(rrf_scores[k], 6)}
            results.append(snip)
        return results

    @staticmethod
    def _mmr(
        candidates: List[Dict[str, Any]],
        query_embedding: List[float],
        top_k: int,
        lambda_: float,
    ) -> List[Dict[str, Any]]:
        """Maximal Marginal Relevance deduplication.

        Greedily selects snippets to maximise:
            lambda_ * sim(snippet, query) - (1 - lambda_) * max_sim(snippet, selected)

        Requires candidate dicts to have an 'embedding' key OR the VectorIndex
        must have returned normalised vectors. Since we strip embeddings from
        VectorIndex results but keep them in the candidate's source, we fall back
        to using the RRF 'score' as the relevance proxy when embeddings are absent.
        """
        # Gather embeddings where available; otherwise use RRF score as proxy
        has_embeddings = all("embedding" in c for c in candidates)

        if has_embeddings:
            cand_matrix = np.array([c["embedding"] for c in candidates], dtype=np.float32)
            norms = np.linalg.norm(cand_matrix, axis=1, keepdims=True)
            cand_matrix = cand_matrix / np.clip(norms, 1e-9, None)

            q = np.array(query_embedding, dtype=np.float32)
            q_norm = float(np.linalg.norm(q))
            if q_norm > 1e-9:
                q = q / q_norm
            query_sims = cand_matrix @ q  # shape (N,)
        else:
            # Proxy: normalise RRF scores to [0, 1] range
            scores = np.array([c.get("score", 0.0) for c in candidates], dtype=np.float32)
            max_s = scores.max()
            if max_s > 0:
                query_sims = scores / max_s
            else:
                query_sims = scores
            cand_matrix = None

        n = len(candidates)
        selected_indices: List[int] = []
        remaining = list(range(n))

        while remaining and len(selected_indices) < top_k:
            if not selected_indices:
                # Pick the highest-relevance candidate first
                best_idx = max(remaining, key=lambda i: float(query_sims[i]))
            else:
                if cand_matrix is not None:
                    sel_matrix = cand_matrix[selected_indices]  # shape (S, D)
                    # Pairwise similarity: remaining × selected
                    rem_matrix = cand_matrix[remaining]  # shape (R, D)
                    sim_to_sel = rem_matrix @ sel_matrix.T  # shape (R, S)
                    max_sim_to_sel = sim_to_sel.max(axis=1)  # shape (R,)
                else:
                    max_sim_to_sel = np.zeros(len(remaining), dtype=np.float32)

                rem_query_sims = query_sims[remaining]
                mmr_scores = lambda_ * rem_query_sims - (1 - lambda_) * max_sim_to_sel
                best_idx = remaining[int(np.argmax(mmr_scores))]

            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        return [candidates[i] for i in selected_indices]
