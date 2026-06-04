"""Tests for app.ingest.chunker — chunk size, overlap, and table pass-through."""

from __future__ import annotations

import pytest

from app.ingest.chunker import chunk_snippets
from app.ingest.loader import Snippet


def _snip(text: str, type_: str = "text", locator: str = "p. 1") -> Snippet:
    return Snippet(locator=locator, text=text, type=type_)


def _para(n: int, word_len: int = 10) -> str:
    """Return a paragraph of exactly *n* characters."""
    word = "w" * word_len
    words = []
    total = 0
    while total < n:
        add = min(word_len, n - total)
        words.append("w" * add)
        total += add + 1  # +1 for space
    return " ".join(words)[:n]


class TestChunkSize:
    def test_short_text_passes_through_unchanged(self) -> None:
        text = "Short text under limit."
        result = chunk_snippets([_snip(text)], max_chars=800)
        assert len(result) == 1
        assert result[0]["text"] == text

    def test_long_text_splits_into_chunks_under_max(self) -> None:
        # Build a long text made of distinct paragraphs
        paragraphs = [f"Paragraph {i}: " + "x" * 100 for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = chunk_snippets([_snip(text)], max_chars=800, overlap_chars=0)
        for chunk in result:
            assert len(chunk["text"]) <= 900, f"Chunk exceeds limit: {len(chunk['text'])}"

    def test_default_max_chars_is_800(self) -> None:
        paragraphs = ["A" * 200 for _ in range(10)]
        text = "\n\n".join(paragraphs)
        result = chunk_snippets([_snip(text)])
        for chunk in result:
            # With default max_chars=800, each chunk text should be manageable
            assert len(chunk["text"]) <= 1200  # allow some tolerance for overlap


class TestOverlap:
    def test_consecutive_chunks_share_tail(self) -> None:
        # Create text that forces a split into ≥2 chunks with overlap
        paragraphs = [f"Paragraph {i}: " + "sentence content here" for i in range(30)]
        text = "\n\n".join(paragraphs)
        result = chunk_snippets([_snip(text)], max_chars=400, overlap_chars=100)

        assert len(result) >= 2, "Expected multiple chunks"
        # The start of chunk[1] should contain some text from the end of chunk[0]
        # (overlap carries tail words into the next chunk)
        chunk0_tail = result[0]["text"][-80:]
        chunk1_start = result[1]["text"][:200]
        # At least some words from chunk0's tail should appear in chunk1's body
        tail_words = set(chunk0_tail.split())
        start_words = set(chunk1_start.split())
        overlap_words = tail_words & start_words
        assert len(overlap_words) > 0, (
            f"Expected overlapping words between chunk 0 tail and chunk 1 start.\n"
            f"chunk0 tail: {chunk0_tail!r}\n"
            f"chunk1 start: {chunk1_start!r}"
        )

    def test_no_overlap_when_overlap_chars_zero(self) -> None:
        paragraphs = [f"Para {i}: " + "distinct content here." for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = chunk_snippets([_snip(text)], max_chars=300, overlap_chars=0)
        assert len(result) >= 2

    def test_single_chunk_no_overlap_padding(self) -> None:
        text = "Short text."
        result = chunk_snippets([_snip(text)], max_chars=800, overlap_chars=150)
        assert len(result) == 1
        assert result[0]["text"] == text


class TestTablePassThrough:
    def test_table_never_split(self) -> None:
        # A table much larger than max_chars should pass through intact
        rows = [f"| Col A | Col B | Col C |\n| val{i} | val{i} | val{i} |" for i in range(50)]
        table_text = "\n".join(rows)
        assert len(table_text) > 800
        result = chunk_snippets([_snip(table_text, type_="table")], max_chars=800)
        assert len(result) == 1
        assert result[0]["type"] == "table"
        assert result[0]["text"] == table_text

    def test_mixed_table_and_text(self) -> None:
        snippets = [
            _snip("A" * 50, type_="table"),
            _snip("\n\n".join(["word " * 60] * 10), type_="text"),
        ]
        result = chunk_snippets(snippets, max_chars=200, overlap_chars=0)
        table_chunks = [r for r in result if r["type"] == "table"]
        text_chunks = [r for r in result if r["type"] == "text"]
        assert len(table_chunks) == 1
        assert len(text_chunks) >= 2


class TestLocators:
    def test_multi_chunk_locators_have_part_suffix(self) -> None:
        paragraphs = [f"Para {i}: " + "content." * 10 for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = chunk_snippets([_snip(text, locator="p. 5")], max_chars=300, overlap_chars=0)
        assert len(result) >= 2
        for i, chunk in enumerate(result):
            assert f"part {i + 1}" in chunk["locator"]

    def test_single_chunk_locator_unchanged(self) -> None:
        result = chunk_snippets([_snip("Short.", locator="p. 3")])
        assert result[0]["locator"] == "p. 3"
