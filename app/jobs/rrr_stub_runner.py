from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from app.analyze.extractors import extract_rrr_solutions
from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job
from app.utils import auto_output_name


def run_rrr_stub(spec_id: str) -> Path:
    job = get_job("rrr_evidence_matrix")
    spec: Dict[str, Any] = _read_json(job.spec_file)
    sols = extract_rrr_solutions(spec)

    payload = {
        "job_id": "rrr_evidence_matrix",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "solutions": []
    }

    for s in sols:
        payload["solutions"].append(
            {
                "solution_id": s.solution_id,
                "solution": s.solution,
                "mechanism": s.mechanism,
                "evidence": {
                    "quality": "none",
                    "rationale": "Stub run: no sources were provided or searched.",
                    "citations": []
                },
                "feasibility_resource_constrained": "unknown",
                "risks": [],
                "implementation_notes": ""
            }
        )

    job.output_dir.mkdir(parents=True, exist_ok=True)
    out_filename = auto_output_name(job.output_dir, "json", mode="stub")
    out_path = Path(out_filename)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
    return out_path


if __name__ == "__main__":
    p = run_rrr_stub(spec_id="rrr_solutions_resource_constrained_v1")
    print(f"Wrote: {p}")
