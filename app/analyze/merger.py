"""Merge partial LLM outputs from per-source runs into a single result."""

from __future__ import annotations

from typing import Any, Dict, List

_QUALITY_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}

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
