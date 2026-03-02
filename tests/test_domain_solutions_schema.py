"""Schema validation tests for domain_solutions_from_evidence."""
import copy
from datetime import date

import pytest

from app.core.validators import SchemaValidationError, validate_output
from app.app import _stamp_run_date, _validate_snippet_verbatim

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


# ── Citation cap validator tests ────────────────────────────────────────────

def _make_cit(doc_id: str, locator: str, snippet: str = "A short verbatim excerpt.") -> dict:
    return {"doc_id": doc_id, "locator": locator, "snippet": snippet}


def _payload_with_cits(evidence_strength: str, citations: list) -> dict:
    """Build a minimal valid payload whose single solution has the given citations."""
    import copy
    p = copy.deepcopy(VALID_PAYLOAD)
    sol = p["domains"][0]["focus_areas"][0]["solutions"][0]
    sol["evidence_strength"] = evidence_strength
    sol["citations"] = citations
    return p


def test_validator_passes_strong_with_3_same_doc() -> None:
    """strong solution: 3 citations from the same doc_id is within policy."""
    cits = [_make_cit("SRC1", f"p.{i}") for i in range(1, 4)]
    validate_output(_payload_with_cits("strong", cits), SCHEMA)


def test_validator_fails_strong_with_4_same_doc() -> None:
    """strong solution: 4 citations from the same doc_id exceeds both per-doc (3) and overall (3) caps."""
    cits = [_make_cit("SRC1", f"p.{i}") for i in range(1, 5)]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(_payload_with_cits("strong", cits), SCHEMA)
    msg = str(exc_info.value)
    assert "SRC1" in msg


def test_validator_passes_weak_with_1_same_doc() -> None:
    """weak solution: 1 citation from a doc_id is within policy."""
    validate_output(_payload_with_cits("weak", [_make_cit("SRC1", "p.1")]), SCHEMA)


def test_validator_fails_weak_with_2_same_doc() -> None:
    """weak solution: 2 citations from the same doc_id exceeds per-doc cap (1)."""
    cits = [_make_cit("SRC1", "p.1"), _make_cit("SRC1", "p.2")]
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_output(_payload_with_cits("weak", cits), SCHEMA)
    msg = str(exc_info.value)
    assert "SRC1" in msg
    assert "weak" in msg


# ── generated_at stamping tests ────────────────────────────────────────────

def test_stamp_run_date_overwrites_wrong_date() -> None:
    """_stamp_run_date replaces a hallucinated LLM date with today's date."""
    payload = {"generated_at": "2023-10-15"}
    _stamp_run_date("domain_solutions_from_evidence", payload)
    assert payload["generated_at"] == date.today().isoformat()


def test_stamp_run_date_does_not_affect_other_jobs() -> None:
    """_stamp_run_date is a no-op for all other job IDs."""
    payload = {"generated_at": "2023-10-15"}
    _stamp_run_date("rrr_evidence_matrix", payload)
    assert payload["generated_at"] == "2023-10-15"


def test_stamped_payload_passes_schema() -> None:
    """After stamping, the payload must still pass full schema validation."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["generated_at"] = "2023-10-15"  # wrong date injected by LLM
    _stamp_run_date("domain_solutions_from_evidence", payload)
    assert payload["generated_at"] == date.today().isoformat()
    validate_output(payload, SCHEMA)


# ── Verbatim snippet validator tests ────────────────────────────────────────

# A tiny sources fixture whose single excerpt matches VALID_PAYLOAD's citation.
_SOURCES_FIXTURE = [
    {
        "source_id": "SRC1",
        "source_title": "Test Source",
        "snippets": [
            {
                "locator": "Section 3.2, p. 45",
                "text": "Districts using structured checklists saw a 23% improvement in protocol adherence among HEWs.",
                "type": "text",
            }
        ],
    }
]


def test_verbatim_snippet_passes() -> None:
    """Exact substring of source text passes the verbatim check."""
    _validate_snippet_verbatim(copy.deepcopy(VALID_PAYLOAD), _SOURCES_FIXTURE)


def test_verbatim_snippet_fails_garbled() -> None:
    """A paraphrased (non-verbatim) snippet raises SchemaValidationError."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["solutions"][0]["citations"][0]["snippet"] = (
        "Districts using checklists saw improvements in adherence."  # paraphrased
    )
    with pytest.raises(SchemaValidationError) as exc_info:
        _validate_snippet_verbatim(payload, _SOURCES_FIXTURE)
    msg = str(exc_info.value)
    assert "SRC1" in msg
    assert "verbatim" in msg.lower()


def test_verbatim_snippet_fails_unknown_doc_id() -> None:
    """A doc_id absent from loaded sources raises SchemaValidationError."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["solutions"][0]["citations"][0]["doc_id"] = "SRC99"
    with pytest.raises(SchemaValidationError) as exc_info:
        _validate_snippet_verbatim(payload, _SOURCES_FIXTURE)
    assert "SRC99" in str(exc_info.value)


def test_verbatim_snippet_fails_unknown_locator() -> None:
    """A locator absent from the source's excerpts raises SchemaValidationError."""
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["domains"][0]["focus_areas"][0]["solutions"][0]["citations"][0]["locator"] = "p. 999"
    with pytest.raises(SchemaValidationError) as exc_info:
        _validate_snippet_verbatim(payload, _SOURCES_FIXTURE)
    assert "p. 999" in str(exc_info.value)
