from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.analyze.prompting import _read_json
from app.core.validators import validate_output
from app.jobs.registry import get_job


def _extract_dimensions_and_countries(spec: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Best-effort extraction for benchmark scoring spec:
    - dimensions: list of {dimension_id, label}
    - countries: list of {country_name, iso3}
    """
    dims: List[Dict[str, str]] = []
    ctries: List[Dict[str, str]] = []

    # Try explicit dimensions first
    for key in ("dimensions", "scoring_dimensions", "criteria"):
        v = spec.get(key)
        if isinstance(v, list):
            for i, d in enumerate(v, start=1):
                if isinstance(d, dict):
                    did = str(d.get("dimension_id") or d.get("id") or f"d{i}").strip()
                    lab = str(d.get("label") or d.get("name") or d.get("title") or "").strip()
                    if did and lab:
                        dims.append({"dimension_id": did, "label": lab})
            break

    # If not found, check for nested phase structure (criteria within phases)
    if not dims:
        for key, value in spec.items():
            if isinstance(value, dict) and "criteria" in value:
                criteria_list = value.get("criteria")
                if isinstance(criteria_list, list):
                    for crit in criteria_list:
                        if isinstance(crit, dict):
                            cid = str(crit.get("criterion_id") or crit.get("id") or "").strip()
                            cname = str(crit.get("name") or crit.get("label") or "").strip()
                            if cid and cname:
                                dims.append({"dimension_id": cid, "label": cname})

    # Try to extract countries
    for key in ("countries", "benchmark_countries", "candidates"):
        v = spec.get(key)
        if isinstance(v, list):
            for c in v:
                if isinstance(c, dict):
                    name = str(c.get("country_name") or c.get("name") or "").strip()
                    iso3 = str(c.get("iso3") or c.get("ISO3") or "").strip().upper()
                    if name and iso3:
                        ctries.append({"country_name": name, "iso3": iso3})
            break

    if not dims:
        # fallback: at least one placeholder dimension
        dims = [{"dimension_id": "d1", "label": "placeholder_dimension"}]
    if not ctries:
        # fallback: at least one placeholder country
        ctries = [{"country_name": "placeholder_country", "iso3": "XXX"}]

    return dims, ctries


def run_benchmark_stub(spec_id: str) -> Path:
    job = get_job("benchmark_country_scoring")
    spec: Dict[str, Any] = _read_json(job.spec_file)
    dims, ctries = _extract_dimensions_and_countries(spec)

    def no_evidence(msg: str) -> dict:
        return {"quality": "none", "rationale": msg, "citations": []}

    payload = {
        "job_id": "benchmark_country_scoring",
        "spec_id": spec_id,
        "generated_at": date.today().isoformat(),
        "countries": []
    }

    for c in ctries:
        dim_scores = []
        for d in dims:
            dim_scores.append(
                {
                    "dimension_id": d["dimension_id"],
                    "label": d["label"],
                    "score_note": {"score": 0, "evidence": no_evidence("Stub run: no sources were provided or searched.")}
                }
            )

        payload["countries"].append(
            {
                "country_name": c["country_name"],
                "iso3": c["iso3"],
                "overall_score": {"score": 0, "evidence": no_evidence("Stub run: no sources were provided or searched.")},
                "dimensions": dim_scores
            }
        )

    job.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = job.output_dir / "output_stub.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
    return out_path


if __name__ == "__main__":
    p = run_benchmark_stub(spec_id="benchmark_country_filters_and_scoring_v1")
    print(f"Wrote: {p}")
