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
from app.app import _check_planner_locators, _planner_to_batches

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

    def test_empty_segments_is_valid(self):
        """A source plan with no segments is allowed (source had no HRH content)."""
        payload = copy.deepcopy(VALID_PLANNER_PAYLOAD)
        payload["plans"][0]["segments"] = []
        validate_output(payload, SCHEMA)


# ===========================================================================
# TestPlannerToBatches — segment → extraction batch conversion
# ===========================================================================

class TestPlannerToBatches:

    def test_two_segments_produce_two_batches(self):
        """Two non-overlapping segments → 2 extraction batches."""
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
        assert len(batches) == 2

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
        """high-priority segment's batch comes before medium-priority segment's batch."""
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
        assert len(batches) == 2
        # High-priority segment (p.0) should appear first
        assert batches[0][0]["snippets"][0]["locator"] == "p.0"
        assert batches[1][0]["snippets"][0]["locator"] == "p.1"


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
