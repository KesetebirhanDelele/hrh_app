"""Tests for RRR RAG query construction."""

from app.app import _build_rrr_query


def test_empty_mechanism_uses_solution_only():
    assert _build_rrr_query("Supportive Supervision and Coaching", "") == "Supportive Supervision and Coaching"


def test_whitespace_mechanism_uses_solution_only():
    assert _build_rrr_query("Supportive Supervision and Coaching", "   ") == "Supportive Supervision and Coaching"


def test_tbd_mechanism_uses_solution_only():
    assert _build_rrr_query("Financial Incentives", "To be determined from evidence for Financial Incentives") == "Financial Incentives"


def test_placeholder_mechanism_uses_solution_only():
    assert _build_rrr_query("Task Shifting", "Mechanism for Task Shifting (stub placeholder)") == "Task Shifting"


def test_tbd_uppercase_uses_solution_only():
    assert _build_rrr_query("Housing Solutions", "TBD") == "Housing Solutions"


def test_tbd_mixed_case_uses_solution_only():
    assert _build_rrr_query("Housing Solutions", "Tbd") == "Housing Solutions"


def test_real_mechanism_includes_both():
    result = _build_rrr_query("Supportive Supervision", "Increases intrinsic motivation through regular feedback loops")
    assert result == "Supportive Supervision — Increases intrinsic motivation through regular feedback loops"
