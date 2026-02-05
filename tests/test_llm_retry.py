from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_llm_retry_repairs_schema_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Forces first LLM attempt to fail schema validation (missing generated_at),
    then returns a valid payload on the second attempt.
    """
    # Import here so monkeypatching targets are available
    import app.analyze.llm as llm_mod
    import app.app as app_mod

    calls = {"n": 0}

    bad_payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        # generated_at intentionally missing -> should fail schema
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "P1_Q1",
                "question": "Stub question",
                "answer": "Stub answer",
                "evidence": {"quality": "none", "rationale": "no sources", "citations": []},
                "tags": []
            }
        ]
    }

    good_payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        "generated_at": "2026-02-04",
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "P1_Q1",
                "question": "Stub question",
                "answer": "Stub answer",
                "evidence": {"quality": "none", "rationale": "no sources", "citations": []},
                "tags": []
            }
        ]
    }

    def fake_generate_json(prompt: str, provider=None, model=None, repair_instructions=None):
        calls["n"] += 1
        text = json.dumps(bad_payload if calls["n"] == 1 else good_payload)
        return llm_mod.LLMResponse(text=text)

    # Patch the LLM call so we never hit the network
    monkeypatch.setattr(llm_mod, "generate_json", fake_generate_json)

    # Run the CLI entrypoint programmatically
    exit_code = app_mod.main([
        "run",
        "--job", "phase1_discovery_qa",
        "--mode", "llm",
        "--spec-id", "phase1_discovery_questions_ethiopia_v1",
        "--country-name", "Ethiopia",
        "--country-iso3", "ETH"
    ])

    assert exit_code == 0
    assert calls["n"] == 2  # proves retry happened

    out_path = Path("outputs/phase1_discovery_qa/output_llm.json")
    assert out_path.exists()

    # Optional cleanup (keep repo tidy)
    # Comment out if you prefer to keep artifacts for debugging.
    out_path.unlink(missing_ok=True)
