from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class QAItem:
    question_id: str
    question: str


@dataclass(frozen=True)
class SolutionItem:
    solution_id: str
    solution: str
    mechanism: str


@dataclass(frozen=True)
class FrameworkItem:
    item_id: str
    category: str
    root_cause: str
    definition: str


@dataclass(frozen=True)
class InterventionItem:
    intervention_id: str
    lever: str
    intervention: str
    mechanism: str


@dataclass(frozen=True)
class DomainItem:
    domain_id: str
    domain: str


def _first_list(spec: Dict[str, Any], keys: Sequence[str]) -> List[Any]:
    for k in keys:
        v = spec.get(k)
        if isinstance(v, list):
            return v
    return []


def _find_list_of_dicts(spec: Dict[str, Any], predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
    # Shallow scan for first list of dicts that matches predicate for at least one element
    for v in spec.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            if any(predicate(x) for x in v):
                return v  # type: ignore[return-value]
    return []


def _clean(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def extract_phase1_questions(spec: Dict[str, Any]) -> List[QAItem]:
    candidates: List[Any] = _first_list(spec, ("questions", "discovery_questions", "items"))
    if not candidates:
        candidates = _find_list_of_dicts(spec, lambda x: ("question" in x) or ("prompt" in x))

    out: List[QAItem] = []
    for i, q in enumerate(candidates, start=1):
        if not isinstance(q, dict):
            continue
        qid = _clean(q.get("question_id") or q.get("id") or q.get("qid") or f"q{i}")
        text = _clean(q.get("question") or q.get("text") or q.get("prompt") or q.get("question_text"))
        if qid and text:
            out.append(QAItem(question_id=qid, question=text))

    if not out:
        raise ValueError("extract_phase1_questions: could not find question_id + question text in spec.")
    return out


def extract_rrr_solutions(spec: Dict[str, Any]) -> List[SolutionItem]:
    candidates: List[Any] = _first_list(spec, ("solutions", "rrr_solutions", "items"))
    if not candidates:
        candidates = _find_list_of_dicts(spec, lambda x: ("solution" in x) or ("intervention" in x))

    # If not found, check for intervention_families_seed_list (RRR spec format)
    if not candidates:
        seed_list = spec.get("intervention_families_seed_list")
        if isinstance(seed_list, list) and seed_list:
            out: List[SolutionItem] = []
            for i, family in enumerate(seed_list, start=1):
                if isinstance(family, str) and family.strip():
                    readable = family.replace("_", " ").title()
                    out.append(SolutionItem(
                        solution_id=f"int_{i}",
                        solution=readable,
                        mechanism=f"Mechanism for {readable} (stub placeholder)"
                    ))
            if out:
                return out

    out: List[SolutionItem] = []
    for i, s in enumerate(candidates, start=1):
        if not isinstance(s, dict):
            continue
        sid = _clean(s.get("solution_id") or s.get("id") or f"s{i}")
        sol = _clean(s.get("solution") or s.get("intervention") or s.get("title"))
        mech = _clean(s.get("mechanism") or s.get("description") or s.get("how_it_works"))
        if sid and sol and mech:
            out.append(SolutionItem(solution_id=sid, solution=sol, mechanism=mech))

    if not out:
        raise ValueError("extract_rrr_solutions: could not find solution + mechanism in spec.")
    return out


def extract_table2_items(spec: Dict[str, Any]) -> List[FrameworkItem]:
    candidates: List[Any] = _first_list(spec, ("framework_items", "items", "root_causes", "table2", "rows"))
    if not candidates:
        candidates = _find_list_of_dicts(spec, lambda x: ("cause" in x) or ("root" in x) or ("category" in x))

    # If not found, check for levels structure (Table 2 spec format)
    if not candidates:
        levels = spec.get("levels")
        if isinstance(levels, list) and levels:
            out: List[FrameworkItem] = []
            for level in levels:
                if not isinstance(level, dict):
                    continue
                level_id = _clean(level.get("level_id") or level.get("id"))
                label = _clean(level.get("label") or level.get("name"))
                primary_factors = level.get("primary_factors") or []
                if level_id and label:
                    factors_str = ", ".join(primary_factors) if primary_factors else "various factors"
                    out.append(FrameworkItem(
                        item_id=level_id,
                        category=label,
                        root_cause=f"Root causes at {label} level",
                        definition=f"Factors affecting performance at the {label} level, including {factors_str} (stub placeholder)"
                    ))
            if out:
                return out

    out: List[FrameworkItem] = []
    for i, it in enumerate(candidates, start=1):
        if not isinstance(it, dict):
            continue
        item_id = _clean(it.get("item_id") or it.get("id") or f"t2_{i}")
        category = _clean(it.get("category") or it.get("domain") or it.get("pillar"))
        root_cause = _clean(it.get("root_cause") or it.get("cause") or it.get("driver") or it.get("rootCause"))
        definition = _clean(it.get("definition") or it.get("description") or it.get("details"))
        if item_id and category and root_cause and definition:
            out.append(FrameworkItem(item_id=item_id, category=category, root_cause=root_cause, definition=definition))

    if not out:
        raise ValueError("extract_table2_items: could not find category/root_cause/definition in spec.")
    return out


def extract_table3_items(spec: Dict[str, Any]) -> List[InterventionItem]:
    candidates: List[Any] = _first_list(spec, ("interventions", "items", "table3", "rows"))
    if not candidates:
        candidates = _find_list_of_dicts(spec, lambda x: ("intervention" in x) or ("lever" in x) or ("mechanism" in x))

    # If not found, check for domains structure (Table 3 spec format)
    # Creates one item per domain, with objectives summarised in the mechanism
    # so the LLM receives meaningful context rather than placeholder text.
    if not candidates:
        domains = spec.get("domains")
        objectives = spec.get("objectives")
        if isinstance(domains, list) and domains and isinstance(objectives, list) and objectives:
            readable_objectives = [str(o).replace("_", " ") for o in objectives]
            objectives_summary = ", ".join(readable_objectives)
            out: List[InterventionItem] = []
            for i, domain in enumerate(domains, start=1):
                domain_str = _clean(domain)
                readable_domain = domain_str.replace("_", " ").title()
                out.append(InterventionItem(
                    intervention_id=f"int_{i}",
                    lever=readable_domain,
                    intervention=f"{readable_domain} interventions",
                    mechanism=f"Interventions in the {readable_domain} domain targeting: {objectives_summary}"
                ))
            if out:
                return out

    out: List[InterventionItem] = []
    for i, it in enumerate(candidates, start=1):
        if not isinstance(it, dict):
            continue
        iid = _clean(it.get("intervention_id") or it.get("id") or f"t3_{i}")
        lever = _clean(it.get("lever") or it.get("domain") or it.get("category"))
        intervention = _clean(it.get("intervention") or it.get("name") or it.get("title"))
        mechanism = _clean(it.get("mechanism") or it.get("description") or it.get("how_it_works"))
        if iid and lever and intervention and mechanism:
            out.append(InterventionItem(intervention_id=iid, lever=lever, intervention=intervention, mechanism=mechanism))

    if not out:
        raise ValueError("extract_table3_items: could not find lever/intervention/mechanism in spec.")
    return out


def extract_learning_domains(spec: Dict[str, Any]) -> List[DomainItem]:
    candidates: List[Any] = _first_list(spec, ("domains", "learning_domains", "items"))
    if not candidates:
        candidates = _find_list_of_dicts(spec, lambda x: ("domain" in x) or ("learning" in x) or ("label" in x))

    out: List[DomainItem] = []
    for i, d in enumerate(candidates, start=1):
        if not isinstance(d, dict):
            continue
        did = _clean(d.get("domain_id") or d.get("id") or f"ld_{i}")
        name = _clean(d.get("domain") or d.get("label") or d.get("name") or d.get("title"))
        if did and name:
            out.append(DomainItem(domain_id=did, domain=name))

    if not out:
        raise ValueError("extract_learning_domains: could not find domain_id + domain label in spec.")
    return out


@dataclass(frozen=True)
class BenchmarkDimension:
    dimension_id: str
    label: str


@dataclass(frozen=True)
class BenchmarkCountry:
    country_name: str
    iso3: str


def extract_benchmark_dimensions_countries(spec: Dict[str, Any]) -> Tuple[List[BenchmarkDimension], List[BenchmarkCountry]]:
    dims_raw: List[Any] = _first_list(spec, ("dimensions", "scoring_dimensions", "criteria"))
    if not dims_raw:
        dims_raw = _find_list_of_dicts(spec, lambda x: ("dimension" in x) or ("criteria" in x) or ("label" in x))

    # If not found at top level, collect criteria from phase objects (benchmark spec format)
    # e.g. phase2_hrh_relevance_and_reform_maturity.criteria, phase3_...criteria, etc.
    if not dims_raw:
        for key, val in spec.items():
            if isinstance(val, dict) and "criteria" in val:
                criteria = val["criteria"]
                if isinstance(criteria, list):
                    dims_raw.extend(criteria)

    dims: List[BenchmarkDimension] = []
    for i, d in enumerate(dims_raw, start=1):
        if not isinstance(d, dict):
            continue
        did = _clean(d.get("dimension_id") or d.get("criterion_id") or d.get("id") or f"d{i}")
        lab = _clean(d.get("label") or d.get("name") or d.get("title"))
        if did and lab:
            dims.append(BenchmarkDimension(dimension_id=did, label=lab))

    c_raw: List[Any] = _first_list(spec, ("countries", "benchmark_countries", "candidates"))
    if not c_raw:
        c_raw = _find_list_of_dicts(spec, lambda x: ("iso3" in x) or ("country" in x) or ("name" in x))

    countries: List[BenchmarkCountry] = []
    for c in c_raw:
        if not isinstance(c, dict):
            continue
        name = _clean(c.get("country_name") or c.get("name"))
        iso3 = _clean(c.get("iso3") or c.get("ISO3")).upper()
        if name and iso3:
            countries.append(BenchmarkCountry(country_name=name, iso3=iso3))

    if not dims:
        dims = [BenchmarkDimension(dimension_id="d1", label="placeholder_dimension")]
    if not countries:
        countries = [BenchmarkCountry(country_name="placeholder_country", iso3="XXX")]

    return dims, countries
