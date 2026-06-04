"""Numpy-backed vector index for fast cosine similarity search."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


class VectorIndex:
    """In-memory vector index backed by a pre-normalised numpy matrix.

    Snippets are stored without their embedding arrays so that results can be
    returned directly without stripping large float lists from each dict.
    """

    def __init__(self, snippets: List[Dict[str, Any]]) -> None:
        if not snippets:
            raise ValueError("VectorIndex requires at least one snippet.")

        embeddings = [s["embedding"] for s in snippets]
        matrix = np.array(embeddings, dtype=np.float32)

        # Pre-normalise rows so search is a plain dot product
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-9, None)
        self._matrix: np.ndarray = matrix / norms  # shape (N, D)

        # Store snippets stripped of their (large) embedding vectors
        self._snippets: List[Dict[str, Any]] = [
            {k: v for k, v in s.items() if k != "embedding"} for s in snippets
        ]

    def search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Return up to *top_k* snippets sorted by cosine similarity descending.

        Each result dict contains all snippet fields plus a 'score' key.
        """
        q = np.array(query_embedding, dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm > 1e-9:
            q = q / norm

        scores: np.ndarray = self._matrix @ q  # shape (N,)

        k = min(top_k, len(self._snippets))
        # argpartition is O(N) vs argsort O(N log N) — faster for large indices
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results: List[Dict[str, Any]] = []
        for idx in top_indices:
            results.append({**self._snippets[idx], "score": round(float(scores[idx]), 4)})
        return results
