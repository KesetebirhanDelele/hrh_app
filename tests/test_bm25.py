"""Tests for app.retrieve.bm25.BM25Index."""

from __future__ import annotations

import pytest

from app.retrieve.bm25 import BM25Index, _tokenize


def _snip(source_id: str, text: str, locator: str = "p.1") -> dict:
    return {
        "source_id": source_id,
        "source_title": f"Source {source_id}",
        "locator": locator,
        "text": text,
        "type": "text",
    }


class TestTokenizer:
    def test_lowercases(self) -> None:
        assert _tokenize("CHW Training") == ["chw", "training"]

    def test_splits_on_punctuation(self) -> None:
        assert _tokenize("health-workers, retention.") == ["health", "workers", "retention"]

    def test_preserves_abbreviations(self) -> None:
        tokens = _tokenize("HMIS data quality")
        assert "hmis" in tokens

    def test_empty_string(self) -> None:
        assert _tokenize("") == []


class TestBM25Index:
    def _build(self, snippets: list[dict]) -> BM25Index:
        return BM25Index(snippets)

    def test_keyword_match_ranks_first(self) -> None:
        snippets = [
            _snip("SRC1", "community health workers training program"),
            _snip("SRC2", "hospital budget allocation and finance"),
            _snip("SRC3", "nurse retention rural incentives"),
        ]
        idx = self._build(snippets)
        results = idx.search("community health workers", top_k=3)
        assert results[0]["source_id"] == "SRC1"

    def test_rare_term_weighted_higher(self) -> None:
        # "retention" appears in only one snippet; "health" appears in two.
        # A query for the rare term should rank its snippet higher.
        snippets = [
            _snip("SRC1", "health workforce retention strategies"),
            _snip("SRC2", "health system financing reform"),
            _snip("SRC3", "health data quality improvement"),
        ]
        idx = self._build(snippets)
        results = idx.search("retention", top_k=3)
        assert results[0]["source_id"] == "SRC1"

    def test_empty_query_returns_empty(self) -> None:
        snippets = [_snip("SRC1", "some text")]
        idx = self._build(snippets)
        results = idx.search("", top_k=5)
        assert results == []

    def test_no_matching_snippets_excluded(self) -> None:
        snippets = [
            _snip("SRC1", "community health workers"),
            _snip("SRC2", "hospital budget finance"),
        ]
        idx = self._build(snippets)
        results = idx.search("retention", top_k=5)
        assert results == []

    def test_score_field_present(self) -> None:
        snippets = [_snip("SRC1", "health workforce planning")]
        idx = self._build(snippets)
        results = idx.search("workforce", top_k=1)
        assert len(results) == 1
        assert "score" in results[0]
        assert results[0]["score"] > 0

    def test_top_k_limit_respected(self) -> None:
        snippets = [_snip(f"SRC{i}", f"health worker {i} training") for i in range(10)]
        idx = self._build(snippets)
        results = idx.search("health worker training", top_k=3)
        assert len(results) <= 3

    def test_result_has_no_embedding_key(self) -> None:
        snippets = [_snip("SRC1", "health data")]
        idx = self._build(snippets)
        results = idx.search("health", top_k=1)
        assert "embedding" not in results[0]

    def test_multiple_query_terms_combined(self) -> None:
        snippets = [
            _snip("SRC1", "community health workers training incentives retention"),
            _snip("SRC2", "hospital budget financing"),
        ]
        idx = self._build(snippets)
        results = idx.search("retention training community", top_k=2)
        assert results[0]["source_id"] == "SRC1"

    def test_idf_scores_single_doc_corpus(self) -> None:
        # With one document, every term has idf > 0 (log(1.5/1.5 + 1) = log(2))
        snippets = [_snip("SRC1", "health workers")]
        idx = self._build(snippets)
        results = idx.search("health", top_k=1)
        assert len(results) == 1
