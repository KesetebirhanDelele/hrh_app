from __future__ import annotations

import pytest

from app.core.validators import SchemaValidationError, validate_output


def test_phase1_schema_valid_payload_passes() -> None:
    payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        "generated_at": "2026-02-04",
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "q1",
                "question": "What are the key HRH challenges?",
                "answer": "Evidence suggests shortages, maldistribution, and training bottlenecks in some regions.",
                "evidence": {
                    "quality": "low",
                    "rationale": "Example payload for schema test; citations included as placeholders.",
                    "citations": [
                        {
                            "source_title": "World Health Statistics 2024",
                            "source_url": "https://example.org/whs-2024",
                            "published_date": "2024-01-01",
                            "locator": "Chapter 3, p. 45",
                            "quote": "Illustrative excerpt."
                        }
                    ]
                },
                "tags": ["workforce", "distribution"]
            }
        ],
        "notes": "This file tests schema validation only."
    }

    # Should not raise
    validate_output(payload, "schemas/phase1_discovery_qa.schema.json")


def test_phase1_schema_invalid_payload_fails() -> None:
    bad_payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        # generated_at missing on purpose
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "q1",
                "question": "What are the key HRH challenges?",
                "answer": "Unknown",
                "evidence": {
                    "quality": "none",
                    "rationale": "No evidence found."
                    # citations must be empty array if present; also ok omitted, but missing generated_at should fail anyway
                }
            }
        ]
    }

    with pytest.raises(SchemaValidationError) as e:
        validate_output(bad_payload, "schemas/phase1_discovery_qa.schema.json")

    # Helpful assertion: should mention the missing field
    assert "generated_at" in str(e.value)
