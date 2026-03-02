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

    def fake_generate_json(prompt: str, provider=None, model=None, repair_instructions=None, job_id=None):
        return llm_mod.LLMResponse(text=json.dumps(payload))

    monkeypatch.setattr(llm_mod, "generate_json", fake_generate_json)

    exit_code = app_mod.main([
        "run",
        "--job", "rrr_evidence_matrix",
        "--mode", "llm",
        "--spec-id", "rrr_solutions_resource_constrained_v1"
    ])

    assert exit_code == 0

    # Find the most recent timestamped folder
    job_output_dir = Path("outputs/rrr_evidence_matrix")
    matching_files = []
    for folder in job_output_dir.iterdir():
        if folder.is_dir():
            json_file = folder / "output_llm.json"
            if json_file.exists():
                matching_files.append(json_file)

    assert len(matching_files) > 0, "No output_llm.json found in timestamped folders"

    # Get the most recent file
    matching_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out_path = matching_files[0]

    assert out_path.exists()

    # Clean up the entire timestamped folder
    import shutil
    shutil.rmtree(out_path.parent, ignore_errors=True)
