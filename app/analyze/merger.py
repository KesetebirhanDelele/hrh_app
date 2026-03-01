"""Merge partial LLM outputs from per-source runs into a single result."""

from __future__ import annotations

from typing import Any, Dict, List

_QUALITY_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}
_STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1}
_MAX_CITATIONS_PER_SOLUTION = 3


def _cap_citations_by_source(citations: List[Dict[str, Any]], max_cits: int = _MAX_CITATIONS_PER_SOLUTION) -> List[Dict[str, Any]]:
    """Keep at most max_cits citations, preferring one per unique doc_id.

    First pass: take the first citation from each distinct doc_id.
    Second pass: fill any remaining slots from any source (in original order).
    """
    if len(citations) <= max_cits:
        return citations
    seen_docs: set[str] = set()
    selected: List[Dict[str, Any]] = []
    remainder: List[Dict[str, Any]] = []
    for cit in citations:
        doc_id = cit.get("doc_id", "")
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            selected.append(cit)
        else:
            remainder.append(cit)
        if len(selected) >= max_cits:
            return selected
    for cit in remainder:
        if len(selected) >= max_cits:
            break
        selected.append(cit)
    return selected

MERGE_CONFIG: Dict[str, Dict[str, Any]] = {
    "phase1_discovery_qa": {
        "array_key": "questions",
        "id_key": "question_id",
        "text_keys": ["answer"],
    },
    "rrr_evidence_matrix": {
        "array_key": "solutions",
        "id_key": "solution_id",
        "text_keys": ["implementation_notes"],
    },
    "table2_root_cause_mapping": {
        "array_key": "framework_items",
        "id_key": "item_id",
        "text_keys": ["definition"],
    },
    "table3_intervention_framework": {
        "array_key": "interventions",
        "id_key": "intervention_id",
        "text_keys": ["implementation_notes"],
    },
    "benchmark_country_scoring": {
        "array_key": "countries",
        "id_key": "country_name",
        "text_keys": [],
    },
    "country_learning_briefs": {
        "array_key": "domains",
        "id_key": "domain_id",
        "text_keys": ["summary"],
    },
}


def _merge_evidence(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two evidence blocks, keeping the higher quality and combining citations."""
    eq = _QUALITY_RANK.get(existing.get("quality", "none"), 0)
    iq = _QUALITY_RANK.get(incoming.get("quality", "none"), 0)

    if iq == 0:
        return existing  # incoming has no evidence, keep existing
    if eq == 0:
        return incoming  # existing has no evidence, take incoming

    # Both have evidence — combine
    merged = dict(existing)
    if iq > eq:
        merged["quality"] = incoming["quality"]
    # Combine rationales
    er = existing.get("rationale", "")
    ir = incoming.get("rationale", "")
    if ir and ir != er:
        merged["rationale"] = er + " " + ir if er else ir
    # Combine citations (deduplicate by source_id + locator)
    seen = set()
    combined_citations = []
    for cit in existing.get("citations", []) + incoming.get("citations", []):
        key = (cit.get("source_id", ""), cit.get("locator", ""), cit.get("source_title", ""))
        if key not in seen:
            seen.add(key)
            combined_citations.append(cit)
    merged["citations"] = combined_citations
    return merged


def _merge_items(
    existing: Dict[str, Any],
    incoming: Dict[str, Any],
    text_keys: List[str],
) -> Dict[str, Any]:
    """Merge two item dicts (same ID), combining text fields and evidence."""
    merged = dict(existing)

    # Merge text fields — append new content
    for key in text_keys:
        ev = existing.get(key, "")
        iv = incoming.get(key, "")
        if iv and iv != ev:
            merged[key] = ev + "\n\n" + iv if ev else iv

    # Merge evidence
    if "evidence" in existing or "evidence" in incoming:
        merged["evidence"] = _merge_evidence(
            existing.get("evidence", {"quality": "none", "rationale": "", "citations": []}),
            incoming.get("evidence", {"quality": "none", "rationale": "", "citations": []}),
        )

    # Merge array fields (tags, risks, dependencies, key_questions)
    for arr_key in ("tags", "risks", "dependencies", "key_questions"):
        if arr_key in existing or arr_key in incoming:
            e_arr = existing.get(arr_key, [])
            i_arr = incoming.get(arr_key, [])
            # Deduplicate strings; keep dicts as-is
            if e_arr and isinstance(e_arr[0], str):
                seen_vals: set[str] = set(e_arr)
                combined = list(e_arr)
                for val in i_arr:
                    if val not in seen_vals:
                        seen_vals.add(val)
                        combined.append(val)
                merged[arr_key] = combined
            else:
                merged[arr_key] = e_arr + [x for x in i_arr if x not in e_arr]

    return merged


def _merge_domain_solutions(partial_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge partial outputs for domain_solutions_from_evidence.

    Walks domains → focus_areas → solutions across all partials, deduplicating
    by title and combining citations and implementation_conditions.
    """
    base = dict(partial_outputs[0])

    # Nested map: domain_id → focus_area_id → title_lower → solution dict
    merged_map: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for output in partial_outputs:
        for domain in output.get("domains", []):
            d_id = domain.get("domain_id")
            if not d_id:
                continue
            if d_id not in merged_map:
                merged_map[d_id] = {}
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id")
                if not fa_id:
                    continue
                if fa_id not in merged_map[d_id]:
                    merged_map[d_id][fa_id] = {}
                for sol in fa.get("solutions", []):
                    title_key = sol.get("title", "").strip().lower()
                    if not title_key:
                        continue
                    if title_key not in merged_map[d_id][fa_id]:
                        merged_map[d_id][fa_id][title_key] = dict(sol)
                    else:
                        existing = merged_map[d_id][fa_id][title_key]
                        # Upgrade evidence_strength if incoming is stronger
                        e_rank = _STRENGTH_RANK.get(existing.get("evidence_strength", "weak"), 1)
                        i_rank = _STRENGTH_RANK.get(sol.get("evidence_strength", "weak"), 1)
                        if i_rank > e_rank:
                            existing["evidence_strength"] = sol["evidence_strength"]
                        # Combine implementation_conditions (deduplicate)
                        seen_conds: set[str] = set(existing.get("implementation_conditions", []))
                        for cond in sol.get("implementation_conditions", []):
                            if cond not in seen_conds:
                                seen_conds.add(cond)
                                existing.setdefault("implementation_conditions", []).append(cond)
                        # Combine risks (deduplicate)
                        seen_risks: set[str] = set(existing.get("risks", []))
                        for risk in sol.get("risks", []):
                            if risk not in seen_risks:
                                seen_risks.add(risk)
                                existing.setdefault("risks", []).append(risk)
                        # Append implementation_notes if different
                        en = (existing.get("implementation_notes") or "").strip()
                        in_ = (sol.get("implementation_notes") or "").strip()
                        if in_ and in_ != en:
                            existing["implementation_notes"] = (en + "\n" + in_).strip() if en else in_
                        # Combine citations (deduplicate by doc_id + locator), then cap
                        seen_cits: set[tuple] = {
                            (c.get("doc_id", ""), c.get("locator", ""))
                            for c in existing.get("citations", [])
                        }
                        for cit in sol.get("citations", []):
                            key = (cit.get("doc_id", ""), cit.get("locator", ""))
                            if key not in seen_cits:
                                seen_cits.add(key)
                                existing.setdefault("citations", []).append(cit)
                        existing["citations"] = _cap_citations_by_source(existing["citations"])

    # Reconstruct domains list preserving order from base, filling in merged solutions
    result_domains = []
    for domain in base.get("domains", []):
        d_id = domain.get("domain_id")
        fa_map = merged_map.get(d_id, {})
        result_fas = []
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id")
            sols_map = fa_map.get(fa_id, {})
            # Renumber solution_ids sequentially within each focus area
            solutions = []
            for n, sol in enumerate(sols_map.values(), 1):
                sol = dict(sol)
                sol["solution_id"] = f"{d_id}_{fa_id}_{n}"
                solutions.append(sol)
            result_fas.append({"focus_area_id": fa_id, "solutions": solutions})
        result_domains.append({"domain_id": d_id, "focus_areas": result_fas})

    base["domains"] = result_domains
    return base


def merge_outputs(
    job_id: str,
    partial_outputs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge multiple partial LLM outputs into a single output dict.

    Each partial output is expected to follow the same schema for *job_id*.
    Items are matched by their ID field and merged: text is concatenated,
    evidence quality is upgraded, and citations are combined.
    """
    if not partial_outputs:
        raise ValueError("merge_outputs: no partial outputs to merge")
    if len(partial_outputs) == 1:
        return partial_outputs[0]

    if job_id == "domain_solutions_from_evidence":
        return _merge_domain_solutions(partial_outputs)

    config = MERGE_CONFIG.get(job_id)
    if not config:
        raise KeyError(f"merge_outputs: no merge config for job_id '{job_id}'")

    array_key = config["array_key"]
    id_key = config["id_key"]
    text_keys = config.get("text_keys", [])

    # Use the first output as the base for top-level fields
    base = dict(partial_outputs[0])

    # Build merged items map
    items_map: Dict[str, Dict[str, Any]] = {}
    for output in partial_outputs:
        for item in output.get(array_key, []):
            item_id = item.get(id_key)
            if not item_id:
                continue
            if item_id not in items_map:
                items_map[item_id] = dict(item)
            else:
                items_map[item_id] = _merge_items(
                    items_map[item_id], item, text_keys
                )

    # Preserve original ordering from first output
    first_ids = [it.get(id_key) for it in partial_outputs[0].get(array_key, [])]
    ordered = []
    seen_ids: set[str] = set()
    for fid in first_ids:
        if fid in items_map and fid not in seen_ids:
            ordered.append(items_map[fid])
            seen_ids.add(fid)
    # Add any items not in the first output
    for item_id, item in items_map.items():
        if item_id not in seen_ids:
            ordered.append(item)

    base[array_key] = ordered
    return base
