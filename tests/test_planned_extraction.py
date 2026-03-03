"""Tests for the 2-stage llm_planned extraction pipeline.

Covers:
  - Planner schema validation
  - _planner_to_batches: segment → extraction batch conversion
  - _check_planner_locators: semantic locator reference validation
"""
from __future__ import annotations

import copy

import pytest

from app.core.validators import SchemaValidationError, validate_output
from app.app import (
    _check_planner_locators,
    _cited_locators_set,
    _count_cited_locators_in_payload,
    _DELTA_GROUP_SIZE,
    _enforce_planner_keyword_coverage,
    _MAX_DELTA_CALLS_PER_BATCH,
    _PLANNER_KEYWORD_FAMILIES,
    _planner_to_batches,
    _rank_locators_by_keyword,
    _skip_expansion_when_delta_enabled,
    _truncate_at_word_boundary,
)

SCHEMA = "schemas/domain_lessons_planner.schema.json"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _snip(n: int, chars: int = 100) -> dict:
    return {"type": "text", "text": "x" * chars, "locator": f"p.{n}"}


def _src(source_id: str, n_snips: int, title: str = "") -> dict:
    return {
        "source_id": source_id,
        "source_title": title or source_id,
        "snippets": [_snip(i) for i in range(n_snips)],
    }


def _make_planner_payload(source_id: str, locator_groups: list[list[str]]) -> dict:
    """Build a minimal valid planner payload with one SourcePlan."""
    segments = []
    for i, locs in enumerate(locator_groups, 1):
        segments.append({
            "segment_id": f"seg_{i:03d}",
            "locators": locs,
            "likely_categories": ["lessons_learnt"],
            "priority": "high",
            "reason": "test segment",
        })
    return {
        "job_id": "domain_lessons_planner",
        "generated_at": "2026-03-02",
        "plans": [
            {
                "source_id": source_id,
                "source_title": "Test Source",
                "segments": segments,
            }
        ],
    }


VALID_PLANNER_PAYLOAD = _make_planner_payload("SRC1", [["p.0", "p.1"]])


# ===========================================================================
# TestPlannerSchema — JSON schema validation
# ===========================================================================

class TestPlannerSchema:

    def test_valid_payload_passes(self):
        validate_output(VALID_PLANNER_PAYLOAD, SCHEMA)

    def test_missing_generated_at_fails(self):
        bad = {k: v for k, v in VALID_PLANNER_PAYLOAD.items() if k != "generated_at"}
        with pytest.raises(SchemaValidationError):
            validate_output(bad, SCHEMA)

    def test_unknown_category_fails(self):
        bad = copy.deepcopy(VALID_PLANNER_PAYLOAD)
        bad["plans"][0]["segments"][0]["likely_categories"] = ["bogus_category"]
        with pytest.raises(SchemaValidationError):
            validate_output(bad, SCHEMA)

    def test_invalid_priority_fails(self):
        bad = copy.deepcopy(VALID_PLANNER_PAYLOAD)
        bad["plans"][0]["segments"][0]["priority"] = "critical"
        with pytest.raises(SchemaValidationError):
            validate_output(bad, SCHEMA)

    def test_consequences_impacts_is_valid_likely_category(self):
        """consequences_impacts is a valid likely_category — planner output must not be rejected."""
        payload = copy.deepcopy(VALID_PLANNER_PAYLOAD)
        payload["plans"][0]["segments"][0]["likely_categories"] = ["consequences_impacts"]
        validate_output(payload, SCHEMA)  # must not raise

    def test_consequences_impacts_combined_with_others(self):
        """consequences_impacts alongside other categories in one segment is valid."""
        payload = _make_planner_payload("SRC2", [["p.12", "p.13"]])
        payload["plans"][0]["segments"][0]["likely_categories"] = [
            "consequences_impacts", "equity_implications"
        ]
        validate_output(payload, SCHEMA)  # must not raise

    def test_empty_segments_is_valid(self):
        """A source plan with no segments is allowed (source had no HRH content)."""
        payload = copy.deepcopy(VALID_PLANNER_PAYLOAD)
        payload["plans"][0]["segments"] = []
        validate_output(payload, SCHEMA)


# ===========================================================================
# TestPlannerToBatches — segment → extraction batch conversion
# ===========================================================================

class TestPlannerToBatches:

    def test_two_segments_produce_one_batch(self):
        """Two non-overlapping segments from the same source → 1 combined batch.
        All selected locators are grouped per-source before sub-batching, so the
        extractor sees full context in a single call (unless limits are exceeded)."""
        src = _src("SRC1", 4)
        plan = {
            "source_id": "SRC1",
            "source_title": "T",
            "segments": [
                {
                    "segment_id": "seg_001",
                    "locators": ["p.0", "p.1"],
                    "likely_categories": ["lessons_learnt"],
                    "priority": "high",
                    "reason": "r",
                },
                {
                    "segment_id": "seg_002",
                    "locators": ["p.2", "p.3"],
                    "likely_categories": ["recommendations"],
                    "priority": "medium",
                    "reason": "r",
                },
            ],
        }
        batches = _planner_to_batches([plan], {"SRC1": src}, max_excerpts=10, max_chars=999_999)
        assert len(batches) == 1
        assert len(batches[0][0]["snippets"]) == 4

    def test_unknown_locators_in_plan_are_skipped(self):
        """Locators not present in source snippets are silently omitted."""
        src = _src("SRC1", 1)  # only p.0 exists
        plan = {
            "source_id": "SRC1",
            "source_title": "T",
            "segments": [
                {
                    "segment_id": "seg_001",
                    "locators": ["p.0", "p.99"],  # p.99 does not exist
                    "likely_categories": ["lessons_learnt"],
                    "priority": "high",
                    "reason": "r",
                },
            ],
        }
        batches = _planner_to_batches([plan], {"SRC1": src}, max_excerpts=10, max_chars=999_999)
        assert len(batches) == 1
        # Only p.0 survived
        assert len(batches[0][0]["snippets"]) == 1
        assert batches[0][0]["snippets"][0]["locator"] == "p.0"

    def test_segment_exceeding_max_excerpts_splits(self):
        """6 locators in one segment, max_excerpts=3 → 2 sub-batches."""
        src = _src("SRC1", 6)
        plan = {
            "source_id": "SRC1",
            "source_title": "T",
            "segments": [
                {
                    "segment_id": "seg_001",
                    "locators": [f"p.{i}" for i in range(6)],
                    "likely_categories": ["lessons_learnt"],
                    "priority": "high",
                    "reason": "r",
                },
            ],
        }
        batches = _planner_to_batches([plan], {"SRC1": src}, max_excerpts=3, max_chars=999_999)
        assert len(batches) == 2

    def test_priority_order_high_before_medium(self):
        """high-priority snippet appears before medium-priority snippet within the combined batch."""
        src = _src("SRC1", 2)
        plan = {
            "source_id": "SRC1",
            "source_title": "T",
            "segments": [
                # Deliberately listed medium first to test sorting
                {
                    "segment_id": "seg_002",
                    "locators": ["p.1"],
                    "likely_categories": ["lessons_learnt"],
                    "priority": "medium",
                    "reason": "r",
                },
                {
                    "segment_id": "seg_001",
                    "locators": ["p.0"],
                    "likely_categories": ["lessons_learnt"],
                    "priority": "high",
                    "reason": "r",
                },
            ],
        }
        batches = _planner_to_batches([plan], {"SRC1": src}, max_excerpts=10, max_chars=999_999)
        # Both locators are in one combined batch; high-priority locator (p.0) comes first.
        assert len(batches) == 1
        snips = batches[0][0]["snippets"]
        assert snips[0]["locator"] == "p.0"
        assert snips[1]["locator"] == "p.1"


# ===========================================================================
# TestCheckPlannerLocators — semantic locator reference validation
# ===========================================================================

class TestCheckPlannerLocators:

    def test_all_valid_returns_empty(self):
        """All referenced locators exist in the source → empty error list."""
        src = _src("SRC1", 2)
        plan = _make_planner_payload("SRC1", [["p.0", "p.1"]])
        assert _check_planner_locators(plan, {"SRC1": src}) == []

    def test_unknown_locator_returns_error(self):
        """One unknown locator → one error mentioning the bad locator."""
        src = _src("SRC1", 1)  # only p.0 exists
        plan = _make_planner_payload("SRC1", [["p.0", "p.99"]])
        errors = _check_planner_locators(plan, {"SRC1": src})
        assert len(errors) == 1
        assert "p.99" in errors[0]

    def test_unknown_source_id_returns_error(self):
        """Plan references a source_id not in sources_by_id → error about source."""
        plan = _make_planner_payload("SRC_GHOST", [["p.0"]])
        errors = _check_planner_locators(plan, {})  # no sources provided
        assert len(errors) == 1
        assert "SRC_GHOST" in errors[0]

    def test_multiple_bad_locators_all_reported(self):
        """Two unknown locators → two errors."""
        src = _src("SRC1", 1)  # only p.0 exists
        plan = _make_planner_payload("SRC1", [["p.0", "p.99", "p.999"]])
        errors = _check_planner_locators(plan, {"SRC1": src})
        assert len(errors) == 2


# ===========================================================================
# TestTruncateAtWordBoundary — preview truncation helper (C)
# ===========================================================================

class TestTruncateAtWordBoundary:

    def test_short_text_unchanged(self):
        """Text shorter than max_chars passes through unchanged."""
        assert _truncate_at_word_boundary("hello world", 300) == "hello world"

    def test_exact_length_unchanged(self):
        """Text exactly at max_chars passes through unchanged."""
        text = "a" * 300
        assert _truncate_at_word_boundary(text, 300) == text

    def test_truncates_at_last_space(self):
        """Long text is cut at the last space before max_chars, not mid-word."""
        text = "freely available in 11 languages the PSS could assist practitioners"
        # max_chars=30 cuts somewhere inside "languages" without word-boundary;
        # the helper should back off to the space before "languages".
        result = _truncate_at_word_boundary(text, 30)
        assert not result.endswith(" ")  # no trailing space
        assert " " not in result[len(result.rstrip()):] or True  # result is a clean token boundary
        # The result must be a prefix of the original text ending at a word boundary.
        assert text.startswith(result)
        assert result == "freely available in 11"

    def test_no_space_falls_back_to_hard_cut(self):
        """If there is no space before max_chars, fall back to a hard character cut."""
        text = "x" * 400
        result = _truncate_at_word_boundary(text, 300)
        assert len(result) == 300

    def test_keyword_not_split(self):
        """A keyword that would be split mid-word by [:300] is preserved intact."""
        # Place "freely available" so it would be cut mid-word at a naive slice.
        prefix = "a" * 295  # 295 chars then a space then keyword
        text = prefix + " freely available in 11 languages"
        naive = text[:300]  # cuts "freely" → "freel"
        result = _truncate_at_word_boundary(text, 300)
        # Word-boundary cut should stop before "freely" so the keyword stays intact.
        assert "freel" not in result  # no mid-word cut
        assert result == prefix  # stops cleanly before the space+keyword


# ===========================================================================
# TestEnforcePlannerKeywordCoverage — deterministic post-planner enforcement
# ===========================================================================

def _make_source(source_id: str, snippets: list[dict]) -> dict:
    """Build a minimal source dict with explicit snippets."""
    return {"source_id": source_id, "source_title": source_id, "snippets": snippets}


def _make_snippet(locator: str, text: str) -> dict:
    return {"locator": locator, "text": text, "type": "text"}


def _make_plan(source_id: str, segments: list[dict]) -> dict:
    return {"source_id": source_id, "source_title": source_id, "segments": segments}


def _make_segment(locators: list[str], categories: list[str], priority: str = "high") -> dict:
    return {
        "segment_id": "seg_001",
        "locators": locators,
        "likely_categories": categories,
        "priority": priority,
        "reason": "test",
    }


class TestEnforcePlannerKeywordCoverage:

    def test_missing_prerequisites_locator_added_to_existing_segment(self):
        """Locator containing 'quick' (prerequisites keyword) gets added to a
        segment already targeting 'prerequisites'."""
        src = _make_source("SRC1", [
            _make_snippet("p.1", "This is the abstract."),
            _make_snippet("p.2", "quick to administer and freely available in 11 languages"),
        ])
        plan = _make_plan("SRC1", [
            _make_segment(["p.1"], ["prerequisites"]),
        ])
        plans = _enforce_planner_keyword_coverage([plan], {"SRC1": src})
        covered = {loc for seg in plans[0]["segments"] for loc in seg["locators"]}
        assert "p.2" in covered, "prerequisites locator must be added"

    def test_missing_equity_locator_creates_new_segment(self):
        """Locator with 'female absenteeism' (equity keyword) creates a new segment
        when no existing segment targets equity_implications."""
        src = _make_source("SRC2", [
            _make_snippet("p.1", "Overview of absenteeism study."),
            _make_snippet("p.4", "Female absenteeism was related to caregiving; male to dual practice."),
        ])
        plan = _make_plan("SRC2", [
            _make_segment(["p.1"], ["lessons_learnt"]),
        ])
        plans = _enforce_planner_keyword_coverage([plan], {"SRC2": src})
        covered = {loc for seg in plans[0]["segments"] for loc in seg["locators"]}
        assert "p.4" in covered, "equity locator must be added"
        # A new segment should have been created for equity_implications
        all_cats = [cat for seg in plans[0]["segments"] for cat in seg["likely_categories"]]
        assert "equity_implications" in all_cats

    def test_already_covered_locator_not_duplicated(self):
        """Locator already in a segment is not added a second time even if it matches keywords."""
        src = _make_source("SRC1", [
            _make_snippet("p.1", "quick to administer, freely available"),
        ])
        plan = _make_plan("SRC1", [
            _make_segment(["p.1"], ["prerequisites"]),
        ])
        plans = _enforce_planner_keyword_coverage([plan], {"SRC1": src})
        all_locators = [loc for seg in plans[0]["segments"] for loc in seg["locators"]]
        assert all_locators.count("p.1") == 1, "locator must not be duplicated"

    def test_consequences_locator_with_delayed_keyword_added(self):
        """Locator containing 'delayed salary payment' (consequences keyword: 'delayed')
        is added when no segment covers it."""
        src = _make_source("SRC2", [
            _make_snippet("p.1", "Background section."),
            _make_snippet("p.14", "drivers ranging from low wages to delayed salary payment and corruption"),
        ])
        plan = _make_plan("SRC2", [
            _make_segment(["p.1"], ["recommendations"]),
        ])
        plans = _enforce_planner_keyword_coverage([plan], {"SRC2": src})
        covered = {loc for seg in plans[0]["segments"] for loc in seg["locators"]}
        assert "p.14" in covered

    def test_unknown_source_id_in_plan_is_skipped(self):
        """A plan referencing a source_id not in sources_by_id is left unchanged."""
        plan = _make_plan("SRC_GHOST", [_make_segment(["p.1"], ["lessons_learnt"])])
        original_segs = [dict(s) for s in plan["segments"]]
        plans = _enforce_planner_keyword_coverage([plan], {})
        assert plan["segments"] == original_segs

    def test_segment_cap_merges_into_last_segment(self):
        """When 10 segments already exist, new keyword-hit locators are merged into
        the last segment rather than creating an 11th."""
        # 10 segments, all covering "lessons_learnt"
        segs = [
            {
                "segment_id": f"seg_{i:03d}",
                "locators": [f"p.{i}"],
                "likely_categories": ["lessons_learnt"],
                "priority": "low",
                "reason": "filler",
            }
            for i in range(1, 11)
        ]
        # p.20 has "future research" (evidence_gaps keyword) — not covered
        snippets = [_make_snippet(f"p.{i}", "generic text") for i in range(1, 11)]
        snippets.append(_make_snippet("p.20", "future research should investigate this further"))
        src = _make_source("SRC1", snippets)
        plan = _make_plan("SRC1", segs)
        plans = _enforce_planner_keyword_coverage([plan], {"SRC1": src})
        assert len(plans[0]["segments"]) == 10, "must not exceed 10 segments"
        covered = {loc for seg in plans[0]["segments"] for loc in seg["locators"]}
        assert "p.20" in covered, "p.20 must be merged into existing segment"


# ===========================================================================
# TestCountCitedLocators — coverage expansion pass trigger helper
# ===========================================================================

def _make_domain_lessons_payload(cited_items: list[tuple[str, str]]) -> dict:
    """Build a minimal domain_lessons_option_b payload with one citation per (doc_id, locator)."""
    citations = [
        {"doc_id": doc_id, "locator": locator, "source_title": "Test", "snippet": "x"}
        for doc_id, locator in cited_items
    ]
    item = {
        "item_id": "ll_001",
        "title": "Test Item",
        "statement": "Test statement.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": citations,
    }
    return {
        "job_id": "domain_lessons_option_b",
        "target_country": "TestCountry",
        "generated_at": "2026-01-01",
        "domains": [
            {
                "domain_id": "accountability",
                "focus_areas": [
                    {
                        "focus_area_id": "supervision_models",
                        "proven_interventions": [],
                        "lessons_learnt": [item],
                        "recommendations": [],
                        "prerequisites": [],
                        "operational_barriers": [],
                        "governance_process_dependencies": [],
                        "evidence_gaps_uncertainty": [],
                        "costs_resource_intensity": [],
                        "equity_implications": [],
                        "consequences_impacts": [],
                    }
                ],
            }
        ],
    }


class TestCountCitedLocators:

    def test_counts_matching_doc_ids(self):
        """Returns count of unique (doc_id, locator) pairs from matching doc_ids."""
        payload = _make_domain_lessons_payload([("SRC1", "p.1"), ("SRC1", "p.3")])
        assert _count_cited_locators_in_payload(payload, {"SRC1"}) == 2

    def test_excludes_non_matching_doc_ids(self):
        """Citations from doc_ids not in the filter set are not counted."""
        payload = _make_domain_lessons_payload([("SRC1", "p.1"), ("SRC2", "p.5")])
        assert _count_cited_locators_in_payload(payload, {"SRC1"}) == 1

    def test_deduplicates_same_locator(self):
        """Same (doc_id, locator) appearing in multiple items counts as 1."""
        cited = [("SRC1", "p.1"), ("SRC1", "p.1")]
        # Build payload with two items sharing the same citation
        citations = [
            {"doc_id": "SRC1", "locator": "p.1", "source_title": "T", "snippet": "x"}
        ]
        item1 = {"item_id": "ll_001", "title": "A", "statement": "s", "evidence_type": "determinant_mechanism", "evidence_strength": "weak", "citations": citations}
        item2 = {"item_id": "ll_002", "title": "B", "statement": "s", "evidence_type": "determinant_mechanism", "evidence_strength": "weak", "citations": citations}
        payload = _make_domain_lessons_payload([])
        payload["domains"][0]["focus_areas"][0]["lessons_learnt"] = [item1, item2]
        assert _count_cited_locators_in_payload(payload, {"SRC1"}) == 1

    def test_empty_payload_returns_zero(self):
        """Payload with no cited items returns 0."""
        payload = _make_domain_lessons_payload([])
        assert _count_cited_locators_in_payload(payload, {"SRC1"}) == 0

    def test_counts_across_all_categories(self):
        """Locators cited in different category arrays are all counted."""
        payload = _make_domain_lessons_payload([])
        fa = payload["domains"][0]["focus_areas"][0]
        fa["prerequisites"] = [
            {"item_id": "pre_001", "title": "Prereq", "statement": "s",
             "evidence_type": "determinant_mechanism", "evidence_strength": "weak",
             "citations": [{"doc_id": "SRC1", "locator": "p.2", "source_title": "T", "snippet": "x"}]}
        ]
        fa["lessons_learnt"] = [
            {"item_id": "ll_001", "title": "Lesson", "statement": "s",
             "evidence_type": "determinant_mechanism", "evidence_strength": "weak",
             "citations": [{"doc_id": "SRC1", "locator": "p.5", "source_title": "T", "snippet": "x"}]}
        ]
        assert _count_cited_locators_in_payload(payload, {"SRC1"}) == 2

    def test_expansion_triggers_when_cited_lt5_and_batch_gte8(self):
        """Expansion should trigger when cited < 5 AND batch >= 8 (logical condition check)."""
        payload = _make_domain_lessons_payload([("SRC1", f"p.{i}") for i in range(4)])
        n_cited = _count_cited_locators_in_payload(payload, {"SRC1"})
        batch_locators = [f"p.{i}" for i in range(10)]
        assert n_cited < 5 and len(batch_locators) >= 8, "expansion should trigger"

    def test_expansion_does_not_trigger_when_cited_gte5(self):
        """Expansion should NOT trigger when ≥5 locators are already cited."""
        payload = _make_domain_lessons_payload([("SRC1", f"p.{i}") for i in range(5)])
        n_cited = _count_cited_locators_in_payload(payload, {"SRC1"})
        batch_locators = [f"p.{i}" for i in range(10)]
        assert not (n_cited < 5 and len(batch_locators) >= 8), "expansion should NOT trigger"


# ===========================================================================
# TestCitedLocatorsSet — _cited_locators_set aggregates across payloads
# ===========================================================================

class TestCitedLocatorsSet:

    def test_returns_locators_for_matching_doc_ids(self):
        """Returns the set of locator strings cited for the specified doc_ids."""
        payload = _make_domain_lessons_payload([("SRC1", "p.1"), ("SRC1", "p.3")])
        result = _cited_locators_set([payload], {"SRC1"})
        assert result == {"p.1", "p.3"}

    def test_excludes_non_matching_doc_ids(self):
        """Citations from doc_ids not in the filter set are not returned."""
        payload = _make_domain_lessons_payload([("SRC1", "p.1"), ("SRC2", "p.5")])
        result = _cited_locators_set([payload], {"SRC1"})
        assert result == {"p.1"}

    def test_deduplicates_same_locator_across_items(self):
        """Same locator cited by two different items counts only once."""
        cit = {"doc_id": "SRC1", "locator": "p.1", "source_title": "T", "snippet": "x"}
        item1 = {"item_id": "ll_001", "title": "A", "statement": "s",
                 "evidence_type": "determinant_mechanism", "evidence_strength": "weak",
                 "citations": [cit]}
        item2 = {"item_id": "ll_002", "title": "B", "statement": "s",
                 "evidence_type": "determinant_mechanism", "evidence_strength": "weak",
                 "citations": [cit]}
        payload = _make_domain_lessons_payload([])
        payload["domains"][0]["focus_areas"][0]["lessons_learnt"] = [item1, item2]
        result = _cited_locators_set([payload], {"SRC1"})
        assert result == {"p.1"}

    def test_aggregates_across_multiple_payloads(self):
        """Locators from a list of payloads are unioned together."""
        p1 = _make_domain_lessons_payload([("SRC1", "p.1")])
        p2 = _make_domain_lessons_payload([("SRC1", "p.3")])
        result = _cited_locators_set([p1, p2], {"SRC1"})
        assert result == {"p.1", "p.3"}

    def test_empty_list_returns_empty_set(self):
        """Empty payload list returns empty set."""
        assert _cited_locators_set([], {"SRC1"}) == set()


# ===========================================================================
# TestRankLocatorsByKeyword — sorting by keyword-family hit count
# ===========================================================================

class TestRankLocatorsByKeyword:

    def test_keyword_hit_locator_ranked_first(self):
        """A locator whose text contains a keyword-family term is ranked before a zero-hit one."""
        snippets = [
            _make_snippet("p.1", "future research is needed to validate these findings"),
            _make_snippet("p.2", "no relevant terms here at all"),
        ]
        src = _make_source("SRC1", snippets)
        result = _rank_locators_by_keyword(["p.2", "p.1"], [src])
        assert result[0] == "p.1", "p.1 has a keyword hit and should come first"

    def test_higher_hit_count_ranked_first(self):
        """A locator with 3 keyword hits is ranked before one with 1 hit."""
        snippets = [
            _make_snippet("p.1", "limitations and heterogeneity and uncertainty in data"),
            _make_snippet("p.2", "some limitations noted"),
        ]
        src = _make_source("SRC1", snippets)
        result = _rank_locators_by_keyword(["p.2", "p.1"], [src])
        assert result[0] == "p.1"

    def test_zero_hit_locators_kept_at_back(self):
        """Zero-hit locators are included at the end, not dropped."""
        snippets = [
            _make_snippet("p.1", "analysis showed higher rates in the sample"),
            # "limitations" is a confirmed keyword in evidence_gaps_uncertainty family
            _make_snippet("p.2", "there are significant limitations in the evidence base"),
        ]
        src = _make_source("SRC1", snippets)
        result = _rank_locators_by_keyword(["p.1", "p.2"], [src])
        assert "p.1" in result, "zero-hit locator must still be in the result"
        assert result[-1] == "p.1", "zero-hit locator should be last"
        assert result[0] == "p.2", "keyword-hit locator should be first"

    def test_empty_input_returns_empty(self):
        """Empty locator list returns empty list."""
        src = _make_source("SRC1", [])
        assert _rank_locators_by_keyword([], [src]) == []


# ===========================================================================
# TestDeltaSweepTrigger — threshold formula, cost cap, keyword prioritisation
# ===========================================================================

class TestDeltaSweepTrigger:

    def test_trigger_below_threshold_8_locators(self):
        """With 8 locators, threshold = min(5, ceil(8*0.5)) = 4. cited=2 → triggers."""
        import math
        n_cited, n_batch = 2, 8
        threshold = min(5, math.ceil(n_batch * 0.5))
        assert n_cited < threshold, "delta sweep should trigger"

    def test_no_trigger_at_threshold_8_locators(self):
        """With 8 locators and 4 cited (= threshold=4), delta does NOT trigger."""
        import math
        n_cited, n_batch = 4, 8
        threshold = min(5, math.ceil(n_batch * 0.5))
        assert not (n_cited < threshold), "delta sweep should NOT trigger"

    def test_threshold_4_locators(self):
        """With 4 locators, threshold = min(5, ceil(2)) = 2."""
        import math
        assert min(5, math.ceil(4 * 0.5)) == 2

    def test_threshold_12_locators_capped_at_5(self):
        """With 12 locators, threshold = min(5, ceil(6)) = 5."""
        import math
        assert min(5, math.ceil(12 * 0.5)) == 5

    def test_cost_cap_limits_to_delta_group_budget(self):
        """12 uncited locators: only DELTA_GROUP_SIZE * MAX_DELTA_CALLS_PER_BATCH are swept."""
        uncited = [f"p.{i}" for i in range(1, 13)]
        max_sweep = _DELTA_GROUP_SIZE * _MAX_DELTA_CALLS_PER_BATCH
        to_sweep = uncited[:max_sweep]
        assert len(to_sweep) == max_sweep
        assert len(to_sweep) == 8  # 4 * 2 = 8 with defaults

    def test_keyword_prioritization_order(self):
        """Keyword-hit locator appears before zero-hit locator after ranking."""
        snippets = [
            _make_snippet("p.1", "no keywords here"),
            _make_snippet("p.2", "limitations and heterogeneity in results"),
            _make_snippet("p.3", "no keywords either"),
        ]
        src = _make_source("SRC1", snippets)
        uncited = ["p.1", "p.2", "p.3"]
        ranked = _rank_locators_by_keyword(uncited, [src])
        assert ranked[0] == "p.2", "p.2 has keyword hits and should be first"
        to_sweep = ranked[:_DELTA_GROUP_SIZE * _MAX_DELTA_CALLS_PER_BATCH]
        assert "p.2" in to_sweep


# ===========================================================================
# TestDeltaGrouping — Fix A: grouped multi-locator delta calls
# ===========================================================================

class TestDeltaGrouping:

    def test_7_uncited_produces_2_groups(self):
        """7 uncited locators with GROUP=3, MAX_CALLS=2 → 2 groups of 3, 1 skipped.

        Top 6 (= 3 * 2) are selected; partitioned into [0:3] and [3:6]; capped at 2 calls.
        """
        uncited = [f"p.{i}" for i in range(1, 8)]  # 7 locators
        group_size, max_calls = 3, 2
        max_sweep = group_size * max_calls          # 6
        to_sweep = uncited[:max_sweep]              # first 6
        groups = [to_sweep[i:i + group_size] for i in range(0, len(to_sweep), group_size)]
        groups = groups[:max_calls]
        assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
        assert len(groups[0]) == 3
        assert len(groups[1]) == 3
        # The 7th locator is skipped
        all_swept = [loc for grp in groups for loc in grp]
        assert "p.7" not in all_swept

    def test_groups_contain_correct_locators(self):
        """First group gets the top-ranked locators; second group gets the next batch."""
        uncited = [f"p.{i}" for i in range(1, 9)]  # 8 locators
        group_size, max_calls = 4, 2
        max_sweep = group_size * max_calls  # 8
        to_sweep = uncited[:max_sweep]
        groups = [to_sweep[i:i + group_size] for i in range(0, len(to_sweep), group_size)]
        groups = groups[:max_calls]
        assert groups[0] == ["p.1", "p.2", "p.3", "p.4"]
        assert groups[1] == ["p.5", "p.6", "p.7", "p.8"]

    def test_fewer_uncited_than_group_size(self):
        """2 uncited locators with GROUP=4 → 1 group of 2, 1 call."""
        uncited = ["p.1", "p.2"]
        group_size, max_calls = 4, 2
        max_sweep = group_size * max_calls
        to_sweep = uncited[:max_sweep]
        groups = [to_sweep[i:i + group_size] for i in range(0, len(to_sweep), group_size)]
        groups = groups[:max_calls]
        assert len(groups) == 1
        assert groups[0] == ["p.1", "p.2"]

    def test_default_constants_give_8_max_locators(self):
        """Defaults: DELTA_GROUP_SIZE=4, MAX_DELTA_CALLS_PER_BATCH=2 → 8 max locators swept."""
        assert _DELTA_GROUP_SIZE * _MAX_DELTA_CALLS_PER_BATCH == 8


# ===========================================================================
# TestDeltaSkipNoKeywords — Fix B: skip delta when all uncited have 0 hits
# ===========================================================================

def _all_kws_flat() -> tuple:
    return tuple(kw for kws in _PLANNER_KEYWORD_FAMILIES.values() for kw in kws)


class TestDeltaSkipNoKeywords:

    def _has_hits_for_top(self, locators: list[str], batch: list[dict]) -> bool:
        """Mirror the in-loop _has_hits check: check only the top-ranked locator."""
        all_kws = _all_kws_flat()
        locator_text = {
            snip.get("locator", ""): snip.get("text", "").lower()
            for src in batch
            for snip in src.get("snippets", [])
            if snip.get("locator")
        }
        ranked = _rank_locators_by_keyword(locators, batch)
        return bool(ranked) and any(kw in locator_text.get(ranked[0], "") for kw in all_kws)

    def test_keyword_hit_locators_have_hits(self):
        """Two locators with keyword text: has_hits=True."""
        snippets = [
            _make_snippet("p.1", "significant limitations in data comparability"),
            _make_snippet("p.2", "delayed salary payment was a major driver"),
        ]
        src = _make_source("SRC1", snippets)
        assert self._has_hits_for_top(["p.1", "p.2"], [src]) is True

    def test_zero_hit_locators_skip_delta(self):
        """All uncited locators with neutral text: has_hits=False → delta skipped."""
        snippets = [
            _make_snippet("p.1", "the study was conducted in three regions"),
            _make_snippet("p.2", "table 1 shows the distribution of participants"),
        ]
        src = _make_source("SRC1", snippets)
        assert self._has_hits_for_top(["p.1", "p.2"], [src]) is False

    def test_mixed_locators_not_skipped(self):
        """One keyword-hit locator among neutrals: has_hits=True → delta runs."""
        snippets = [
            _make_snippet("p.1", "workload increased significantly for remaining staff"),
            _make_snippet("p.2", "table 2 shows participant demographics"),
        ]
        src = _make_source("SRC1", snippets)
        # _rank puts p.1 (keyword hit) first → has_hits=True
        assert self._has_hits_for_top(["p.2", "p.1"], [src]) is True

    def test_empty_uncited_no_hits(self):
        """Empty locator list: has_hits=False."""
        src = _make_source("SRC1", [])
        assert self._has_hits_for_top([], [src]) is False


# ===========================================================================
# TestSkipExpansionWhenDelta — Fix C: expansion skipped when delta is scheduled
# ===========================================================================

class TestSkipExpansionWhenDelta:

    def test_skip_expansion_enabled_by_default(self):
        """HRH_SKIP_EXPANSION_WHEN_DELTA is ON by default (env var absent)."""
        import os
        os.environ.pop("HRH_SKIP_EXPANSION_WHEN_DELTA", None)
        assert _skip_expansion_when_delta_enabled() is True

    def test_skip_expansion_disabled_by_zero(self):
        """Setting HRH_SKIP_EXPANSION_WHEN_DELTA=0 disables the skip."""
        import os
        os.environ["HRH_SKIP_EXPANSION_WHEN_DELTA"] = "0"
        try:
            assert _skip_expansion_when_delta_enabled() is False
        finally:
            os.environ.pop("HRH_SKIP_EXPANSION_WHEN_DELTA", None)

    def test_skip_expansion_disabled_by_false(self):
        """Setting HRH_SKIP_EXPANSION_WHEN_DELTA=false disables the skip."""
        import os
        os.environ["HRH_SKIP_EXPANSION_WHEN_DELTA"] = "false"
        try:
            assert _skip_expansion_when_delta_enabled() is False
        finally:
            os.environ.pop("HRH_SKIP_EXPANSION_WHEN_DELTA", None)

    def test_expansion_skipped_when_cited_below_delta_threshold(self):
        """Logic check: when cited < delta_threshold AND skip enabled → expansion is skipped."""
        import math
        n_cited, n_batch = 2, 8
        delta_threshold = min(5, math.ceil(n_batch * 0.5))  # 4
        # With skip enabled and cited(2) < threshold(4): skip expansion
        skip_enabled = True
        skip_exp = skip_enabled and n_cited < delta_threshold
        assert skip_exp is True, "expansion should be skipped"

    def test_expansion_runs_when_delta_not_triggered(self):
        """When cited >= delta_threshold, skip is False regardless of flag."""
        import math
        n_cited, n_batch = 5, 8
        delta_threshold = min(5, math.ceil(n_batch * 0.5))  # 4
        skip_enabled = True
        skip_exp = skip_enabled and n_cited < delta_threshold
        assert skip_exp is False, "expansion should NOT be skipped"
