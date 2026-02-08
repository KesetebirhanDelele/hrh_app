from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from app.analyze.extractors import extract_table3_items
from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job
from app.utils import auto_output_name


def run_table3_stub(spec_id: str) -> Path:
    job = get_job("table3_intervention_framework")
    spec: Dict[str, Any] = _read_json(job.spec_file)
    items = extract_table3_items(spec)

    payload = {
        "job_id": "table3_intervention_framework",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "interventions": []
    }

    for it in items:
        payload["interventions"].append(
            {
                "intervention_id": it.intervention_id,
                "lever": it.lever,
                "intervention": it.intervention,
                "mechanism": it.mechanism,
                "evidence": {
                    "quality": "none",
                    "rationale": "Stub run: no sources were provided or searched.",
                    "citations": []
                },
                "implementation_notes": "",
                "dependencies": [],
                "risks": []
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
    p = run_table3_stub(spec_id="table3_integrated_intervention_framework_v1")
    print(f"Wrote: {p}")
