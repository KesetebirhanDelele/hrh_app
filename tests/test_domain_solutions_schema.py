"""Schema validation tests for domain_solutions_from_evidence."""
import copy

import pytest

from app.core.validators import SchemaValidationError, validate_output

SCHEMA = "schemas/domain_solutions_from_evidence.schema.json"

# Minimal valid payload — one solution in one focus area of one domain.
VALID_PAYLOAD = {
    "job_id": "domain_solutions_from_evidence",
    "target_country": "Ethiopia",
    "generated_at": "2026-02-28",
    "domains": [
        {
            "domain_id": "accountability",
            "focus_areas": [
                {
                    "focus_area_id": "supervision_models",
                    "solutions": [
                        {
                            "solution_id": "accountability_supervision_models_1",
                            "title": "Structured Supervisory Checklists",
                            "description": "Supervisors use standardised checklists during monthly visits to health posts.",
                            "mechanism": "Checklists standardise clinical expectations, which increases protocol adherence.",
                            "implementation_conditions": [
                                "Trained supervisors with protected travel budget",
                                "Monthly visit schedule enforced by district office",
                            ],
                            "evidence_strength": "moderate",
                            "citations": [
                                {
                                    "doc_id": "SRC1",
                                    "locator": "Section 3.2, p. 45",
                                    "snippet": "Districts using structured checklists saw a 23% improvement in protocol adherence among HEWs.",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ],
}


def test_valid_payload_passes() -> None:
    validate_output(VALID_PAYLOAD, SCHEMA)


def test_missing_generated_at_fails() -> None:
    bad = {k: v for k, v in VALID_PAYLOAD.items() if k != "generated_at"}
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(bad, SCHEMA)
    assert "generated_at" in str(exc_info.value)


def test_solution_without_citations_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["solutions"][0]["citations"] = []
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


def test_invalid_evidence_strength_fails() -> None:
    # Schema uses strong|moderate|weak; "high" is the old enum from common.json
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["solutions"][0]["evidence_strength"] = "high"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_snippet_over_300_chars_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["solutions"][0]["citations"][0]["snippet"] = "x" * 301
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_empty_solutions_array_is_valid() -> None:
    """A focus area with no evidence found must pass with an empty solutions list."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["solutions"] = []
    validate_output(payload, SCHEMA)


def test_additional_property_on_solution_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["solutions"][0]["extra_field"] = "not allowed"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)


def test_additional_property_on_citation_fails() -> None:
    bad = copy.deepcopy(VALID_PAYLOAD)
    bad["domains"][0]["focus_areas"][0]["solutions"][0]["citations"][0]["source_url"] = "https://example.org"
    with pytest.raises(SchemaValidationError):
        validate_output(bad, SCHEMA)
