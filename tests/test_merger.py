"""Tests for app.analyze.merger."""

from __future__ import annotations

import pytest

from app.analyze.merger import merge_outputs, _merge_evidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phase1_output(questions: list[dict], spec_id: str = "test_spec") -> dict:
    return {
        "job_id": "phase1_discovery_qa",
        "spec_id": spec_id,
        "generated_at": "2026-02-10",
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": questions,
    }


def _q(qid: str, answer: str, quality: str = "none", citations: list | None = None) -> dict:
    evidence: dict = {"quality": quality, "rationale": f"Rationale for {qid}"}
    if quality == "none":
        evidence["citations"] = []
    else:
        evidence["citations"] = citations or []
    return {"question_id": qid, "question": f"Question {qid}?", "answer": answer, "evidence": evidence}


# ---------------------------------------------------------------------------
# _merge_evidence
# ---------------------------------------------------------------------------

class TestMergeEvidence:
    def test_incoming_none_keeps_existing(self) -> None:
        existing = {"quality": "medium", "rationale": "r1", "citations": [{"source_title": "A", "locator": "p.1"}]}
        incoming = {"quality": "none", "rationale": "", "citations": []}
        result = _merge_evidence(existing, incoming)
        assert result["quality"] == "medium"
        assert len(result["citations"]) == 1

    def test_existing_none_takes_incoming(self) -> None:
        existing = {"quality": "none", "rationale": "", "citations": []}
        incoming = {"quality": "high", "rationale": "r2", "citations": [{"source_title": "B", "locator": "p.2"}]}
        result = _merge_evidence(existing, incoming)
        assert result["quality"] == "high"
        assert len(result["citations"]) == 1

    def test_quality_upgrade(self) -> None:
        existing = {"quality": "low", "rationale": "r1", "citations": [{"source_title": "A", "locator": "p.1"}]}
        incoming = {"quality": "high", "rationale": "r2", "citations": [{"source_title": "B", "locator": "p.2"}]}
        result = _merge_evidence(existing, incoming)
        assert result["quality"] == "high"
        assert len(result["citations"]) == 2

    def test_citation_dedup(self) -> None:
        cit = {"source_id": "SRC1", "source_title": "A", "locator": "p.1"}
        existing = {"quality": "medium", "rationale": "r1", "citations": [cit]}
        incoming = {"quality": "medium", "rationale": "r2", "citations": [cit]}  # same citation
        result = _merge_evidence(existing, incoming)
        assert len(result["citations"]) == 1  # deduplicated

    def test_rationale_combined(self) -> None:
        existing = {"quality": "low", "rationale": "Found in report", "citations": []}
        incoming = {"quality": "medium", "rationale": "Also in survey", "citations": []}
        result = _merge_evidence(existing, incoming)
        assert "Found in report" in result["rationale"]
        assert "Also in survey" in result["rationale"]


# ---------------------------------------------------------------------------
# merge_outputs — phase1_discovery_qa
# ---------------------------------------------------------------------------

class TestMergePhase1:
    def test_single_output_passthrough(self) -> None:
        output = _make_phase1_output([_q("Q1", "Answer 1")])
        result = merge_outputs("phase1_discovery_qa", [output])
        assert result is output

    def test_two_sources_different_evidence(self) -> None:
        o1 = _make_phase1_output([
            _q("Q1", "From source A", "medium", [{"source_id": "SRC1", "source_title": "A", "locator": "p.5"}]),
            _q("Q2", "No evidence", "none"),
        ])
        o2 = _make_phase1_output([
            _q("Q1", "From source B", "high", [{"source_id": "SRC2", "source_title": "B", "locator": "p.10"}]),
            _q("Q2", "Found in B", "low", [{"source_id": "SRC2", "source_title": "B", "locator": "p.20"}]),
        ])
        result = merge_outputs("phase1_discovery_qa", [o1, o2])
        questions = result["questions"]
        assert len(questions) == 2

        # Q1: merged — quality upgraded, both citations present, answers combined
        q1 = questions[0]
        assert q1["evidence"]["quality"] == "high"
        assert len(q1["evidence"]["citations"]) == 2
        assert "From source A" in q1["answer"]
        assert "From source B" in q1["answer"]

        # Q2: evidence from o2 wins over none
        q2 = questions[1]
        assert q2["evidence"]["quality"] == "low"
        assert len(q2["evidence"]["citations"]) == 1

    def test_preserves_order_from_first_output(self) -> None:
        o1 = _make_phase1_output([_q("Q2", "A2"), _q("Q1", "A1")])
        o2 = _make_phase1_output([_q("Q1", "B1"), _q("Q2", "B2")])
        result = merge_outputs("phase1_discovery_qa", [o1, o2])
        assert result["questions"][0]["question_id"] == "Q2"
        assert result["questions"][1]["question_id"] == "Q1"


# ---------------------------------------------------------------------------
# merge_outputs — other job types
# ---------------------------------------------------------------------------

class TestMergeOtherJobs:
    def test_rrr_evidence_matrix(self) -> None:
        o1 = {"job_id": "rrr_evidence_matrix", "solutions": [
            {"solution_id": "S1", "solution": "Sol", "mechanism": "M",
             "evidence": {"quality": "low", "rationale": "r", "citations": []}}
        ]}
        o2 = {"job_id": "rrr_evidence_matrix", "solutions": [
            {"solution_id": "S1", "solution": "Sol", "mechanism": "M",
             "evidence": {"quality": "high", "rationale": "r2", "citations": [
                 {"source_id": "SRC1", "source_title": "X", "locator": "p.1"}
             ]}}
        ]}
        result = merge_outputs("rrr_evidence_matrix", [o1, o2])
        assert result["solutions"][0]["evidence"]["quality"] == "high"

    def test_table2(self) -> None:
        o1 = {"job_id": "table2", "framework_items": [
            {"item_id": "I1", "category": "C", "root_cause": "RC", "definition": "Def A",
             "evidence": {"quality": "none", "rationale": "", "citations": []}}
        ]}
        o2 = {"job_id": "table2", "framework_items": [
            {"item_id": "I1", "category": "C", "root_cause": "RC", "definition": "Def B",
             "evidence": {"quality": "medium", "rationale": "r", "citations": [
                 {"source_id": "SRC2", "source_title": "Y", "locator": "p.3"}
             ]}}
        ]}
        result = merge_outputs("table2_root_cause_mapping", [o1, o2])
        item = result["framework_items"][0]
        assert item["evidence"]["quality"] == "medium"
        assert "Def A" in item["definition"]
        assert "Def B" in item["definition"]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            merge_outputs("phase1_discovery_qa", [])

    def test_unknown_job_raises(self) -> None:
        with pytest.raises(KeyError):
            merge_outputs("nonexistent_job", [{"data": 1}, {"data": 2}])
