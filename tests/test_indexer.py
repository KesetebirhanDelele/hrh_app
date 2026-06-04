"""Tests for app.ingest.indexer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.ingest.indexer import (
    _cosine_similarity,
    _embed_texts,
    build_index,
    group_by_source,
    load_index,
    retrieve,
)


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_similar_vectors(self) -> None:
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 4.0]
        sim = _cosine_similarity(a, b)
        assert sim > 0.9  # very similar


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------

def _make_index(snippets_data: list[dict]) -> dict:
    """Build a minimal index dict for testing."""
    return {
        "model": "text-embedding-3-small",
        "snippet_count": len(snippets_data),
        "snippets": snippets_data,
    }


def _snippet(source_id: str, text: str, embedding: list[float], locator: str = "p.1") -> dict:
    return {
        "source_id": source_id,
        "source_title": f"Source {source_id}",
        "locator": locator,
        "text": text,
        "type": "text",
        "embedding": embedding,
    }


class TestRetrieve:
    @patch("app.ingest.indexer._embed_texts")
    def test_top_k_ordering(self, mock_embed: MagicMock) -> None:
        # Query embedding is [1, 0, 0] — most similar to snippet with [1, 0, 0]
        mock_embed.return_value = [[1.0, 0.0, 0.0]]

        index = _make_index([
            _snippet("SRC1", "staffing", [0.0, 1.0, 0.0]),     # orthogonal -> score 0
            _snippet("SRC2", "budget", [1.0, 0.0, 0.0]),       # identical -> score 1
            _snippet("SRC3", "training", [0.5, 0.5, 0.0]),     # partial -> ~0.7
        ])

        results = retrieve(index, "test query", top_k=2, api_key="fake")

        assert len(results) == 2
        assert results[0]["source_id"] == "SRC2"  # highest score
        assert results[0]["score"] == pytest.approx(1.0, abs=0.01)
        assert results[1]["source_id"] == "SRC3"  # second highest

    @patch("app.ingest.indexer._embed_texts")
    def test_no_embedding_in_results(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0]]
        index = _make_index([_snippet("SRC1", "text", [1.0, 0.0])])

        results = retrieve(index, "query", top_k=5, api_key="fake")
        assert "embedding" not in results[0]

    @patch("app.ingest.indexer._embed_texts")
    def test_preserves_metadata(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0]]
        index = _make_index([
            _snippet("SRC5", "example text", [1.0, 0.0], locator="p. 42")
        ])

        results = retrieve(index, "query", top_k=1, api_key="fake")
        assert results[0]["source_id"] == "SRC5"
        assert results[0]["source_title"] == "Source SRC5"
        assert results[0]["locator"] == "p. 42"
        assert results[0]["text"] == "example text"
        assert results[0]["type"] == "text"

    @patch("app.ingest.indexer._embed_texts")
    def test_top_k_limits_results(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0]]
        snippets = [_snippet(f"SRC{i}", f"text {i}", [1.0, 0.0]) for i in range(50)]
        index = _make_index(snippets)

        results = retrieve(index, "query", top_k=5, api_key="fake")
        assert len(results) == 5


# ---------------------------------------------------------------------------
# group_by_source
# ---------------------------------------------------------------------------

class TestGroupBySource:
    def test_groups_correctly(self) -> None:
        snippets = [
            {"source_id": "SRC1", "source_title": "A", "locator": "p.1", "text": "t1", "type": "text"},
            {"source_id": "SRC2", "source_title": "B", "locator": "p.2", "text": "t2", "type": "table"},
            {"source_id": "SRC1", "source_title": "A", "locator": "p.3", "text": "t3", "type": "text"},
        ]
        grouped = group_by_source(snippets)
        assert len(grouped) == 2

        src1 = next(s for s in grouped if s["source_id"] == "SRC1")
        assert len(src1["snippets"]) == 2
        assert src1["source_title"] == "A"

        src2 = next(s for s in grouped if s["source_id"] == "SRC2")
        assert len(src2["snippets"]) == 1

    def test_empty_input(self) -> None:
        assert group_by_source([]) == []


# ---------------------------------------------------------------------------
# build_index (mocked)
# ---------------------------------------------------------------------------

class TestNumpyRetrieve:
    """Verify that the numpy-based retrieve() returns the same ordering as the
    manual cosine similarity tests above (regression guard)."""

    @patch("app.ingest.indexer._embed_texts")
    def test_numpy_ordering_matches_expected(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0, 0.0]]

        index = _make_index([
            _snippet("SRC1", "staffing", [0.0, 1.0, 0.0]),     # orthogonal -> score 0
            _snippet("SRC2", "budget", [1.0, 0.0, 0.0]),       # identical -> score 1
            _snippet("SRC3", "training", [0.5, 0.5, 0.0]),     # partial -> ~0.7
        ])

        results = retrieve(index, "test query", top_k=3, api_key="fake")

        assert len(results) == 3
        assert results[0]["source_id"] == "SRC2"   # highest similarity
        assert results[1]["source_id"] == "SRC3"   # second
        assert results[2]["source_id"] == "SRC1"   # lowest

    @patch("app.ingest.indexer._embed_texts")
    def test_score_is_rounded_float(self, mock_embed: MagicMock) -> None:
        mock_embed.return_value = [[1.0, 0.0]]
        index = _make_index([_snippet("SRC1", "text", [1.0, 0.0])])
        results = retrieve(index, "q", top_k=1, api_key="fake")
        assert isinstance(results[0]["score"], float)
        assert results[0]["score"] == pytest.approx(1.0, abs=0.01)


class TestBuildIndex:
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("app.ingest.indexer._embed_texts")
    def test_build_and_load(self, mock_embed: MagicMock, tmp_path: Path) -> None:
        # Create a minimal sources file
        sources = {
            "sources": [
                {
                    "source_id": "SRC1",
                    "source_title": "Test Doc",
                    "snippets": [
                        {"locator": "p.1", "text": "Hello world", "type": "text"},
                        {"locator": "p.2", "text": "Goodbye world", "type": "text"},
                    ]
                }
            ]
        }
        sources_file = tmp_path / "test_sources.json"
        sources_file.write_text(json.dumps(sources), encoding="utf-8")

        # Mock embeddings
        mock_embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

        output_path = str(tmp_path / "test_index.json")
        result = build_index(str(sources_file), output_path)

        assert result == output_path
        assert Path(output_path).exists()

        # Load and verify
        index = load_index(output_path)
        assert index["model"] == "text-embedding-3-small"
        assert index["snippet_count"] == 2
        assert len(index["snippets"]) == 2
        assert index["snippets"][0]["source_id"] == "SRC1"
        assert index["snippets"][0]["embedding"] == [0.1, 0.2]

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("app.ingest.indexer._embed_texts")
    def test_empty_snippets_raises(self, mock_embed: MagicMock, tmp_path: Path) -> None:
        sources = {"sources": [{"source_id": "SRC1", "source_title": "Empty", "snippets": []}]}
        sources_file = tmp_path / "empty_sources.json"
        sources_file.write_text(json.dumps(sources), encoding="utf-8")

        with pytest.raises(ValueError, match="No snippets"):
            build_index(str(sources_file))
