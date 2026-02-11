from __future__ import annotations

import json
import os
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
from app.ingest.indexer import retrieve, group_by_source, load_index


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


def _trim_sources(
    sources: List[Dict[str, Any]], max_chars: int
) -> List[Dict[str, Any]]:
    """Return a copy of *sources* with snippets trimmed to fit a character budget.

    Distributes the budget evenly across sources, then fills remaining budget
    with leftovers. Tables are prioritised over plain text within each source.
    Sources always keep their metadata even if all snippets are dropped.
    """
    if max_chars <= 0:
        return [{**s, "snippets": []} for s in sources]

    total_chars = sum(
        len(snip.get("text", "")) for s in sources for snip in s.get("snippets", [])
    )
    if total_chars <= max_chars:
        return sources  # everything fits

    # Fair-share budget per source
    n_sources = len(sources) or 1
    per_source = max_chars // n_sources
    trimmed: list[Dict[str, Any]] = []
    remaining_budget = max_chars

    for src in sources:
        snips = src.get("snippets", [])
        # Prioritise tables, then text
        sorted_snips = sorted(snips, key=lambda s: 0 if s.get("type") == "table" else 1)
        kept: list[dict] = []
        used = 0
        budget = min(per_source, remaining_budget)
        for snip in sorted_snips:
            size = len(snip.get("text", ""))
            if used + size <= budget:
                kept.append(snip)
                used += size
        remaining_budget -= used
        trimmed.append({**src, "snippets": kept})

    return trimmed


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

    # Load curated sources if provided, trimming snippets to fit token budget
    if sources_path:
        sources_data = _read_json(Path(sources_path))
        max_snippet_chars = int(os.getenv("HRH_MAX_SNIPPET_CHARS", str(80_000)))
        inputs["allowed_sources"] = _trim_sources(
            sources_data.get("sources", []), max_snippet_chars
        )

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


def render_prompt_with_rag(
    job_id: str,
    template_path: str,
    spec_path: str,
    spec_id: str,
    query_text: str,
    index_data: Dict[str, Any],
    top_k: int = 20,
    country_name: Optional[str] = None,
    country_iso3: Optional[str] = None,
    item_inputs: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a prompt for a single question/item using RAG retrieval.

    Instead of stuffing all sources, retrieves only the top-K most relevant
    snippets for the given query_text, then builds a focused prompt.

    Args:
        job_id: The analysis job type.
        template_path: Path to the prompt template.
        spec_path: Path to the spec JSON.
        spec_id: Spec identifier.
        query_text: The question or item text to retrieve snippets for.
        index_data: Loaded embedding index (from load_index).
        top_k: Number of snippets to retrieve.
        country_name: Country name (for country-specific jobs).
        country_iso3: ISO3 code.
        item_inputs: Pre-built inputs dict for the specific item (e.g. single question).

    Returns:
        The rendered prompt string with retrieved sources.
    """
    template = _read_text(Path(template_path))

    # Retrieve relevant snippets
    retrieved = retrieve(index_data, query_text, top_k=top_k)
    allowed_sources = group_by_source(retrieved)

    # Build inputs
    inputs: Dict[str, Any] = {"spec_id": spec_id}
    inputs["allowed_sources"] = allowed_sources

    if item_inputs:
        inputs.update(item_inputs)

    # Build final prompt
    final_prompt = (
        template.rstrip()
        + "\n\n## RENDERED INPUTS (machine-generated)\n"
        + json.dumps(inputs, ensure_ascii=False, indent=2)
        + "\n"
    )

    # Add source_id enforcement
    if allowed_sources:
        final_prompt += "\n## IMPORTANT: Source ID Enforcement\n"
        final_prompt += "When citing from the allowed_sources above, you MUST include the source_id field in each citation.\n"
        final_prompt += "The source_id must match one of the source_id values from allowed_sources (e.g., SRC1, SRC2, etc.).\n"
        final_prompt += "This enables validation that citations reference only the curated sources provided.\n"

    return final_prompt
