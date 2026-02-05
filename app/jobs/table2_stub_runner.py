from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from app.analyze.extractors import extract_table2_items
from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job


def run_table2_stub(spec_id: str) -> Path:
    job = get_job("table2_root_cause_mapping")
    spec: Dict[str, Any] = _read_json(job.spec_file)
    items = extract_table2_items(spec)

    payload = {
        "job_id": "table2_root_cause_mapping",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "framework_items": []
    }

    for it in items:
        payload["framework_items"].append(
            {
                "item_id": it.item_id,
                "category": it.category,
                "root_cause": it.root_cause,
                "definition": it.definition,
                "evidence": {
                    "quality": "none",
                    "rationale": "Stub run: no sources were provided or searched.",
                    "citations": []
                },
                "tags": []
            }
        )

    job.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = job.output_dir / "output_stub.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
    return out_path


if __name__ == "__main__":
    p = run_table2_stub(spec_id="table2_root_cause_framework_v1")
    print(f"Wrote: {p}")
