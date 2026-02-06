from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.analyze.extractors import (
    extract_phase1_questions,
    extract_rrr_solutions,
    extract_table2_items,
    extract_table3_items,
    extract_learning_domains,
    extract_benchmark_dimensions_countries,
)


@dataclass(frozen=True)
class Phase1Question:
    question_id: str
    question: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    """
    Read JSON with a UTF-8-first strategy; fall back to cp1252 if needed.
    This avoids mojibake like â€™ when files were saved in a Windows encoding.
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return json.loads(text)


def render_phase1_prompt(
    template_path: str,
    spec_path: str,
    spec_id: str,
    country_name: str,
    country_iso3: Optional[str] = None,
) -> str:
    """
    Renders a single prompt by appending an Inputs block containing the fields
    the template expects. (We keep the template itself unchanged.)
    """
    template = _read_text(Path(template_path))
    spec = _read_json(Path(spec_path))
    questions = extract_phase1_questions(spec)

    inputs = {
        "country_name": country_name,
        "country_iso3": country_iso3,
        "spec_id": spec_id,
        "questions": [{"question_id": q.question_id, "question": q.question} for q in questions],
    }

    return template.rstrip() + "\n\n## RENDERED INPUTS (machine-generated)\n" + json.dumps(inputs, ensure_ascii=False, indent=2) + "\n"


def render_prompt_for_job(
    job_id: str,
    template_path: str,
    spec_path: str,
    spec_id: str,
    country_name: Optional[str] = None,
    country_iso3: Optional[str] = None,
    sources_path: Optional[str] = None,
) -> str:
    template = _read_text(Path(template_path))
    spec = _read_json(Path(spec_path))

    inputs: Dict[str, Any] = {"spec_id": spec_id}

    # Load curated sources if provided
    if sources_path:
        sources_data = _read_json(Path(sources_path))
        inputs["allowed_sources"] = sources_data.get("sources", [])

    if job_id == "phase1_discovery_qa":
        if not country_name:
            raise ValueError("country_name is required for phase1_discovery_qa")
        questions = extract_phase1_questions(spec)
        inputs.update(
            {
                "country_name": country_name,
                "country_iso3": country_iso3,
                "questions": [{"question_id": q.question_id, "question": q.question} for q in questions],
            }
        )

    elif job_id == "rrr_evidence_matrix":
        sols = extract_rrr_solutions(spec)
        inputs["solutions"] = [
            {"solution_id": s.solution_id, "solution": s.solution, "mechanism": s.mechanism} for s in sols
        ]

    elif job_id == "table2_root_cause_mapping":
        items = extract_table2_items(spec)
        inputs["framework_items"] = [
            {
                "item_id": it.item_id,
                "category": it.category,
                "root_cause": it.root_cause,
                "definition": it.definition,
            }
            for it in items
        ]

    elif job_id == "table3_intervention_framework":
        items = extract_table3_items(spec)
        inputs["interventions"] = [
            {
                "intervention_id": it.intervention_id,
                "lever": it.lever,
                "intervention": it.intervention,
                "mechanism": it.mechanism,
            }
            for it in items
        ]

    elif job_id == "benchmark_country_scoring":
        dims, countries = extract_benchmark_dimensions_countries(spec)
        inputs["dimensions"] = [{"dimension_id": d.dimension_id, "label": d.label} for d in dims]
        inputs["countries"] = [{"country_name": c.country_name, "iso3": c.iso3} for c in countries]

    elif job_id == "country_learning_briefs":
        if not country_name:
            raise ValueError("country_name is required for country_learning_briefs")
        domains = extract_learning_domains(spec)
        inputs.update(
            {
                "country_name": country_name,
                "country_iso3": country_iso3,
                "learning_domains": [{"domain_id": d.domain_id, "domain": d.domain} for d in domains],
            }
        )

    else:
        raise KeyError(f"render_prompt_for_job: unsupported job_id '{job_id}'")

    # Build final prompt
    final_prompt = template.rstrip() + "\n\n## RENDERED INPUTS (machine-generated)\n" + json.dumps(inputs, ensure_ascii=False, indent=2) + "\n"

    # Add source_id enforcement instruction if allowed_sources provided
    if sources_path and inputs.get("allowed_sources"):
        final_prompt += "\n## IMPORTANT: Source ID Enforcement\n"
        final_prompt += "When citing from the allowed_sources above, you MUST include the source_id field in each citation.\n"
        final_prompt += "The source_id must match one of the source_id values from allowed_sources (e.g., SRC1, SRC2, etc.).\n"
        final_prompt += "This enables validation that citations reference only the curated sources provided.\n"

    return final_prompt
