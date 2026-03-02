"""Tests for snippet sub-batching in the domain_lessons_option_b legacy path."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, call

import pytest

from app.app import _expand_source_batches_for_job, _snippet_sub_batches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snip(n: int, chars: int = 100) -> dict:
    return {"type": "text", "text": "x" * chars, "locator": f"p.{n}"}


def _src(doc_id: str, snippets: list[dict], has_meta: bool = False) -> dict:
    return {"doc_id": doc_id, "snippets": snippets}


def _meta_src(doc_id: str) -> dict:
    """Source with no snippets (metadata-only)."""
    return {"doc_id": doc_id, "snippets": []}


# ===========================================================================
# _snippet_sub_batches — pure function
# ===========================================================================

class TestSnippetSubBatches:

    def test_empty_input_returns_one_empty_batch(self):
        result = _snippet_sub_batches([], max_excerpts=5, max_chars=10_000)
        assert result == [[]]

    def test_split_by_count_exact_multiple(self):
        snips = [_snip(i) for i in range(6)]
        result = _snippet_sub_batches(snips, max_excerpts=3, max_chars=999_999)
        assert len(result) == 2
        assert all(len(b) == 3 for b in result)

    def test_split_by_count_ceil(self):
        """ceil(10 / 4) = 3 batches."""
        n, max_ex = 10, 4
        snips = [_snip(i) for i in range(n)]
        result = _snippet_sub_batches(snips, max_excerpts=max_ex, max_chars=999_999)
        assert len(result) == math.ceil(n / max_ex)

    def test_split_by_chars(self):
        """Each snippet is 100 chars; budget is 250 → batch sizes 2, 2, 1 for 5 snippets."""
        snips = [_snip(i, chars=100) for i in range(5)]
        result = _snippet_sub_batches(snips, max_excerpts=999, max_chars=250)
        # 250 chars fits 2 snippets (200 ≤ 250 < 300)
        assert len(result) == 3
        assert sum(len(b) for b in result) == 5

    def test_split_by_whichever_limit_hit_first(self):
        """max_excerpts=3, max_chars=180 (fits 1 snippet of 100); excerpts limit wins."""
        snips = [_snip(i, chars=50) for i in range(9)]
        # 50-char snips, budget=180 fits 3 → same as count limit → 3 batches of 3
        result = _snippet_sub_batches(snips, max_excerpts=3, max_chars=180)
        assert len(result) == 3

    def test_oversized_single_snippet_still_admitted(self):
        """A snippet that alone exceeds max_chars is admitted (at-least-one guarantee)."""
        big = _snip(0, chars=50_000)
        result = _snippet_sub_batches([big], max_excerpts=5, max_chars=100)
        assert len(result) == 1
        assert result[0] == [big]

    def test_oversized_first_snippet_then_normal(self):
        """Oversized first snippet gets its own batch; remaining snippets follow."""
        big = _snip(0, chars=50_000)
        small = _snip(1, chars=50)
        result = _snippet_sub_batches([big, small], max_excerpts=5, max_chars=100)
        assert len(result) == 2
        assert result[0] == [big]
        assert result[1] == [small]

    def test_preserves_snippet_order(self):
        snips = [_snip(i) for i in range(7)]
        result = _snippet_sub_batches(snips, max_excerpts=3, max_chars=999_999)
        flat = [s for batch in result for s in batch]
        assert flat == snips

    def test_single_snippet_returns_one_batch(self):
        snip = _snip(0)
        result = _snippet_sub_batches([snip], max_excerpts=5, max_chars=10_000)
        assert result == [[snip]]


# ===========================================================================
# _expand_source_batches_for_job
# ===========================================================================

class TestExpandSourceBatchesForJob:

    def test_other_job_unchanged(self):
        """Non-domain_lessons job: input returned as-is."""
        batches = [[_src("A", [_snip(i) for i in range(10)])]]
        result = _expand_source_batches_for_job(
            "rrr_evidence_matrix", batches, max_excerpts=3, max_chars=999_999
        )
        assert result is batches  # same object

    def test_none_batch_passed_through(self):
        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", [None], max_excerpts=5, max_chars=999_999
        )
        assert result == [None]

    def test_batch_without_snippets_passed_through(self):
        batch = [_meta_src("A"), _meta_src("B")]
        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", [batch], max_excerpts=5, max_chars=999_999
        )
        assert len(result) == 1
        assert result[0] is batch

    def test_call_count_equals_ceil_n_over_max_excerpts(self):
        """N=10 snippets, max_excerpts=3 → ceil(10/3)=4 sub-batches → 4 LLM calls."""
        n, max_ex = 10, 3
        snips = [_snip(i) for i in range(n)]
        batches = [[_src("SRC1", snips)]]

        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches, max_excerpts=max_ex, max_chars=999_999
        )
        assert len(result) == math.ceil(n / max_ex)

    def test_meta_sources_carried_into_every_sub_batch(self):
        """Metadata-only sources appear in every sub-batch."""
        snips = [_snip(i) for i in range(6)]
        meta = _meta_src("META")
        batches = [[_src("SRC1", snips), meta]]

        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches, max_excerpts=3, max_chars=999_999
        )
        assert len(result) == 2
        for sub_batch in result:
            doc_ids = [s["doc_id"] for s in sub_batch]
            assert "META" in doc_ids, "metadata source missing from sub-batch"

    def test_multiple_sources_each_sub_batched(self):
        """Two sources × 6 snippets each, max_excerpts=3 → 4 total sub-batches."""
        snips = [_snip(i) for i in range(6)]
        src_a = _src("A", snips)
        src_b = _src("B", [_snip(i, 50) for i in range(6)])
        # Per-source mode: each source in its own batch
        batches = [[src_a], [src_b]]

        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches, max_excerpts=3, max_chars=999_999
        )
        assert len(result) == 4

    def test_snippet_content_preserved_across_sub_batches(self):
        """All original snippets appear exactly once across the expanded sub-batches."""
        snips = [_snip(i) for i in range(7)]
        batches = [[_src("SRC1", snips)]]

        result = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches, max_excerpts=3, max_chars=999_999
        )
        recovered = [
            s
            for sub_batch in result
            for src in sub_batch
            if src["doc_id"] == "SRC1"
            for s in src["snippets"]
        ]
        assert recovered == snips


# ===========================================================================
# Simulated call-count harness (mock generate_json)
# ===========================================================================

class TestSimulatedCallCount:

    def _run_mock_loop(self, expanded_batches: list, mock_gen: MagicMock) -> int:
        """Simulate the cmd_run legacy loop: one generate_json call per sub-batch."""
        for _batch in expanded_batches:
            mock_gen(prompt="...", job_id="domain_lessons_option_b")
        return mock_gen.call_count

    def test_call_count_equals_sub_batch_count(self):
        """generate_json is called exactly once per sub-batch."""
        n, max_ex = 10, 3  # ceil(10/3) = 4 calls expected
        snips = [_snip(i) for i in range(n)]
        batches = [[_src("SRC1", snips)]]

        expanded = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches, max_excerpts=max_ex, max_chars=999_999
        )

        mock_gen = MagicMock(return_value=MagicMock(text='{"job_id": "x"}'))
        actual_calls = self._run_mock_loop(expanded, mock_gen)

        assert actual_calls == math.ceil(n / max_ex)

    def test_call_count_varies_by_max_excerpts(self):
        """Doubling max_excerpts halves the number of calls (approx.)."""
        n = 12
        snips = [_snip(i) for i in range(n)]
        batches_a = [[_src("SRC1", snips)]]
        batches_b = [[_src("SRC1", snips)]]

        expanded_a = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches_a, max_excerpts=3, max_chars=999_999
        )
        expanded_b = _expand_source_batches_for_job(
            "domain_lessons_option_b", batches_b, max_excerpts=6, max_chars=999_999
        )

        mock_a, mock_b = MagicMock(), MagicMock()
        calls_a = self._run_mock_loop(expanded_a, mock_a)
        calls_b = self._run_mock_loop(expanded_b, mock_b)

        assert calls_a == 4   # ceil(12/3)
        assert calls_b == 2   # ceil(12/6)
        assert calls_a == calls_b * 2

    def test_no_extra_calls_for_other_jobs(self):
        """Non-domain_lessons jobs: source_batches unchanged → call count unchanged."""
        n = 10
        snips = [_snip(i) for i in range(n)]
        batches = [[_src("SRC1", snips)]]

        # rrr_evidence_matrix: batches not expanded
        expanded = _expand_source_batches_for_job(
            "rrr_evidence_matrix", batches, max_excerpts=3, max_chars=999_999
        )

        mock_gen = MagicMock()
        calls = self._run_mock_loop(expanded, mock_gen)

        assert calls == 1  # one batch, one call
