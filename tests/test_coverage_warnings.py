"""Unit tests for _log_coverage_warnings in app.app."""
from __future__ import annotations

import pytest

from app.app import _log_coverage_warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(source_id: str, n_snippets: int, title: str = "") -> dict:
    return {
        "source_id": source_id,
        "source_title": title or source_id,
        "snippets": [{"locator": f"p.{i}", "text": "x"} for i in range(n_snippets)],
    }


def _make_payload(citations: list[dict]) -> dict:
    """Minimal domain_lessons_option_b payload with citations in proven_interventions."""
    return {
        "job_id": "domain_lessons_option_b",
        "domains": [
            {
                "domain_id": "accountability",
                "focus_areas": [
                    {
                        "focus_area_id": "supervision_models",
                        "proven_interventions": [
                            {"item_id": "pi_001", "citations": citations}
                        ],
                        "lessons_learnt": [],
                        "recommendations": [],
                        "prerequisites": [],
                        "operational_barriers": [],
                        "governance_process_dependencies": [],
                        "evidence_gaps_uncertainty": [],
                        "costs_resource_intensity": [],
                        "equity_implications": [],
                    }
                ],
            }
        ],
    }


def _cit(doc_id: str, locator: str) -> dict:
    return {"doc_id": doc_id, "source_title": "X", "locator": locator, "snippet": "x"}


# ---------------------------------------------------------------------------
# Warning fires
# ---------------------------------------------------------------------------

def test_warning_when_low_coverage_and_many_snippets(capsys):
    """Coverage < 10% AND available >= 20 → WARNING printed."""
    # 20 snippets available, only 1 locator cited → 5% coverage
    src = _make_source("SRC1", 20, "Big Report 2023")
    payload = _make_payload([_cit("SRC1", "p.0")])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" in out
    assert "source_id=SRC1" in out
    assert "source_title='Big Report 2023'" in out
    assert "available_snippets=20" in out
    assert "cited_locators=1" in out
    assert "coverage=5.0%" in out


def test_warning_lists_coverage_percentage_correctly(capsys):
    """2 cited out of 25 available = 8.0% → warning with correct percentage."""
    src = _make_source("SRC2", 25)
    payload = _make_payload([_cit("SRC2", "p.0"), _cit("SRC2", "p.1")])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "coverage=8.0%" in out


def test_warning_when_zero_citations(capsys):
    """No citations at all for a source with >= 20 snippets → WARNING."""
    src = _make_source("SRC1", 30)
    payload = _make_payload([])  # no citations

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" in out
    assert "cited_locators=0" in out
    assert "coverage=0.0%" in out


# ---------------------------------------------------------------------------
# Warning suppressed
# ---------------------------------------------------------------------------

def test_no_warning_when_coverage_at_threshold(capsys):
    """Exactly 10% coverage (2/20) → no warning."""
    src = _make_source("SRC1", 20)
    payload = _make_payload([_cit("SRC1", "p.0"), _cit("SRC1", "p.1")])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" not in out


def test_no_warning_when_coverage_above_threshold(capsys):
    """20 out of 20 snippets cited → no warning."""
    src = _make_source("SRC1", 20)
    payload = _make_payload([_cit("SRC1", f"p.{i}") for i in range(20)])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" not in out


def test_no_warning_when_fewer_than_20_snippets(capsys):
    """Source with 19 snippets and 0% coverage → no warning (below threshold)."""
    src = _make_source("SRC1", 19)
    payload = _make_payload([])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" not in out


def test_no_warning_for_other_job_ids(capsys):
    """Other job_ids are ignored even with low coverage."""
    src = _make_source("SRC1", 30)
    payload = _make_payload([])

    _log_coverage_warnings("domain_solutions_from_evidence", payload, [src])
    _log_coverage_warnings("rrr_evidence_matrix", payload, [src])

    out = capsys.readouterr().out
    assert "[COVERAGE WARNING]" not in out


# ---------------------------------------------------------------------------
# Multiple sources
# ---------------------------------------------------------------------------

def test_only_low_coverage_source_warned(capsys):
    """Two sources: one low coverage (warns), one adequate (silent)."""
    src_low = _make_source("SRC1", 20)   # 0 cited → 0%
    src_ok  = _make_source("SRC2", 20)   # 10 cited → 50%

    cits = [_cit("SRC2", f"p.{i}") for i in range(10)]
    payload = _make_payload(cits)

    _log_coverage_warnings("domain_lessons_option_b", payload, [src_low, src_ok])

    out = capsys.readouterr().out
    assert "source_id=SRC1" in out
    assert "source_id=SRC2" not in out


def test_all_low_coverage_sources_warned(capsys):
    """Two sources both below threshold → two warning lines."""
    src_a = _make_source("SRC1", 20)
    src_b = _make_source("SRC2", 25)
    payload = _make_payload([])  # zero citations for either

    _log_coverage_warnings("domain_lessons_option_b", payload, [src_a, src_b])

    out = capsys.readouterr().out
    assert out.count("[COVERAGE WARNING]") == 2


# ---------------------------------------------------------------------------
# Deduplication: same locator cited multiple times counts as one
# ---------------------------------------------------------------------------

def test_duplicate_locator_counts_once(capsys):
    """Citing the same locator in three items counts as one unique locator."""
    src = _make_source("SRC1", 20)
    # 3 citations all pointing to the same locator
    payload = _make_payload([
        _cit("SRC1", "p.0"),
        _cit("SRC1", "p.0"),
        _cit("SRC1", "p.0"),
    ])

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    # 1/20 = 5% → warning, cited_locators=1
    assert "[COVERAGE WARNING]" in out
    assert "cited_locators=1" in out


# ---------------------------------------------------------------------------
# Citations across all nine categories are counted
# ---------------------------------------------------------------------------

def test_citations_across_all_categories_counted(capsys):
    """Locators cited in any of the nine category arrays all count towards coverage."""
    src = _make_source("SRC1", 20)

    # Spread 2 citations (locators p.0 and p.1) across different categories
    payload = {
        "job_id": "domain_lessons_option_b",
        "domains": [
            {
                "domain_id": "accountability",
                "focus_areas": [
                    {
                        "focus_area_id": "supervision_models",
                        "proven_interventions": [
                            {"item_id": "pi_001", "citations": [_cit("SRC1", "p.0")]}
                        ],
                        "lessons_learnt": [],
                        "recommendations": [],
                        "prerequisites": [
                            {"item_id": "pre_001", "citations": [_cit("SRC1", "p.1")]}
                        ],
                        "operational_barriers": [],
                        "governance_process_dependencies": [],
                        "evidence_gaps_uncertainty": [],
                        "costs_resource_intensity": [],
                        "equity_implications": [],
                    }
                ],
            }
        ],
    }

    _log_coverage_warnings("domain_lessons_option_b", payload, [src])

    out = capsys.readouterr().out
    # 2/20 = 10% → no warning
    assert "[COVERAGE WARNING]" not in out
