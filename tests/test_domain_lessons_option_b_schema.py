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
    """Barrier item whose snippet only describes a cause, no barrier keywords — must fail."""
    return {
        "item_id": item_id,
        "title": "Low Supervision Rates",
        "statement": "Insufficient supervision rates were associated with higher absenteeism.",
        "evidence_type": "determinant_mechanism",
        "evidence_strength": "moderate",
        "citations": [{
            "doc_id": "SRC1",
            "source_title": "Vallieres et al. BMC Health Services Research 2018",
            "locator": "p.2",
            "snippet": "causes included insufficient supervision (56%) and low pay (44%).",
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
    """All nine category arrays are required in a focus area."""
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
