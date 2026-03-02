"""Tests for app.analyze.merger."""

from __future__ import annotations

import pytest

from app.analyze.merger import merge_outputs, _merge_evidence, _cap_per_doc


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


# ---------------------------------------------------------------------------
# _cap_per_doc + merge_outputs — domain_solutions_from_evidence
# ---------------------------------------------------------------------------

def _ds_partial(title: str, evidence_strength: str, citations: list) -> dict:
    """Build a minimal domain_solutions_from_evidence partial payload."""
    return {
        "job_id": "domain_solutions_from_evidence",
        "target_country": "Global",
        "generated_at": "2026-02-28",
        "domains": [{
            "domain_id": "accountability",
            "focus_areas": [{
                "focus_area_id": "supervision_models",
                "solutions": [{
                    "solution_id": "accountability_supervision_models_1",
                    "title": title,
                    "description": "Test.",
                    "mechanism": "Test mechanism.",
                    "implementation_conditions": [],
                    "evidence_strength": evidence_strength,
                    "citations": citations,
                }]
            }]
        }]
    }


class TestCapPerDoc:
    def test_weak_caps_to_1_per_doc(self) -> None:
        """_cap_per_doc keeps only 1 citation per doc_id for weak solutions."""
        cits = [
            {"doc_id": "SRC1", "locator": "p.1", "snippet": "Short."},
            {"doc_id": "SRC1", "locator": "p.2", "snippet": "Longer snippet here."},
        ]
        result = _cap_per_doc(cits, "weak")
        assert len(result) == 1
        # Longer snippet should be preferred
        assert result[0]["locator"] == "p.2"

    def test_strong_caps_to_3_per_doc(self) -> None:
        """_cap_per_doc keeps up to 3 citations per doc_id for strong solutions."""
        cits = [
            {"doc_id": "SRC1", "locator": "p.1", "snippet": "A."},
            {"doc_id": "SRC1", "locator": "p.2", "snippet": "BB."},
            {"doc_id": "SRC1", "locator": "p.3", "snippet": "CCC."},
            {"doc_id": "SRC1", "locator": "p.4", "snippet": "X."},  # tied-shortest, later → dropped
        ]
        result = _cap_per_doc(cits, "strong")
        assert len(result) == 3
        locators = {c["locator"] for c in result}
        assert "p.3" in locators   # longest snippet, always kept
        assert "p.4" not in locators  # tied-shortest but latest index, dropped

    def test_preserves_order(self) -> None:
        """Result preserves the original relative order of kept citations."""
        cits = [
            {"doc_id": "SRC1", "locator": "p.1", "snippet": "AA."},
            {"doc_id": "SRC2", "locator": "p.2", "snippet": "B."},
            {"doc_id": "SRC1", "locator": "p.3", "snippet": "A."},  # trimmed by weak cap
        ]
        result = _cap_per_doc(cits, "weak")
        # Both doc_ids get 1 each; SRC1 keeps "p.1" (longer snippet than "p.3")
        assert [c["locator"] for c in result] == ["p.1", "p.2"]


class TestMergeDomainSolutions:
    def test_weak_merge_caps_citations_to_1_per_doc(self) -> None:
        """Merging two weak-solution partials from same doc_id yields only 1 citation."""
        p1 = _ds_partial("Test Solution", "weak",
                         [{"doc_id": "SRC1", "locator": "p.1", "snippet": "Short."}])
        p2 = _ds_partial("test solution", "weak",   # same title (case-insensitive)
                         [{"doc_id": "SRC1", "locator": "p.2", "snippet": "Longer snippet here."}])
        result = merge_outputs("domain_solutions_from_evidence", [p1, p2])
        sol = result["domains"][0]["focus_areas"][0]["solutions"][0]
        assert sol["evidence_strength"] == "weak"
        assert len(sol["citations"]) == 1
        # Longer snippet preferred
        assert sol["citations"][0]["locator"] == "p.2"

    def test_strong_merge_caps_citations_to_3_per_doc(self) -> None:
        """Merging strong-solution partials that total 4 same-doc citations yields 3."""
        p1 = _ds_partial("Test Solution", "strong", [
            {"doc_id": "SRC1", "locator": "p.1", "snippet": "A."},
            {"doc_id": "SRC1", "locator": "p.2", "snippet": "BB."},
        ])
        p2 = _ds_partial("test solution", "strong", [
            {"doc_id": "SRC1", "locator": "p.3", "snippet": "CCC."},
            {"doc_id": "SRC1", "locator": "p.4", "snippet": "X."},  # shortest tie, latest
        ])
        result = merge_outputs("domain_solutions_from_evidence", [p1, p2])
        sol = result["domains"][0]["focus_areas"][0]["solutions"][0]
        assert sol["evidence_strength"] == "strong"
        assert len(sol["citations"]) == 3
        locators = {c["locator"] for c in sol["citations"]}
        assert "p.3" in locators    # longest snippet
        assert "p.4" not in locators  # dropped


# ---------------------------------------------------------------------------
# _merge_domain_lessons + merge_outputs — domain_lessons_option_b
# ---------------------------------------------------------------------------

def _empty_fa(fa_id: str) -> dict:
    """Build a fully-populated focus area with all nine empty category arrays."""
    return {
        "focus_area_id": fa_id,
        "proven_interventions": [],
        "lessons_learnt": [],
        "recommendations": [],
        "prerequisites": [],
        "operational_barriers": [],
        "governance_process_dependencies": [],
        "evidence_gaps_uncertainty": [],
        "costs_resource_intensity": [],
        "equity_implications": [],
    }


def _dl_partial(
    pi_items: list | None = None,
    cost_items: list | None = None,
) -> dict:
    """Minimal domain_lessons_option_b partial with one focus area."""
    fa = _empty_fa("supervision_models")
    if pi_items:
        fa["proven_interventions"] = pi_items
    if cost_items:
        fa["costs_resource_intensity"] = cost_items
    return {
        "job_id": "domain_lessons_option_b",
        "target_country": "Global",
        "generated_at": "2026-03-01",
        "domains": [{"domain_id": "accountability", "focus_areas": [fa]}],
    }


def _item(title: str, strength: str, doc_id: str, locator: str) -> dict:
    return {
        "item_id": "x",
        "title": title,
        "statement": f"Statement for {title}.",
        "evidence_type": "intervention_effect",
        "evidence_strength": strength,
        "citations": [{"doc_id": doc_id, "source_title": "T", "locator": locator, "snippet": "S."}],
    }


def _cost(title: str, intensity: str, driver: str) -> dict:
    return {
        "item_id": "x",
        "title": title,
        "statement": "Cost statement.",
        "intensity": intensity,
        "cost_drivers": [driver],
        "citations": [{"doc_id": "SRC1", "source_title": "T", "locator": "p.1", "snippet": "S."}],
    }


class TestMergeDomainLessons:
    def test_single_output_passthrough(self) -> None:
        output = _dl_partial([_item("Checklists", "weak", "SRC1", "p.1")])
        result = merge_outputs("domain_lessons_option_b", [output])
        assert result is output

    def test_two_partials_different_titles_both_appear(self) -> None:
        """Items with different titles from two partials are both kept."""
        p1 = _dl_partial([_item("Checklists", "weak", "SRC1", "p.1")])
        p2 = _dl_partial([_item("Peer Supervision", "moderate", "SRC2", "p.5")])
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        pi = result["domains"][0]["focus_areas"][0]["proven_interventions"]
        titles = {i["title"] for i in pi}
        assert "Checklists" in titles
        assert "Peer Supervision" in titles

    def test_same_title_deduplicates_and_upgrades_strength(self) -> None:
        """Same title in two partials → one item with upgraded evidence_strength."""
        p1 = _dl_partial([_item("Checklists", "weak", "SRC1", "p.1")])
        p2 = _dl_partial([_item("checklists", "strong", "SRC2", "p.9")])  # same title, case-insensitive
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        pi = result["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(pi) == 1
        assert pi[0]["evidence_strength"] == "strong"
        assert len(pi[0]["citations"]) == 2

    def test_same_title_deduplicates_citations_by_doc_and_locator(self) -> None:
        """Identical (doc_id, locator) citations are not duplicated."""
        cit = {"doc_id": "SRC1", "source_title": "T", "locator": "p.1", "snippet": "S."}
        item1 = {**_item("Checklists", "weak", "SRC1", "p.1"), "citations": [cit]}
        item2 = {**_item("Checklists", "weak", "SRC1", "p.1"), "citations": [cit]}
        p1 = _dl_partial([item1])
        p2 = _dl_partial([item2])
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        pi = result["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(pi[0]["citations"]) == 1

    def test_cost_item_intensity_upgrade(self) -> None:
        """Lower intensity is upgraded when the same cost item appears in two partials."""
        p1 = _dl_partial(cost_items=[_cost("Travel Budget", "low", "Vehicle fuel")])
        p2 = _dl_partial(cost_items=[_cost("travel budget", "high", "Driver costs")])
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        cri = result["domains"][0]["focus_areas"][0]["costs_resource_intensity"]
        assert len(cri) == 1
        assert cri[0]["intensity"] == "high"
        assert "Vehicle fuel" in cri[0]["cost_drivers"]
        assert "Driver costs" in cri[0]["cost_drivers"]

    def test_item_ids_renumbered_sequentially(self) -> None:
        """After merge, item_ids follow the pattern {abbrev}_{n:03d}."""
        p1 = _dl_partial([_item("Checklists", "weak", "SRC1", "p.1")])
        p2 = _dl_partial([_item("Peer Supervision", "weak", "SRC2", "p.5")])
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        pi = result["domains"][0]["focus_areas"][0]["proven_interventions"]
        ids = {i["item_id"] for i in pi}
        assert "pi_001" in ids
        assert "pi_002" in ids

    def test_unique_item_ids_per_focus_area(self) -> None:
        """After merge, all item_ids within a focus area are unique across all 9 categories."""
        _ALL_CATS = (
            "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
            "operational_barriers", "governance_process_dependencies",
            "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
        )
        p1 = _dl_partial(
            pi_items=[_item("Checklists", "weak", "SRC1", "p.1")],
            cost_items=[_cost("Travel Budget", "low", "Vehicle fuel")],
        )
        p2 = _dl_partial(
            pi_items=[_item("Peer Supervision", "moderate", "SRC2", "p.5")],
            cost_items=[_cost("travel budget", "high", "Driver costs")],
        )
        result = merge_outputs("domain_lessons_option_b", [p1, p2])
        fa = result["domains"][0]["focus_areas"][0]
        all_ids = [
            item["item_id"]
            for cat in _ALL_CATS
            for item in fa.get(cat, [])
        ]
        assert len(all_ids) == len(set(all_ids)), f"Duplicate item_ids in focus area: {all_ids}"
