from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_llm_generalized_rrr_uses_schema_and_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.analyze.llm as llm_mod
    import app.app as app_mod

    # Minimal valid RRR payload (single solution row)
    payload = {
        "job_id": "rrr_evidence_matrix",
        "spec_id": "rrr_solutions_resource_constrained_v1",
        "generated_at": "2026-02-04",
        "solutions": [
            {
                "solution_id": "S1",
                "solution": "Example solution",
                "mechanism": "Example mechanism",
                "evidence": {"quality": "none", "rationale": "unit test", "citations": []},
                "feasibility_resource_constrained": "unknown",
                "risks": [],
                "implementation_notes": ""
            }
        ]
    }

    def fake_generate_json(prompt: str, provider=None, model=None, repair_instructions=None):
        return llm_mod.LLMResponse(text=json.dumps(payload))

    monkeypatch.setattr(llm_mod, "generate_json", fake_generate_json)

    exit_code = app_mod.main([
        "run",
        "--job", "rrr_evidence_matrix",
        "--mode", "llm",
        "--spec-id", "rrr_solutions_resource_constrained_v1"
    ])

    assert exit_code == 0

    out_path = Path("outputs/rrr_evidence_matrix/output_llm.json")
    assert out_path.exists()
    out_path.unlink(missing_ok=True)
