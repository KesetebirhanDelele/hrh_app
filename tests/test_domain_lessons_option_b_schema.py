"""Schema validation tests for domain_lessons_option_b."""
import copy

import pytest

from app.core.validators import SchemaValidationError, validate_output

SCHEMA = "schemas/domain_lessons_option_b.schema.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _citation(doc_id: str = "SRC1") -> dict:
    return {
        "doc_id": doc_id,
        "source_title": "Vallieres et al. BMC Health Services Research 2018",
        "locator": "Section 3.2, p. 45",
        "snippet": "Districts using structured checklists saw a 23% improvement in protocol adherence among HEWs.",
    }


def _item(item_id: str = "accountability_supervision_models_pi_1") -> dict:
    return {
        "item_id": item_id,
        "title": "Structured Supervisory Checklists",
        "statement": "Districts using structured checklists saw a 23% improvement in protocol adherence.",
        "evidence_type": "intervention_effect",
        "evidence_strength": "moderate",
        "citations": [_citation()],
    }


def _rec_item(item_id: str = "rec_001") -> dict:
    return {
        "item_id": item_id,
        "title": "Integrate Supervision into Performance Appraisal",
        "statement": "Supervision outcomes should be formally integrated into annual performance appraisals.",
        "evidence_type": "recommendation_only",
        "evidence_strength": "moderate",
        "citations": [_citation()],
    }


def _gap_item(item_id: str = "egu_001") -> dict:
    return {
        "item_id": item_id,
        "title": "Lack of Longitudinal Supervision Data",
        "statement": "No longitudinal studies track supervisory frequency against health outcomes over multi-year periods.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": [_citation()],
    }


def _bar_item_pass(item_id: str = "bar_001") -> dict:
    """Barrier item whose snippet contains 'inadequate' — must pass."""
    return {
        "item_id": item_id,
        "title": "IT Infrastructure Gaps",
        "statement": "Inadequate IT infrastructure impeded digital attendance reporting.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.4",
            "snippet": "hurdles included inadequate IT infrastructure such as computers, internet, and electricity.",
        }],
    }


def _bar_item_fail(item_id: str = "bar_001") -> dict:
    """Barrier item whose snippet only describes a cause with no barrier keywords — must fail."""
    return {
        "item_id": item_id,
        "title": "Low Supervision Rates",
        "statement": "Low supervision rates were associated with higher absenteeism.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.2",
            "snippet": "causes included low supervision (56%) and low pay (44%).",
        }],
    }


def _cost_item(item_id: str = "cri_001") -> dict:
    return {
        "item_id": item_id,
        "title": "Supervisory Checklist Resource Intensity",
        "statement": "Structured supervisory programmes require protected travel budgets.",
        "intensity": "medium",
        "cost_drivers": ["Supervisor travel", "Training time"],
        "citations": [_citation()],
    }


def _con_item(item_id: str = "con_001") -> dict:
    return {
        "item_id": item_id,
        "title": "Delayed Patient Access",
        "statement": "Absenteeism led to delayed access to care for patients.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.5",
            "snippet": "Absenteeism resulted in delayed access to care and increased workload for present staff.",
        }],
    }


def _empty_focus_area(focus_area_id: str) -> dict:
    return {
        "focus_area_id": focus_area_id,
        "proven_interventions": [],
        "lessons_learnt": [],
        "recommendations": [],
        "prerequisites": [],
        "operational_barriers": [],
        "governance_process_dependencies": [],
        "evidence_gaps_uncertainty": [],
        "costs_resource_intensity": [],
        "equity_implications": [],
        "consequences_impacts": [],
    }


# Minimal valid payload: 1 domain, 1 focus area with items across proven_interventions,
# recommendations, evidence_gaps_uncertainty, and costs_resource_intensity — confirming
# evidence_strength is accepted (and therefore required) in all Item categories.
VALID_PAYLOAD: dict = {
    "job_id": "domain_lessons_option_b",
    "target_country": "Ethiopia",
    "generated_at": "2026-03-01",
    "domains": [
        {
            "domain_id": "accountability",
            "focus_areas": [
                {
                    "focus_area_id": "supervision_models",
                    "proven_interventions": [_item()],
                    "lessons_learnt": [],
                    "recommendations": [_rec_item()],
                    "prerequisites": [],
                    "operational_barriers": [],
                    "governance_process_dependencies": [],
                    "evidence_gaps_uncertainty": [_gap_item()],
                    "costs_resource_intensity": [_cost_item()],
                    "equity_implications": [],
                    "consequences_impacts": [],
                }
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

def test_valid_payload_passes() -> None:
    validate_output(VALID_PAYLOAD, SCHEMA)


def test_all_empty_focus_area_passes() -> None:
    """A focus area with no extracted items in any category is valid."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0] = _empty_focus_area("supervision_models")
    validate_output(payload, SCHEMA)


def test_item_with_mechanism_passes() -> None:
    """Optional mechanism field is accepted when present."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["mechanism"] = (
        "Checklists standardise expectations, increasing protocol adherence."
    )
    validate_output(payload, SCHEMA)


def test_cost_item_without_cost_drivers_passes() -> None:
    """cost_drivers is optional; omitting it should still pass."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    del payload["domains"][0]["focus_areas"][0]["costs_resource_intensity"][0]["cost_drivers"]
    validate_output(payload, SCHEMA)


# ---------------------------------------------------------------------------
# Missing required top-level fields
# ---------------------------------------------------------------------------

def test_missing_generated_at_fails() -> None:
    bad = {k: v for k, v in VALID_PAYLOAD.items() if k != "generated_at"}
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(bad, SCHEMA)
    assert "generated_at" in str(exc_info.value)


def test_wrong_job_id_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["job_id"] = "domain_solutions_from_evidence"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------

def test_citation_missing_source_title_fails() -> None:
    """source_title is required in LocalCitation for this job."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    del bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["source_title"]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(bad, SCHEMA)
    assert "source_title" in str(exc_info.value)


def test_citation_snippet_too_long_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"] = "x" * 301
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_item_empty_citations_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"] = []
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------

def test_invalid_evidence_type_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["evidence_type"] = "high"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_invalid_evidence_strength_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["evidence_strength"] = "none"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_recommendation_without_evidence_strength_fails() -> None:
    """evidence_strength is required on recommendations items, not just proven_interventions."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    del bad["domains"][0]["focus_areas"][0]["recommendations"][0]["evidence_strength"]
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_evidence_gap_without_evidence_strength_fails() -> None:
    """evidence_strength is required on evidence_gaps_uncertainty items."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    del bad["domains"][0]["focus_areas"][0]["evidence_gaps_uncertainty"][0]["evidence_strength"]
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_invalid_cost_intensity_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["costs_resource_intensity"][0]["intensity"] = "very_high"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_invalid_domain_id_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["domain_id"] = "unknown_domain"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_invalid_focus_area_id_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["focus_area_id"] = "not_a_real_focus_area"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


# ---------------------------------------------------------------------------
# Structure: missing category arrays
# ---------------------------------------------------------------------------

def test_missing_category_array_fails() -> None:
    """All ten category arrays are required in a focus area."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    del bad["domains"][0]["focus_areas"][0]["recommendations"]
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_additional_property_on_item_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["extra_field"] = "not allowed"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_additional_property_on_citation_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["source_url"] = "https://example.org"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


# ---------------------------------------------------------------------------
# item_id uniqueness within a focus area
# ---------------------------------------------------------------------------

def test_duplicate_item_id_within_focus_area_fails() -> None:
    """Two items in different categories of the same focus area must not share an item_id."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    shared_id = bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["item_id"]
    # Force the recommendation item to use the same id
    bad["domains"][0]["focus_areas"][0]["recommendations"][0]["item_id"] = shared_id
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(bad, SCHEMA)
    assert shared_id in str(exc_info.value)


# ---------------------------------------------------------------------------
# operational_barriers barrier-keyword validation
# ---------------------------------------------------------------------------

def test_barrier_item_with_inadequate_in_snippet_passes() -> None:
    """operational_barriers item containing 'inadequate' in its snippet passes."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [_bar_item_pass()]
    validate_output(payload, SCHEMA)


def test_barrier_item_without_barrier_language_fails() -> None:
    """operational_barriers item whose snippet only describes a cause (no barrier keyword) fails."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [_bar_item_fail()]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(payload, SCHEMA)
    assert "operational_barriers" in str(exc_info.value)


# ---------------------------------------------------------------------------
# consequences_impacts — schema tests
# ---------------------------------------------------------------------------

def test_consequences_impacts_accepted() -> None:
    """Schema accepts a valid consequences_impacts item."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [_con_item()]
    validate_output(payload, SCHEMA)


def test_missing_consequences_impacts_fails() -> None:
    """Omitting consequences_impacts from a focus area fails schema validation."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    del bad["domains"][0]["focus_areas"][0]["consequences_impacts"]
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


# ---------------------------------------------------------------------------
# consequences_impacts — validator tests
# ---------------------------------------------------------------------------

def test_consequences_impacts_item_with_impact_keywords_passes() -> None:
    """Validator passes a consequences_impacts item whose snippet contains 'resulted in'."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [_con_item()]
    validate_output(payload, SCHEMA)  # should not raise


def test_consequences_impacts_item_without_impact_keywords_fails() -> None:
    """Validator rejects a consequences_impacts item whose snippet has no impact keywords."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad_item = {
        "item_id": "con_001",
        "title": "Some Impact",
        "statement": "HRH failures affected the system.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.1",
            "snippet": "The PSS tool was administered to health workers in sub-Saharan Africa.",
        }],
    }
    bad["domains"][0]["focus_areas"][0]["consequences_impacts"] = [bad_item]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(bad, SCHEMA)
    assert "consequences_impacts" in str(exc_info.value)


def test_barrier_with_impact_keywords_hints_consequences() -> None:
    """Barrier item with impact-language snippet (but no barrier language) hints to use consequences_impacts."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    impact_barrier = {
        "item_id": "bar_001",
        "title": "Delayed Patient Access",
        "statement": "Absenteeism resulted in delayed access to care.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.5",
            "snippet": "Absenteeism resulted in delayed access to care and increased workload for present staff.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [impact_barrier]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(payload, SCHEMA)
    assert "consequences_impacts" in str(exc_info.value)


# ---------------------------------------------------------------------------
# consequences_impacts — merger test
# ---------------------------------------------------------------------------

def test_merge_consequences_impacts_deduplicates() -> None:
    """Two partial outputs with the same-titled con_item → one merged item, combined citations."""
    from app.analyze.merger import merge_outputs

    cit1 = {
        "doc_id": "SRC1",
        "source_title": "Source One",
        "locator": "p.1",
        "snippet": "Absenteeism resulted in delayed access to care.",
    }
    cit2 = {
        "doc_id": "SRC2",
        "source_title": "Source Two",
        "locator": "p.3",
        "snippet": "Increased workload led to burnout among remaining staff.",
    }
    item_base = {
        "item_id": "con_001",
        "title": "Delayed Patient Access",
        "statement": "Absenteeism caused delayed access.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [cit1],
    }
    item_dup = dict(item_base) | {"citations": [cit2]}

    fa = {
        "focus_area_id": "measurement_approaches",
        **{cat: [] for cat in (
            "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
            "operational_barriers", "governance_process_dependencies",
            "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
        )},
        "consequences_impacts": [item_base],
    }
    fa2 = dict(fa) | {"consequences_impacts": [item_dup]}

    partial1 = {
        "job_id": "domain_lessons_option_b",
        "target_country": "Ethiopia",
        "generated_at": "2026-01-01",
        "domains": [{"domain_id": "absenteeism", "focus_areas": [fa]}],
    }
    partial2 = {
        "job_id": "domain_lessons_option_b",
        "target_country": "Ethiopia",
        "generated_at": "2026-01-01",
        "domains": [{"domain_id": "absenteeism", "focus_areas": [fa2]}],
    }

    merged = merge_outputs("domain_lessons_option_b", [partial1, partial2])
    merged_fa = merged["domains"][0]["focus_areas"][0]
    con_items = merged_fa["consequences_impacts"]
    assert len(con_items) == 1, f"Expected 1 merged item, got {len(con_items)}"
    assert len(con_items[0]["citations"]) == 2


# ---------------------------------------------------------------------------
# XLSX renderer — consequences_impacts appears in items sheet
# ---------------------------------------------------------------------------

def test_xlsx_consequences_impacts_not_in_menu() -> None:
    """consequences_impacts items are NOT in the lean 10-col MENU — neither as rows nor as
    fa-level aggregations. The category stays in JSON but never produces MENU output."""
    openpyxl = pytest.importorskip("openpyxl")
    load_workbook = openpyxl.load_workbook
    import tempfile
    from pathlib import Path
    from app.render.xlsx import render_xlsx

    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [_con_item()]

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name

    try:
        render_xlsx("domain_lessons_option_b", payload, Path(tmp_path))
        wb = load_workbook(tmp_path)
        ws = wb["MENU"]
        # The consequences_impacts statement should NOT appear in any MENU cell
        all_vals = [str(cell.value) for row in ws.iter_rows(min_row=2) for cell in row if cell.value]
        assert not any("Delayed Patient Access" in v for v in all_vals), (
            f"consequences_impacts title leaked into MENU. Values: {[v for v in all_vals if 'Delayed' in v]}"
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# consequences_impacts — expanded keywords (D)
# ---------------------------------------------------------------------------

def test_consequences_impacts_passes_for_workload_snippet() -> None:
    """'workload' is a primary impact keyword — item passes without fallback."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_001",
        "title": "Increased Workload",
        "statement": "Absenteeism increases workload for remaining staff.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC2",
            "source_title": "Absenteeism in SSA",
            "locator": "p.12",
            "snippet": "high workload for remaining healthcare workers (n=4, 29%).",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


def test_consequences_impacts_passes_for_stress_snippet() -> None:
    """'stress' is a newly added impact keyword — item passes."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_002",
        "title": "Staff Stress Due to Understaffing",
        "statement": "Chronic understaffing caused significant staff stress.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC2",
            "source_title": "Absenteeism in SSA",
            "locator": "p.13",
            "snippet": "Nurses reported overwhelming stress and strain from working understaffed shifts.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


def test_consequences_impacts_fallback_passes_when_statement_has_impact_and_snippet_has_broad_term() -> None:
    """Fallback: statement has 'led to' + snippet has 'patient' → validator accepts."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_003",
        "title": "Patient Harm from Absenteeism",
        "statement": "Absenteeism led to harm for patients who could not access care.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC2",
            "source_title": "Absenteeism in SSA",
            "locator": "p.12",
            # Snippet cut before the word "led" appears — broad term "patient" present
            "snippet": "Consequences for patient well-being were documented across nine studies.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


def test_consequences_impacts_fallback_fails_when_both_checks_miss() -> None:
    """Fallback does not rescue a truly neutral snippet with no broad terms either."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_004",
        "title": "Unclear Impact",
        "statement": "The PSS tool was validated in seven countries.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.1",
            "snippet": "The PSS was administered to enumerators in local and English languages.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(payload, SCHEMA)
    assert "consequences_impacts" in str(exc_info.value)


# ---------------------------------------------------------------------------
# operational_barriers — statement fallback (Fix C)
# ---------------------------------------------------------------------------

def test_barrier_no_keyword_snippet_with_barrier_statement_passes() -> None:
    """operational_barriers item whose snippet contains no barrier keywords passes when
    its statement contains barrier-proxy language ('time-intensive', 'requires', etc.).

    This covers the real case where the LLM quotes a sentence fragment that doesn't
    include a recognised barrier keyword, but the statement clearly describes a constraint.
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    bar_item = {
        "item_id": "bar_001",
        "title": "Existing Tools Are Resource Intensive",
        "statement": "Existing supervision tools are lengthy and time-intensive, requiring substantial resources.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p. 2 (part 1)",
            # Snippet contains the source text but has no barrier keyword (no "lack of", "inadequate", etc.)
            "snippet": "these tools are lengthy, time-intensive, and require substantial programmatic input",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [bar_item]
    validate_output(payload, SCHEMA)  # must not raise


def test_barrier_no_keyword_snippet_neutral_statement_fails() -> None:
    """operational_barriers item with no barrier keywords in snippet OR statement fails."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    bar_item = {
        "item_id": "bar_001",
        "title": "Supervision Gap",
        "statement": "Supervision rates were low in rural areas.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.3",
            # Neutral snippet — causal/statistical framing only, no barrier keywords
            "snippet": "causes included low supervision rates (56%) and low pay (44%).",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [bar_item]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(payload, SCHEMA)
    assert "operational_barriers" in str(exc_info.value)


# ---------------------------------------------------------------------------
# consequences_impacts — expanded keyword coverage (false-negative fixes)
# ---------------------------------------------------------------------------

def test_consequences_impacts_passes_for_impact_keyword() -> None:
    """'impact' is a newly added keyword — snippet 'The impact of absenteeism ... is profound.' passes."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_010",
        "title": "Impact of Absenteeism on Patients and Workers",
        "statement": "The impact of absenteeism on patients and healthcare workers is profound.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.7",
            "snippet": "The impact of absenteeism on patients and healthcare workers is profound.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


def test_consequences_impacts_passes_for_patient_safety_keyword() -> None:
    """'patient safety' is a newly added keyword — 'Compromised patient safety and outcomes.' passes."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_011",
        "title": "Compromised Patient Safety",
        "statement": "Staff shortages directly compromised patient safety and care outcomes.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.8",
            "snippet": "Compromised patient safety and outcomes.",
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


def test_consequences_impacts_passes_for_suffering_keyword() -> None:
    """'suffering' is a newly added keyword — snippet about staff shortages causing suffering passes."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    item = {
        "item_id": "con_012",
        "title": "Suffering Caused by Staff Shortages",
        "statement": "Shortages of medical staff cause suffering for people in need of care.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.9",
            "snippet": (
                "Needless to say, the shortages of medical staff cause suffering for people "
                "in need of care and could have fatal consequences."
            ),
        }],
    }
    payload["domains"][0]["focus_areas"][0]["consequences_impacts"] = [item]
    validate_output(payload, SCHEMA)  # must not raise


# ---------------------------------------------------------------------------
# applicable_countries — schema and renderer tests
# ---------------------------------------------------------------------------

def test_item_with_applicable_countries_passes() -> None:
    """Item with applicable_countries array is valid."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = [
        "Ethiopia", "Kenya"
    ]
    validate_output(payload, SCHEMA)  # must not raise


def test_item_with_empty_applicable_countries_passes() -> None:
    """Item with applicable_countries as empty array is valid."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = []
    validate_output(payload, SCHEMA)  # must not raise


def test_item_without_applicable_countries_passes() -> None:
    """Item without applicable_countries at all (field omitted) remains valid."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    # Ensure field is absent (default fixture has no applicable_countries)
    assert "applicable_countries" not in payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]
    validate_output(payload, SCHEMA)  # must not raise


def test_item_applicable_countries_non_string_fails() -> None:
    """applicable_countries containing a non-string entry fails schema validation."""
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = [123]
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_cost_item_with_applicable_countries_passes() -> None:
    """CostItem also accepts applicable_countries."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["costs_resource_intensity"][0]["applicable_countries"] = [
        "Bangladesh"
    ]
    validate_output(payload, SCHEMA)  # must not raise


def test_xlsx_applicable_countries_not_in_lean_menu() -> None:
    """Lean 10-col MENU does not have a 'Country of the intervention' column.
    applicable_countries is stored in JSON but not rendered in the MENU sheet."""
    openpyxl = pytest.importorskip("openpyxl")
    import tempfile
    from pathlib import Path
    from app.render.xlsx import render_xlsx

    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = [
        "Ethiopia", "Kenya"
    ]

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name
    try:
        render_xlsx("domain_lessons_option_b", payload, Path(tmp_path))
        wb = openpyxl.load_workbook(tmp_path)
        ws = wb["MENU"]
        headers = [cell.value for cell in ws[1]]
        # The lean 10-col MENU does not include 'Country of the intervention'
        assert "Country of the intervention" not in headers, (
            f"Lean 10-col MENU should not include Country column. Headers: {headers}"
        )
        assert len(headers) == 10, f"Expected 10 headers, got {len(headers)}: {headers}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_xlsx_applicable_countries_field_preserved_in_json() -> None:
    """applicable_countries field is preserved in the JSON output (schema accepts it)."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = [
        "Ethiopia", "Kenya"
    ]
    validate_output(payload, SCHEMA)  # must not raise


def test_md_applicable_countries_rendered() -> None:
    """Markdown output includes 'Countries:' line when applicable_countries is present."""
    from app.render.md import render_markdown

    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["applicable_countries"] = [
        "Ethiopia", "Kenya"
    ]
    md = render_markdown("domain_lessons_option_b", payload)
    assert "Countries: Ethiopia, Kenya" in md


def test_md_applicable_countries_absent_when_empty() -> None:
    """Markdown output has no 'Countries:' line when applicable_countries is absent."""
    from app.render.md import render_markdown

    payload = copy.deepcopy(VALID_PAYLOAD)
    md = render_markdown("domain_lessons_option_b", payload)
    assert "Countries:" not in md


# ---------------------------------------------------------------------------
# Task 4F — XLSX MENU + CITATIONS structure tests
# ---------------------------------------------------------------------------

_MENU_EXPECTED_HEADERS = [
    "Intervention ID",
    "Title",
    "HRH-II Package Component",
    "Description",
    "Evidence status",
    "Strength of evidence",
    "Evidence design/type",
    "Target cadre & setting",
    "Implementation considerations",
    "Expected impact",
]


def _render_to_wb(payload: dict):
    """Helper: render payload to xlsx and return openpyxl workbook."""
    openpyxl = pytest.importorskip("openpyxl")
    import tempfile
    from pathlib import Path
    from app.render.xlsx import render_xlsx

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name
    try:
        render_xlsx("domain_lessons_option_b", payload, Path(tmp_path))
        wb = openpyxl.load_workbook(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return wb


class TestXlsxMenuStructure:
    """XLSX MENU sheet has exactly 10 columns in the correct order (lean solutions menu)."""

    def test_menu_sheet_exists(self) -> None:
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        assert "MENU" in wb.sheetnames

    def test_menu_has_10_columns(self) -> None:
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        headers = [cell.value for cell in wb["MENU"][1]]
        assert len(headers) == 10, f"Expected 10 columns, got {len(headers)}: {headers}"

    def test_menu_column_order(self) -> None:
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        headers = [cell.value for cell in wb["MENU"][1]]
        assert headers == _MENU_EXPECTED_HEADERS, (
            f"Column order mismatch.\nExpected: {_MENU_EXPECTED_HEADERS}\nGot:      {headers}"
        )

    def test_menu_intervention_id_populated(self) -> None:
        """Intervention ID column is non-empty for each data row."""
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        ws = wb["MENU"]
        ids = [row[0] for row in ws.iter_rows(min_row=2, values_only=True) if row[0]]
        assert len(ids) > 0, "No rows with Intervention ID found in MENU sheet"

    def test_menu_hrh_package_component_is_col3(self) -> None:
        """HRH-II Package Component is col 3 (index 2) and encodes domain → focus_area."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"] = [_item()]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        components = [row[2] for row in ws.iter_rows(min_row=2, values_only=True) if row[2]]
        assert any("accountability" in c and "supervision_models" in c for c in components), (
            f"Expected domain+focus_area in HRH-II Package Component (col 3). Got: {components}"
        )


class TestXlsxCitationsSheet:
    """XLSX CITATIONS sheet has correct structure."""

    def test_citations_sheet_exists(self) -> None:
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        assert "CITATIONS" in wb.sheetnames

    def test_citations_headers(self) -> None:
        """CITATIONS sheet has exactly 5 columns (Intervention ID, doc_id, source_title, locator, snippet)."""
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        headers = [cell.value for cell in wb["CITATIONS"][1]]
        expected = ["Intervention ID", "doc_id", "source_title", "locator", "snippet"]
        assert headers == expected, f"CITATIONS headers mismatch.\nExpected: {expected}\nGot: {headers}"

    def test_citations_one_row_per_citation(self) -> None:
        """Each citation from MENU rows (proven_interventions + recommendations) produces one row."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        # VALID_PAYLOAD has: 1 proven_intervention + 1 recommendation as MENU rows (2 citations)
        # gap and cost items are NOT MENU rows → not in CITATIONS
        wb = _render_to_wb(payload)
        ws = wb["CITATIONS"]
        data_rows = list(ws.iter_rows(min_row=2, values_only=True))
        assert len(data_rows) == 2, f"Expected 2 citation rows (pi + rec only), got {len(data_rows)}"

    def test_citations_intervention_id_matches_menu(self) -> None:
        """Intervention IDs in CITATIONS match those in MENU."""
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        menu_ids = {row[0] for row in wb["MENU"].iter_rows(min_row=2, values_only=True) if row[0]}
        cit_ids = {row[0] for row in wb["CITATIONS"].iter_rows(min_row=2, values_only=True) if row[0]}
        assert cit_ids.issubset(menu_ids), (
            f"CITATIONS has IDs not in MENU: {cit_ids - menu_ids}"
        )

    def test_citations_no_extra_sheets(self) -> None:
        """Only MENU and CITATIONS sheets are produced — no legacy 'items'/'costs' sheets."""
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        assert "items" not in wb.sheetnames
        assert "costs" not in wb.sheetnames
        assert set(wb.sheetnames) == {"MENU", "CITATIONS"}


# ---------------------------------------------------------------------------
# Task 4F — merger dedupe + intervention_id tests
# ---------------------------------------------------------------------------

class TestMergerDedupeAndInterventionId:
    """Merger correctly deduplicates items and assigns stable intervention_ids."""

    def _make_partial(self, items: list, cat: str = "proven_interventions") -> dict:
        fa: dict = {
            "focus_area_id": "supervision_models",
            **{c: [] for c in (
                "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
                "operational_barriers", "governance_process_dependencies",
                "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
                "consequences_impacts",
            )},
        }
        fa[cat] = items
        return {
            "job_id": "domain_lessons_option_b",
            "target_country": "Ethiopia",
            "generated_at": "2026-01-01",
            "domains": [{"domain_id": "accountability", "focus_areas": [fa]}],
        }

    def test_identical_title_deduplicates_to_one_item(self) -> None:
        from app.analyze.merger import merge_outputs
        cit1 = {**_citation("SRC1"), "locator": "p.1"}
        cit2 = {**_citation("SRC2"), "locator": "p.2", "source_title": "Source Two",
                "snippet": "Districts saw improvement."}
        item_a = dict(_item()) | {"citations": [cit1]}
        item_b = dict(_item()) | {"citations": [cit2]}
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_partial([item_a]), self._make_partial([item_b])])
        items = merged["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(items) == 1, f"Expected 1 merged item, got {len(items)}"
        assert len(items[0]["citations"]) == 2

    def test_case_insensitive_title_deduplicates(self) -> None:
        from app.analyze.merger import merge_outputs
        item_upper = dict(_item()) | {"title": "Structured Supervisory Checklists"}
        item_lower = dict(_item()) | {"title": "structured supervisory checklists"}
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_partial([item_upper]), self._make_partial([item_lower])])
        items = merged["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(items) == 1

    def test_different_titles_produce_two_items(self) -> None:
        from app.analyze.merger import merge_outputs
        item_a = dict(_item("id_1")) | {"title": "Checklists"}
        item_b = dict(_item("id_2")) | {"title": "Performance Contracts"}
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_partial([item_a]), self._make_partial([item_b])])
        items = merged["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(items) == 2

    def test_intervention_id_assigned_in_merged_output(self) -> None:
        from app.analyze.merger import merge_outputs
        merged = merge_outputs("domain_lessons_option_b", [self._make_partial([_item()])])
        item = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        assert "intervention_id" in item, "intervention_id not set by merger"
        assert item["intervention_id"], "intervention_id is empty"

    def test_applicable_countries_union_across_partials(self) -> None:
        from app.analyze.merger import merge_outputs
        item_a = dict(_item()) | {"applicable_countries": ["Ethiopia"]}
        item_b = dict(_item()) | {"applicable_countries": ["Kenya"]}
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_partial([item_a]), self._make_partial([item_b])])
        item = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        countries = item.get("applicable_countries", [])
        assert "Ethiopia" in countries and "Kenya" in countries, (
            f"Expected union of countries, got: {countries}"
        )


# ---------------------------------------------------------------------------
# Session 5 — MENU redesign tests
# ---------------------------------------------------------------------------

def _det_item(item_id: str = "pi_002") -> dict:
    """proven_interventions item with evidence_type=determinant_mechanism (FORBIDDEN in MENU)."""
    return {
        "item_id": item_id,
        "title": "Low Supervision Rate Predictor",
        "statement": "Low supervision rate is associated with higher absenteeism.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "weak",
        "citations": [_citation()],
    }


class TestMenuEligibilityFilter:
    """MENU rows come ONLY from proven_interventions + recommendations; determinant items excluded."""

    def test_only_pi_and_rec_produce_menu_rows(self) -> None:
        """lessons_learnt, prerequisites, operational_barriers, etc. produce NO MENU rows."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        # Clear proven_interventions so only non-MENU categories have content
        fa["proven_interventions"] = []
        fa["lessons_learnt"] = [dict(_item("ll_001")) | {"evidence_type": "determinant_mechanism"}]
        fa["operational_barriers"] = [_bar_item_pass()]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        data_rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if any(row)]
        # Only the recommendation from VALID_PAYLOAD should remain
        assert len(data_rows) == 1, (
            f"Expected 1 MENU row (recommendation only), got {len(data_rows)}"
        )

    def test_determinant_mechanism_in_proven_interventions_excluded(self) -> None:
        """Items in proven_interventions with evidence_type=determinant_mechanism are NOT MENU rows."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_det_item()]  # only determinant item
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        data_rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if any(row)]
        titles = [row[1] for row in data_rows if row[1]]
        assert "Low Supervision Rate Predictor" not in titles, (
            f"determinant_mechanism item appeared in MENU: {titles}"
        )

    def test_evidence_status_proven_for_pi_category(self) -> None:
        """proven_interventions category maps to 'proven' in Evidence status col (index 4)."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [dict(_item()) | {"evidence_type": "intervention_effect"}]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        statuses = [row[4] for row in ws.iter_rows(min_row=2, values_only=True) if row[4]]
        assert "proven" in statuses, f"Expected 'proven' in Evidence status col (index 4). Got: {statuses}"

    def test_evidence_status_proven_for_validated_tool(self) -> None:
        """validated_tool_or_metric in proven_interventions also maps to 'proven'."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [dict(_item()) | {"evidence_type": "validated_tool_or_metric"}]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        statuses = [row[4] for row in ws.iter_rows(min_row=2, values_only=True) if row[4]]
        assert "proven" in statuses, f"Expected 'proven' in Evidence status col. Got: {statuses}"

    def test_evidence_status_recommendation_only_for_rec(self) -> None:
        """recommendations category maps to 'recommendation_only' in Evidence status col (index 4)."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = []
        fa["recommendations"] = [_rec_item()]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        statuses = [row[4] for row in ws.iter_rows(min_row=2, values_only=True) if row[4]]
        assert "recommendation_only" in statuses, (
            f"Expected 'recommendation_only' in Evidence status col (index 4). Got: {statuses}"
        )

    def test_evidence_design_type_in_col7(self) -> None:
        """evidence_design_type field appears in Evidence design/type col (index 6)."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [dict(_item()) | {"evidence_design_type": "RCT"}]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        design_vals = [row[6] for row in ws.iter_rows(min_row=2, values_only=True) if row[6]]
        assert "RCT" in design_vals, f"evidence_design_type 'RCT' not in col 7 (index 6). Got: {design_vals}"

    def test_non_menu_categories_not_in_any_column(self) -> None:
        """operational_barriers and consequences_impacts produce NO MENU rows or fa-level agg columns."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_item()]
        fa["recommendations"] = []
        fa["operational_barriers"] = [_bar_item_pass()]
        fa["consequences_impacts"] = [_con_item()]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        # 10-col MENU: non-menu category content must not appear in any column
        all_vals = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            for v in row:
                if v:
                    all_vals.add(str(v))
        # The delayed access statement from consequences_impacts should NOT be in any MENU cell
        assert not any("Delayed Patient Access" in v for v in all_vals), (
            f"consequences_impacts content leaked into MENU: {[v for v in all_vals if 'Delayed' in v]}"
        )


class TestSolutionsOnlyValidator:
    """_validate_proven_interventions_are_actions raises on determinant_mechanism in proven_interventions."""

    def test_determinant_in_proven_interventions_raises(self) -> None:
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"] = [_det_item()]
        with pytest.raises(SchemaValidationError, match="determinant_mechanism"):
            validate_output(payload, SCHEMA)

    def test_intervention_effect_in_proven_interventions_passes(self) -> None:
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"] = [_item()]
        validate_output(payload, SCHEMA)  # must not raise

    def test_determinant_in_lessons_learnt_passes(self) -> None:
        """determinant_mechanism in lessons_learnt is valid — only proven_interventions is checked."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        ll = dict(_item("ll_001")) | {"evidence_type": "determinant_mechanism"}
        payload["domains"][0]["focus_areas"][0]["lessons_learnt"] = [ll]
        validate_output(payload, SCHEMA)  # must not raise


class TestMergerDedupeEvidenceType:
    """Dedupe key includes evidence_type — items with same title but different type stay separate."""

    def _make_partial(self, pi_items: list, rec_items: list) -> dict:
        fa: dict = {
            "focus_area_id": "supervision_models",
            **{c: [] for c in (
                "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
                "operational_barriers", "governance_process_dependencies",
                "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
                "consequences_impacts",
            )},
        }
        fa["proven_interventions"] = pi_items
        fa["recommendations"] = rec_items
        return {
            "job_id": "domain_lessons_option_b",
            "target_country": "Ethiopia",
            "generated_at": "2026-01-01",
            "domains": [{"domain_id": "accountability", "focus_areas": [fa]}],
        }

    def test_same_title_diff_evidence_type_not_merged(self) -> None:
        """Same title in proven_interventions (intervention_effect) and recommendations
        (recommendation_only) must produce 2 items — not merged."""
        from app.analyze.merger import merge_outputs
        pi = dict(_item("pi_001")) | {"evidence_type": "intervention_effect", "title": "Same Title"}
        rec = dict(_rec_item("rec_001")) | {"evidence_type": "recommendation_only", "title": "Same Title"}
        partial = self._make_partial([pi], [rec])
        merged = merge_outputs("domain_lessons_option_b", [partial])
        pi_items = merged["domains"][0]["focus_areas"][0]["proven_interventions"]
        rec_items = merged["domains"][0]["focus_areas"][0]["recommendations"]
        assert len(pi_items) == 1 and len(rec_items) == 1, (
            f"Expected 1 pi + 1 rec (not merged). Got pi={len(pi_items)}, rec={len(rec_items)}"
        )

    def test_same_title_same_evidence_type_merges(self) -> None:
        """Same title AND same evidence_type across partials should still merge to 1 item."""
        from app.analyze.merger import merge_outputs
        cit1 = {**_citation("SRC1"), "locator": "p.1"}
        cit2 = {**_citation("SRC2"), "locator": "p.2", "source_title": "Source Two",
                "snippet": "Districts saw improvement."}
        pi_a = dict(_item("pi_001")) | {"citations": [cit1], "evidence_type": "intervention_effect"}
        pi_b = dict(_item("pi_002")) | {"citations": [cit2], "evidence_type": "intervention_effect"}
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_partial([pi_a], []), self._make_partial([pi_b], [])])
        pi_items = merged["domains"][0]["focus_areas"][0]["proven_interventions"]
        assert len(pi_items) == 1, f"Expected 1 merged pi item, got {len(pi_items)}"
        assert len(pi_items[0]["citations"]) == 2


# ---------------------------------------------------------------------------
# Session 6 — new optional fields: schema, renderer, merger
# ---------------------------------------------------------------------------

def _rich_item(item_id: str = "pi_001") -> dict:
    """proven_interventions item with all new optional fields populated."""
    return {
        "item_id": item_id,
        "title": "Structured Supervisory Checklists",
        "statement": "Districts using structured checklists saw a 23% improvement in protocol adherence.",
        "evidence_summary": "Supervisory checklists improved protocol adherence by 23% in a controlled pre-post study.",
        "mechanism": "Checklists standardise expectations, reducing variation in supervisory feedback.",
        "evidence_design_type": "quasi-experimental",
        "target_cadre_setting": "HEWs, rural health posts",
        "governance_operating_model": "Owner: District health officer\nActors: Supervisors visit monthly\nData/artifacts: Completed checklist\nCadence/trigger: Monthly; escalate if score <70%",
        "intervention_risks": [
            "Checklists may be completed retrospectively",
            "HEWs may perform only during visit",
        ],
        "expected_impact": "Observed: 23% improvement in protocol adherence among HEWs.",
        "evidence_type": "intervention_effect",
        "evidence_strength": "moderate",
        "citations": [_citation()],
    }


class TestSchemaNewFields:
    """New optional fields are accepted by schema validation."""

    def test_rich_item_passes_schema(self) -> None:
        """Item with all new optional fields populated validates without error."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"] = [_rich_item()]
        validate_output(payload, SCHEMA)  # must not raise

    def test_intervention_risks_is_array(self) -> None:
        """intervention_risks must be an array; a string value fails schema."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        bad = dict(_rich_item()) | {"intervention_risks": "not an array"}
        payload["domains"][0]["focus_areas"][0]["proven_interventions"] = [bad]
        with pytest.raises(Exception):
            validate_output(payload, SCHEMA)


class TestMenuRendererNewFields:
    """MENU renderer maps new fields to correct 10-col positions and applies fallbacks."""

    def test_intervention_risks_in_col9_when_present(self) -> None:
        """intervention_risks bullets → Implementation considerations col (index 8) when populated."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_rich_item()]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col9_vals = [row[8] for row in ws.iter_rows(min_row=2, values_only=True) if row[8]]
        assert any("retrospectively" in str(v) for v in col9_vals), (
            f"intervention_risks not in Implementation considerations col (index 8). Got: {col9_vals}"
        )

    def test_impl_considerations_NOT_from_fa_consequences(self) -> None:
        """Implementation considerations must NOT use fa-level consequences_impacts aggregation."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        # Item with no intervention_risks; fa has consequences_impacts
        item = dict(_item())  # no intervention_risks
        fa["proven_interventions"] = [item]
        fa["recommendations"] = []
        fa["consequences_impacts"] = [_con_item()]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col9_vals = [row[8] for row in ws.iter_rows(min_row=2, values_only=True)]
        # Col 9 (index 8) must be blank (or empty) — not filled from consequences_impacts
        assert all(not v for v in col9_vals), (
            f"Implementation considerations incorrectly filled from fa-level agg. Got: {col9_vals}"
        )

    def test_expected_impact_in_col10_when_present(self) -> None:
        """expected_impact → Expected impact col (index 9) when populated."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_rich_item()]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col10_vals = [row[9] for row in ws.iter_rows(min_row=2, values_only=True) if row[9]]
        assert any("Observed:" in str(v) for v in col10_vals), (
            f"expected_impact not in Expected impact col (index 9). Got: {col10_vals}"
        )

    def test_expected_impact_fallback_observed_prefix_for_proven(self) -> None:
        """Fallback: proven item without expected_impact gets 'Observed: ' prefix in col 10."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        item = dict(_item()) | {"evidence_type": "intervention_effect"}  # no expected_impact
        fa["proven_interventions"] = [item]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col10_vals = [row[9] for row in ws.iter_rows(min_row=2, values_only=True) if row[9]]
        assert any(str(v).startswith("Observed:") for v in col10_vals), (
            f"Fallback for proven should start with 'Observed:'. Got: {col10_vals}"
        )

    def test_expected_impact_fallback_intended_prefix_for_recommendation(self) -> None:
        """Fallback: recommendation_only item without expected_impact gets 'Intended to: ' prefix."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        item = dict(_rec_item())  # no expected_impact, evidence_type=recommendation_only
        fa["proven_interventions"] = []
        fa["recommendations"] = [item]
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col10_vals = [row[9] for row in ws.iter_rows(min_row=2, values_only=True) if row[9]]
        assert any(str(v).startswith("Intended to:") for v in col10_vals), (
            f"Fallback for recommendation should start with 'Intended to:'. Got: {col10_vals}"
        )

    def test_evidence_design_type_in_col7(self) -> None:
        """evidence_design_type → Evidence design/type col (index 6)."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_rich_item()]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col7_vals = [row[6] for row in ws.iter_rows(min_row=2, values_only=True) if row[6]]
        assert "quasi-experimental" in col7_vals, (
            f"evidence_design_type not in Evidence design/type col (index 6). Got: {col7_vals}"
        )

    def test_evidence_design_type_defaults_to_unknown(self) -> None:
        """When evidence_design_type is absent, col 7 (index 6) shows 'unknown'."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        item = dict(_item())  # no evidence_design_type
        fa["proven_interventions"] = [item]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col7_vals = [row[6] for row in ws.iter_rows(min_row=2, values_only=True)]
        assert any(v == "unknown" for v in col7_vals), (
            f"Missing evidence_design_type should default to 'unknown'. Got: {col7_vals}"
        )

    def test_target_cadre_setting_in_col8(self) -> None:
        """target_cadre_setting → Target cadre & setting col (index 7)."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        fa["proven_interventions"] = [_rich_item()]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col8_vals = [row[7] for row in ws.iter_rows(min_row=2, values_only=True) if row[7]]
        assert any("HEWs" in str(v) for v in col8_vals), (
            f"target_cadre_setting not in Target cadre & setting col (index 7). Got: {col8_vals}"
        )

    def test_target_cadre_setting_defaults_to_unspecified(self) -> None:
        """When target_cadre_setting is absent, col 8 (index 7) shows 'unspecified'."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        fa = payload["domains"][0]["focus_areas"][0]
        item = dict(_item())  # no target_cadre_setting
        fa["proven_interventions"] = [item]
        fa["recommendations"] = []
        wb = _render_to_wb(payload)
        ws = wb["MENU"]
        col8_vals = [row[7] for row in ws.iter_rows(min_row=2, values_only=True)]
        assert any(v == "unspecified" for v in col8_vals), (
            f"Missing target_cadre_setting should default to 'unspecified'. Got: {col8_vals}"
        )


class TestMergerNewFieldPreservation:
    """Merger preserves new optional fields across partials."""

    def _make_pi_partial(self, item: dict) -> dict:
        fa: dict = {
            "focus_area_id": "supervision_models",
            **{c: [] for c in (
                "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
                "operational_barriers", "governance_process_dependencies",
                "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
                "consequences_impacts",
            )},
        }
        fa["proven_interventions"] = [item]
        return {
            "job_id": "domain_lessons_option_b",
            "target_country": "Ethiopia",
            "generated_at": "2026-01-01",
            "domains": [{"domain_id": "accountability", "focus_areas": [fa]}],
        }

    def test_evidence_summary_carried_through_merge(self) -> None:
        from app.analyze.merger import merge_outputs
        item = dict(_rich_item()) | {"citations": [{**_citation("SRC1"), "locator": "p.1"}]}
        merged = merge_outputs("domain_lessons_option_b", [self._make_pi_partial(item)])
        result = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        assert result.get("evidence_summary"), "evidence_summary lost after merge"
        assert "23%" in result["evidence_summary"]

    def test_evidence_summary_filled_from_second_partial(self) -> None:
        """If first partial lacks evidence_summary, it is filled from second partial."""
        from app.analyze.merger import merge_outputs
        item_no_es = dict(_item("pi_001")) | {"citations": [{**_citation("SRC1"), "locator": "p.1"}]}
        item_with_es = dict(_item("pi_002")) | {
            "evidence_summary": "Checklists improved adherence by 15%.",
            "citations": [{**_citation("SRC2"), "locator": "p.2",
                           "source_title": "Source Two", "snippet": "Districts saw improvement."}],
        }
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_pi_partial(item_no_es), self._make_pi_partial(item_with_es)])
        result = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        assert result.get("evidence_summary") == "Checklists improved adherence by 15%.", (
            f"evidence_summary not filled from second partial. Got: {result.get('evidence_summary')}"
        )

    def test_intervention_risks_unioned_across_partials(self) -> None:
        """intervention_risks from two partials are unioned (up to 3)."""
        from app.analyze.merger import merge_outputs
        item_a = dict(_item("pi_001")) | {
            "intervention_risks": ["Risk A"],
            "citations": [{**_citation("SRC1"), "locator": "p.1"}],
        }
        item_b = dict(_item("pi_002")) | {
            "intervention_risks": ["Risk B"],
            "citations": [{**_citation("SRC2"), "locator": "p.2",
                           "source_title": "Source Two", "snippet": "Districts saw improvement."}],
        }
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_pi_partial(item_a), self._make_pi_partial(item_b)])
        result = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        risks = result.get("intervention_risks") or []
        assert "Risk A" in risks and "Risk B" in risks, (
            f"intervention_risks not unioned. Got: {risks}"
        )

    def test_intervention_risks_capped_at_3(self) -> None:
        """intervention_risks never exceeds 3 bullets after merge."""
        from app.analyze.merger import merge_outputs
        item_a = dict(_item("pi_001")) | {
            "intervention_risks": ["R1", "R2"],
            "citations": [{**_citation("SRC1"), "locator": "p.1"}],
        }
        item_b = dict(_item("pi_002")) | {
            "intervention_risks": ["R3", "R4"],
            "citations": [{**_citation("SRC2"), "locator": "p.2",
                           "source_title": "Source Two", "snippet": "Districts saw improvement."}],
        }
        merged = merge_outputs("domain_lessons_option_b",
                               [self._make_pi_partial(item_a), self._make_pi_partial(item_b)])
        result = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        risks = result.get("intervention_risks") or []
        assert len(risks) <= 3, f"intervention_risks exceeded cap of 3. Got: {risks}"

    def test_governance_operating_model_carried_through_merge(self) -> None:
        from app.analyze.merger import merge_outputs
        gov_text = "Owner: DHO\nActors: Supervisors\nData: Checklist\nCadence: Monthly"
        item = dict(_item()) | {
            "governance_operating_model": gov_text,
            "citations": [{**_citation("SRC1"), "locator": "p.1"}],
        }
        merged = merge_outputs("domain_lessons_option_b", [self._make_pi_partial(item)])
        result = merged["domains"][0]["focus_areas"][0]["proven_interventions"][0]
        assert result.get("governance_operating_model") == gov_text, (
            f"governance_operating_model lost after merge. Got: {result.get('governance_operating_model')}"
        )


# ---------------------------------------------------------------------------
# D4 — Snippet truncation: _clean_citations applied before validate_output
# ---------------------------------------------------------------------------

class TestSnippetTruncationBeforeValidation:
    """_clean_citations truncates snippets >300 chars before schema validation."""

    def test_long_snippet_truncated_by_clean_citations(self) -> None:
        """Snippet >300 chars in a payload is truncated to ≤300 after _clean_citations."""
        from app.app import _clean_citations
        long_snippet = "A " * 200  # 400 chars
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"] = long_snippet
        result = _clean_citations(payload)
        snippet = result["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"]
        assert len(snippet) <= 300, f"Snippet not truncated: {len(snippet)} chars"

    def test_clean_citations_allows_subsequent_validate_to_pass(self) -> None:
        """A payload with snippet >300 chars fails validation but passes after _clean_citations."""
        from app.app import _clean_citations
        long_snippet = "Evidence shows improvement. " * 15  # >300 chars
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"] = long_snippet
        # Raw payload must fail schema validation (maxLength: 300)
        with pytest.raises(Exception):
            validate_output(payload, SCHEMA)
        # After _clean_citations, it must pass
        cleaned = _clean_citations(payload)
        validate_output(cleaned, SCHEMA)  # must not raise

    def test_short_snippet_unchanged_by_clean_citations(self) -> None:
        """Snippets ≤300 chars are not modified by _clean_citations."""
        from app.app import _clean_citations
        snippet = "Short evidence snippet."
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"] = snippet
        result = _clean_citations(payload)
        result_snippet = result["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"]
        assert result_snippet == snippet


# ---------------------------------------------------------------------------
# D7 — Expanded barrier keywords: lacking, without, absence of, insufficient
# ---------------------------------------------------------------------------

class TestExpandedBarrierKeywords:
    """New barrier framing keywords accepted in operational_barriers snippets."""

    def _make_barrier_payload(self, snippet: str) -> dict:
        payload = copy.deepcopy(VALID_PAYLOAD)
        item = {
            "item_id": "bar_001",
            "title": "Barrier Item",
            "statement": "This is a barrier.",
            "evidence_type": "determinant_mechanism",
            "evidence_strength": "moderate",
            "citations": [{
                "doc_id": "SRC1",
                "source_title": "Vallieres et al. BMC Health Services Research 2018",
                "locator": "p.1",
                "snippet": snippet,
            }],
        }
        payload["domains"][0]["focus_areas"][0]["operational_barriers"] = [item]
        return payload

    def test_lacking_keyword_accepted(self) -> None:
        """Snippet with 'lacking' passes barrier framing validation."""
        payload = self._make_barrier_payload("Lacking sufficient supervisors, attendance monitoring failed.")
        validate_output(payload, SCHEMA)  # must not raise

    def test_without_keyword_accepted(self) -> None:
        """Snippet with 'without' passes barrier framing validation."""
        payload = self._make_barrier_payload("Without reliable IT infrastructure, reporting was impossible.")
        validate_output(payload, SCHEMA)

    def test_absence_of_keyword_accepted(self) -> None:
        """Snippet with 'absence of' passes barrier framing validation."""
        payload = self._make_barrier_payload("The absence of reliable transport limited supervisory visits.")
        validate_output(payload, SCHEMA)

    def test_insufficient_keyword_accepted(self) -> None:
        """Snippet with 'insufficient' passes barrier framing validation."""
        payload = self._make_barrier_payload("Insufficient funding prevented scale-up of the programme.")
        validate_output(payload, SCHEMA)


# ---------------------------------------------------------------------------
# CITATIONS sheet: 5 columns + snippet ≤300 enforcement
# ---------------------------------------------------------------------------

class TestCitationsSheetLeanStructure:
    """CITATIONS sheet has 5 columns and enforces snippet ≤300."""

    def test_citations_snippet_truncated_at_300_in_citations_sheet(self) -> None:
        """Snippets >300 chars in source items are truncated in the CITATIONS sheet."""
        payload = copy.deepcopy(VALID_PAYLOAD)
        long_snip = "Evidence text. " * 25  # >300 chars
        payload["domains"][0]["focus_areas"][0]["proven_interventions"][0]["citations"][0]["snippet"] = long_snip
        wb = _render_to_wb(payload)
        ws2 = wb["CITATIONS"]
        snippets = [row[4] for row in ws2.iter_rows(min_row=2, values_only=True) if row[4]]
        for snip in snippets:
            assert len(str(snip)) <= 300, f"CITATIONS sheet snippet exceeds 300 chars: {len(str(snip))}"

    def test_citations_iid_matches_menu_iid(self) -> None:
        """Intervention IDs in CITATIONS exactly match those in MENU (5-col linkage)."""
        wb = _render_to_wb(copy.deepcopy(VALID_PAYLOAD))
        menu_ids = {row[0] for row in wb["MENU"].iter_rows(min_row=2, values_only=True) if row[0]}
        cit_ids = {row[0] for row in wb["CITATIONS"].iter_rows(min_row=2, values_only=True) if row[0]}
        assert cit_ids.issubset(menu_ids), f"CITATIONS IIDs not a subset of MENU IIDs: {cit_ids - menu_ids}"
