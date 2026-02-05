from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict

from app.analyze.extractors import extract_phase1_questions
from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job


def run_phase1_stub(spec_id: str, country_name: str, country_iso3: str | None = None) -> Path:
    job = get_job("phase1_discovery_qa")

    spec: Dict[str, Any] = _read_json(job.spec_file)
    questions = extract_phase1_questions(spec)

    out = {
        "job_id": "phase1_discovery_qa",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "country": {"name": country_name, **({"iso3": country_iso3} if country_iso3 else {})},
        "questions": []
    }

    for q in questions:
        out["questions"].append(
            {
                "question_id": q.question_id,
                "question": q.question,
                "answer": "TBD (stub).",
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
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Validate immediately (deterministic gate)
    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(out, schema_rel)

    return out_path


if __name__ == "__main__":
    p = run_phase1_stub(
        spec_id="phase1_discovery_questions_ethiopia_v1",
        country_name="Ethiopia",
        country_iso3="ETH",
    )
    print(f"Wrote: {p}")
