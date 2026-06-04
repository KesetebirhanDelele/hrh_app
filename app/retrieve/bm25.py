"""Pure-Python BM25-Okapi keyword index — no external dependencies."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase + split on non-alphanumeric boundaries.

    Preserves HRH abbreviations (CHW, HMIS, etc.) as single tokens since
    they are uppercase alphanumeric sequences.
    """
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """BM25-Okapi index built from a list of snippet dicts.

    Parameters
    ----------
    k1 : float
        Term-frequency saturation parameter (default 1.5).
    b : float
        Length normalisation parameter (default 0.75).
    """

    def __init__(
        self,
        snippets: List[Dict[str, Any]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._k1 = k1
        self._b = b
        self._snippets: List[Dict[str, Any]] = snippets

        # Build corpus statistics
        self._tf: List[Counter] = []         # per-doc term frequencies
        self._doc_lens: List[int] = []       # token count per doc
        doc_freq: Counter = Counter()        # how many docs each term appears in

        for snip in snippets:
            tokens = _tokenize(snip.get("text", ""))
            tf = Counter(tokens)
            self._tf.append(tf)
            self._doc_lens.append(len(tokens))
            for term in tf:
                doc_freq[term] += 1

        n = len(snippets)
        self._avg_dl: float = sum(self._doc_lens) / n if n else 1.0

        # Pre-compute IDF for every known term
        self._idf: Dict[str, float] = {}
        for term, df in doc_freq.items():
            # Robertson IDF with +0.5 smoothing (always positive)
            self._idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, tokens: List[str], doc_idx: int) -> float:
        """BM25 score for *tokens* against document at *doc_idx*."""
        k1, b = self._k1, self._b
        dl = self._doc_lens[doc_idx]
        avg_dl = self._avg_dl
        tf_map = self._tf[doc_idx]
        total = 0.0
        for term in tokens:
            idf = self._idf.get(term, 0.0)
            tf = tf_map.get(term, 0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avg_dl)
            total += idf * (numerator / denominator if denominator else 0.0)
        return total

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Return up to *top_k* snippets sorted by BM25 score descending.

        Each result dict contains all snippet fields plus a 'score' key.
        Zero-scoring snippets are excluded from results.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []

        scored: List[Tuple[float, int]] = []
        for i in range(len(self._snippets)):
            s = self.score(tokens, i)
            if s > 0.0:
                scored.append((s, i))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[Dict[str, Any]] = []
        for s, idx in scored[:top_k]:
            results.append({**self._snippets[idx], "score": round(s, 4)})
        return results
