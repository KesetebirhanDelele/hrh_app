"""Tests for extract_rrr_solutions with both spec formats."""

from app.analyze.extractors import extract_rrr_solutions


# --- Spec with top-level "solutions" array (new format) ---

SPEC_WITH_SOLUTIONS = {
    "spec_id": "rrr_solutions_resource_constrained_v1",
    "intervention_families_seed_list": [
        "supportive_supervision_and_coaching",
        "performance_contracts_and_scorecards",
        "task_shifting_and_task_redesign",
    ],
    "solutions": [
        {
            "solution_id": "int_1",
            "intervention": "Supportive Supervision and Coaching",
            "mechanism": "",
            "feasibility_resource_constrained": "unknown",
        },
        {
            "solution_id": "int_2",
            "intervention": "Performance Contracts and Scorecards",
            "mechanism": "",
            "feasibility_resource_constrained": "unknown",
        },
    ],
}


def test_solutions_array_used_when_present():
    items = extract_rrr_solutions(SPEC_WITH_SOLUTIONS)
    assert len(items) == 2
    assert items[0].solution_id == "int_1"
    assert items[0].solution == "Supportive Supervision and Coaching"
    assert items[1].solution_id == "int_2"
    assert items[1].solution == "Performance Contracts and Scorecards"


def test_solutions_array_no_stub_placeholder():
    items = extract_rrr_solutions(SPEC_WITH_SOLUTIONS)
    for item in items:
        assert "stub placeholder" not in item.mechanism.lower()
        assert "stub placeholder" not in item.solution.lower()


def test_solutions_array_mechanism_is_empty():
    items = extract_rrr_solutions(SPEC_WITH_SOLUTIONS)
    for item in items:
        assert item.mechanism == ""


def test_solutions_array_takes_priority_over_seed_list():
    """seed_list has 3 entries, solutions has 2 — must return 2 (solutions wins)."""
    items = extract_rrr_solutions(SPEC_WITH_SOLUTIONS)
    assert len(items) == 2, (
        f"Expected 2 items from solutions[], got {len(items)} — "
        "seed_list fallback was used instead"
    )


# --- Spec with only intervention_families_seed_list (legacy format) ---

SPEC_SEED_ONLY = {
    "spec_id": "rrr_solutions_resource_constrained_v1",
    "intervention_families_seed_list": [
        "supportive_supervision_and_coaching",
        "financial_incentives_and_allowances",
        "task_shifting_and_task_redesign",
    ],
}


def test_seed_list_fallback_produces_correct_count():
    items = extract_rrr_solutions(SPEC_SEED_ONLY)
    assert len(items) == 3


def test_seed_list_fallback_no_stub_placeholder():
    items = extract_rrr_solutions(SPEC_SEED_ONLY)
    for item in items:
        assert "stub placeholder" not in item.mechanism.lower()
        assert "stub placeholder" not in item.solution.lower()


def test_seed_list_fallback_mechanism_is_empty():
    items = extract_rrr_solutions(SPEC_SEED_ONLY)
    for item in items:
        assert item.mechanism == ""


def test_seed_list_fallback_ids_increment():
    items = extract_rrr_solutions(SPEC_SEED_ONLY)
    assert [it.solution_id for it in items] == ["int_1", "int_2", "int_3"]


def test_seed_list_fallback_readable_names():
    items = extract_rrr_solutions(SPEC_SEED_ONLY)
    assert items[0].solution == "Supportive Supervision And Coaching"
    assert items[1].solution == "Financial Incentives And Allowances"
    assert items[2].solution == "Task Shifting And Task Redesign"
