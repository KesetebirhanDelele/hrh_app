from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from app.analyze.extractors import extract_learning_domains
from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job
from app.utils import auto_output_name


def run_briefs_stub(spec_id: str, country_name: str, country_iso3: str | None = None) -> Path:
    job = get_job("country_learning_briefs")
    spec: Dict[str, Any] = _read_json(job.spec_file)
    domains = extract_learning_domains(spec)

    payload = {
        "job_id": "country_learning_briefs",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "country": {"name": country_name, **({"iso3": country_iso3} if country_iso3 else {})},
        "domains": []
    }

    for d in domains:
        payload["domains"].append(
            {
                "domain_id": d.domain_id,
                "domain": d.domain,
                "summary": "TBD (stub).",
                "key_questions": ["TBD (stub)."],
                "evidence": {
                    "quality": "none",
                    "rationale": "Stub run: no sources were provided or searched.",
                    "citations": []
                }
            }
        )

    job.output_dir.mkdir(parents=True, exist_ok=True)
    out_filename = auto_output_name(
        job.output_dir,
        "json",
        mode="stub",
        country_name=country_name,
        country_iso3=country_iso3,
    )
    out_path = Path(out_filename)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
    return out_path


if __name__ == "__main__":
    p = run_briefs_stub(spec_id="key_hrh_learning_domains_v1", country_name="Ethiopia", country_iso3="ETH")
    print(f"Wrote: {p}")
