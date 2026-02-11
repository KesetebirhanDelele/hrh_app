"""Tests for app.ingest.loader and app.ingest.chunker."""

from __future__ import annotations

import pytest

from app.ingest.loader import _table_to_markdown, Snippet
from app.ingest.chunker import chunk_snippets


# ---------------------------------------------------------------------------
# _table_to_markdown
# ---------------------------------------------------------------------------

class TestTableToMarkdown:
    def test_simple_table(self) -> None:
        data = [
            ["Name", "Age", "City"],
            ["Alice", "30", "Addis Ababa"],
            ["Bob", "25", "Hawassa"],
        ]
        md = _table_to_markdown(data)
        lines = md.strip().split("\n")
        assert len(lines) == 4  # header + separator + 2 data rows
        assert "| Name | Age | City |" in lines[0]
        assert "| --- | --- | --- |" in lines[1]
        assert "Alice" in lines[2]
        assert "Bob" in lines[3]

    def test_none_cells_become_empty(self) -> None:
        data = [
            ["Header1", "Header2"],
            [None, "value"],
        ]
        md = _table_to_markdown(data)
        assert "|  | value |" in md

    def test_pipe_in_cell_is_escaped(self) -> None:
        data = [
            ["Col"],
            ["a | b"],
        ]
        md = _table_to_markdown(data)
        assert "a \\| b" in md

    def test_empty_table_returns_empty(self) -> None:
        assert _table_to_markdown([]) == ""
        assert _table_to_markdown([[]]) == ""

    def test_rows_shorter_than_header_are_padded(self) -> None:
        data = [
            ["A", "B", "C"],
            ["1"],  # only 1 cell, should be padded
        ]
        md = _table_to_markdown(data)
        lines = md.strip().split("\n")
        # Data row should have 3 cells
        assert lines[2].count("|") == 4  # leading + 3 separators


# ---------------------------------------------------------------------------
# chunk_snippets
# ---------------------------------------------------------------------------

class TestChunkSnippets:
    def test_small_snippet_passes_through(self) -> None:
        snippets = [Snippet(locator="p. 1", text="Short text.", type="text")]
        result = chunk_snippets(snippets, max_chars=100)
        assert len(result) == 1
        assert result[0]["text"] == "Short text."

    def test_tables_never_split(self) -> None:
        long_table = "| A | B |\n| --- | --- |\n" + "| x | y |\n" * 200
        snippets = [Snippet(locator="Table on p. 1", text=long_table, type="table")]
        result = chunk_snippets(snippets, max_chars=50)
        assert len(result) == 1  # table stays intact

    def test_long_text_is_split(self) -> None:
        paras = ["Paragraph number {}.".format(i) for i in range(20)]
        text = "\n\n".join(paras)
        snippets = [Snippet(locator="p. 5", text=text, type="text")]
        result = chunk_snippets(snippets, max_chars=100)
        assert len(result) > 1
        # All parts should have locator info
        for s in result:
            assert "p. 5" in s["locator"]

    def test_chunk_locator_has_part_number(self) -> None:
        text = "A" * 100 + "\n\n" + "B" * 100
        snippets = [Snippet(locator="p. 3", text=text, type="text")]
        result = chunk_snippets(snippets, max_chars=120)
        assert len(result) == 2
        assert "(part 1)" in result[0]["locator"]
        assert "(part 2)" in result[1]["locator"]

    def test_empty_list_returns_empty(self) -> None:
        assert chunk_snippets([]) == []
