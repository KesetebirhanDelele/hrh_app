"""Unit tests for prompting._trim_sources balanced text/table budget."""
from __future__ import annotations

import pytest

from app.analyze.prompting import _trim_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snip(text: str, kind: str = "text") -> dict:
    return {"type": kind, "text": text, "locator": "p.1"}


def _src(doc_id: str, *snips: dict) -> dict:
    return {"doc_id": doc_id, "snippets": list(snips)}


def _all_snips(sources: list[dict]) -> list[dict]:
    return [s for src in sources for s in src["snippets"]]


def _types(sources: list[dict]) -> set[str]:
    return {s["type"] for s in _all_snips(sources)}


# ---------------------------------------------------------------------------
# No-op when everything fits
# ---------------------------------------------------------------------------

def test_no_trim_when_under_budget():
    """Returns input unchanged when total chars <= max_chars."""
    sources = [_src("A", _snip("hello", "text"), _snip("| a |", "table"))]
    result = _trim_sources(sources, max_chars=10_000)
    assert result is sources  # same object returned


def test_empty_budget_drops_all_snippets():
    sources = [_src("A", _snip("hello"), _snip("| a |", "table"))]
    result = _trim_sources(sources, max_chars=0)
    assert _all_snips(result) == []
    assert len(result) == 1  # source metadata preserved


# ---------------------------------------------------------------------------
# Both types survive under tight budget
# ---------------------------------------------------------------------------

def test_both_text_and_table_included_under_tight_budget():
    """With a 50/50 split, both text and table snippets survive even when
    total content exceeds the budget."""
    text_snip = _snip("A" * 1000, "text")
    table_snip = _snip("T" * 1000, "table")
    sources = [_src("A", text_snip, table_snip)]

    # Budget is only 1200 — half each would be 600, too small for either full
    # snippet but the guarantee rule should admit at least one of each.
    result = _trim_sources(sources, max_chars=1200)
    types = _types(result)
    assert "text" in types, "text snippet was dropped"
    assert "table" in types, "table snippet was dropped"


def test_multiple_snippets_both_types_survive():
    """When each source has several snippets of both types, both types appear
    in the trimmed output."""
    sources = [
        _src("A",
             _snip("text-a1 " * 50, "text"),
             _snip("text-a2 " * 50, "text"),
             _snip("| table-a1 |" * 30, "table"),
             _snip("| table-a2 |" * 30, "table"),
        ),
        _src("B",
             _snip("text-b1 " * 50, "text"),
             _snip("| table-b1 |" * 30, "table"),
        ),
    ]
    total = sum(len(s["text"]) for src in sources for s in src["snippets"])
    budget = total // 3  # force significant trimming

    result = _trim_sources(sources, max_chars=budget)
    snips = _all_snips(result)
    assert any(s["type"] == "text" for s in snips), "no text snippets survived"
    assert any(s["type"] == "table" for s in snips), "no table snippets survived"


# ---------------------------------------------------------------------------
# Spillover: text budget → tables, table budget → text
# ---------------------------------------------------------------------------

def test_table_leftover_spills_to_text():
    """When source has only text snippets, the table budget is reallocated
    to admit more text."""
    # 3 text snippets, no tables; budget = 250 (50% text = 125 chars)
    sources = [_src("A",
        _snip("A" * 100, "text"),
        _snip("B" * 100, "text"),
        _snip("C" * 100, "text"),
    )]
    result = _trim_sources(sources, max_chars=250)
    snips = _all_snips(result)
    # Without spillover only 1 text snippet would fit in the 125-char text
    # budget; with the table leftover spilled over, 2 should fit (200 chars).
    texts = [s for s in snips if s["type"] == "text"]
    assert len(texts) >= 2, f"expected at least 2 text snippets, got {len(texts)}"


def test_text_leftover_spills_to_tables():
    """When source has only table snippets, the text budget is reallocated
    to admit more tables."""
    sources = [_src("A",
        _snip("T" * 100, "table"),
        _snip("U" * 100, "table"),
        _snip("V" * 100, "table"),
    )]
    result = _trim_sources(sources, max_chars=250)
    snips = _all_snips(result)
    tables = [s for s in snips if s["type"] == "table"]
    assert len(tables) >= 2, f"expected at least 2 table snippets, got {len(tables)}"


# ---------------------------------------------------------------------------
# At-least-one guarantee
# ---------------------------------------------------------------------------

def test_at_least_one_text_when_text_exists():
    """Even when a single text snippet far exceeds its half-budget share,
    it is still included."""
    big_text = _snip("X" * 5000, "text")
    small_table = _snip("T" * 10, "table")
    sources = [_src("A", big_text, small_table)]

    result = _trim_sources(sources, max_chars=100)  # 100 << 5000
    snips = _all_snips(result)
    assert any(s["type"] == "text" for s in snips)


def test_at_least_one_table_when_table_exists():
    """Even when a single table snippet far exceeds its half-budget share,
    it is still included."""
    big_table = _snip("T" * 5000, "table")
    small_text = _snip("X" * 10, "text")
    sources = [_src("A", small_text, big_table)]

    result = _trim_sources(sources, max_chars=100)
    snips = _all_snips(result)
    assert any(s["type"] == "table" for s in snips)


# ---------------------------------------------------------------------------
# Ordering preserved within a source
# ---------------------------------------------------------------------------

def test_original_ordering_preserved_within_source():
    """Snippets that survive trimming appear in the same order as in the
    original source, regardless of type."""
    snips_in_order = [
        _snip("text-first " * 10, "text"),
        _snip("| table-mid |" * 5, "table"),
        _snip("text-last " * 10, "text"),
    ]
    sources = [_src("A", *snips_in_order)]
    total = sum(len(s["text"]) for s in snips_in_order)

    result = _trim_sources(sources, max_chars=total)  # everything fits
    result_texts = [s["text"] for s in result[0]["snippets"]]
    expected = [s["text"] for s in snips_in_order]
    assert result_texts == expected


# ---------------------------------------------------------------------------
# Source metadata always preserved
# ---------------------------------------------------------------------------

def test_source_metadata_preserved_when_all_snippets_dropped():
    """Sources with no snippets surviving trimming still appear in output."""
    sources = [
        _src("A", _snip("A" * 10, "text")),
        _src("B", _snip("B" * 10_000, "text")),  # too big
    ]
    result = _trim_sources(sources, max_chars=10)
    assert len(result) == 2
    assert result[0]["doc_id"] == "A"
    assert result[1]["doc_id"] == "B"
