from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@dataclass
class SchemaValidationError(Exception):
    schema_path: str
    message: str
    errors: list[str]

    def __str__(self) -> str:
        details = "\n".join(f"- {e}" for e in self.errors)
        return f"{self.message}\nSchema: {self.schema_path}\n{details}"


def _strict_citations_enabled() -> bool:
    return os.getenv("HRH_STRICT_CITATIONS", "").strip().lower() in ("1", "true", "yes", "on")


def _is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _enforce_allowed_sources_enabled() -> bool:
    return os.getenv("HRH_ENFORCE_ALLOWED_SOURCES", "").strip().lower() in ("1", "true", "yes", "on")


def _get_allowed_source_ids() -> set[str]:
    """Get the allowed source IDs from environment variable."""
    ids_str = os.getenv("HRH_ALLOWED_SOURCE_IDS", "")
    if not ids_str:
        return set()
    return {sid.strip() for sid in ids_str.split(",") if sid.strip()}


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read JSON at {path}: {e}") from e


def _build_registry_for_dir(schema_dir: Path) -> Registry:
    """
    Build a registry of all *.json schemas in schema_dir so relative $ref like
    'common.json#/$defs/...' resolves reliably without deprecated RefResolver.
    """
    reg: Registry = Registry()
    for p in schema_dir.glob("*.json"):
        try:
            contents = _load_json(p)
            # Use a file URI so Draft202012Validator can resolve references
            uri = p.resolve().as_uri()
            reg = reg.with_resource(uri, Resource.from_contents(contents))
            # Also register the bare filename URI for convenience
            reg = reg.with_resource(p.name, Resource.from_contents(contents))
        except (ValueError, json.JSONDecodeError):
            # Skip empty or invalid schema files (placeholders)
            continue
    return reg


def _validate_domain_solutions_citations(payload: Dict[str, Any], schema_file: Path) -> None:
    """Semantic citation-cap validation for domain_solutions_from_evidence.

    Rules applied per solution:
    - evidence_strength strong/moderate: at most 3 citations per doc_id
    - evidence_strength weak:            at most 1 citation per doc_id
    - Overall:                           at most 3 citations per solution
    """
    _MAX_PER_SOL = 3
    _MAX_PER_DOC: Dict[str, int] = {"strong": 3, "moderate": 3, "weak": 1}

    for domain in payload.get("domains", []):
        d_id = domain.get("domain_id", "?")
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id", "?")
            for sol in fa.get("solutions", []):
                sol_id = sol.get("solution_id", "?")
                strength = sol.get("evidence_strength", "weak")
                allowed_per_doc = _MAX_PER_DOC.get(strength, 1)
                citations = sol.get("citations", [])

                errors: list[str] = []

                # Overall cap
                if len(citations) > _MAX_PER_SOL:
                    errors.append(
                        f"solution '{sol_id}' has {len(citations)} citations "
                        f"(max {_MAX_PER_SOL} total per solution)"
                    )

                # Per-doc-id cap
                doc_counts: Dict[str, int] = {}
                for cit in citations:
                    doc_id = cit.get("doc_id", "")
                    doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
                for doc_id, count in doc_counts.items():
                    if count > allowed_per_doc:
                        errors.append(
                            f"solution '{sol_id}' (evidence_strength='{strength}'): "
                            f"doc_id '{doc_id}' has {count} citations "
                            f"(max {allowed_per_doc} per doc_id for this evidence_strength — "
                            f"remove or consolidate extra citations from this source)"
                        )

                if errors:
                    raise SchemaValidationError(
                        schema_path=str(schema_file),
                        message=f"Citation policy violation in domain='{d_id}', focus_area='{fa_id}'",
                        errors=errors,
                    )


_LESSON_ALL_CATEGORIES = (
    "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
    "operational_barriers", "governance_process_dependencies",
    "evidence_gaps_uncertainty", "costs_resource_intensity", "equity_implications",
    "consequences_impacts",
)


def _validate_domain_lessons_item_id_uniqueness(payload: Dict[str, Any], schema_file: Path) -> None:
    """Check that within each focus_area, all item_ids are unique across all 9 category arrays."""
    for domain in payload.get("domains", []):
        d_id = domain.get("domain_id", "?")
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id", "?")
            seen: Dict[str, str] = {}   # item_id → first-seen category
            duplicates: list[str] = []
            for cat in _LESSON_ALL_CATEGORIES:
                for item in fa.get(cat, []):
                    iid = item.get("item_id", "")
                    if not iid:
                        continue
                    if iid in seen:
                        duplicates.append(
                            f"item_id '{iid}' appears in both '{seen[iid]}' and '{cat}'"
                        )
                    else:
                        seen[iid] = cat
            if duplicates:
                raise SchemaValidationError(
                    schema_path=str(schema_file),
                    message=f"Duplicate item_ids in domain='{d_id}', focus_area='{fa_id}'",
                    errors=duplicates,
                )


# Keywords that signal genuine implementation-barrier framing (case-insensitive substring match).
# Kept deliberately narrow to avoid false positives while catching causal/statistical framings.
_OB_BARRIER_KEYWORDS = (
    "lack of", "lacking", "without", "absence of", "insufficient",
    "inadequate", "barrier", "constraint", "difficulty",
    "hurdle", "challenge", "shortage",
    # Quantitative/operational gap framing common in health evidence literature
    "negligible", "gap", "low coverage", "not being",
    "not meet", "low rate", "unavailability",
    # Systemic weakness framing
    "weak", "poor", "limited",
    # Unplanned burden framing
    "unplanned",
    # Payment absence framing
    "not paid",
    # Quantitative inadequacy
    "very low", "is low",
    # Working condition barriers
    "hardship", "unsafe", "insecure",
    # Policy/rights/equity barriers
    "restrictions", "not uniform",
    # Off-role task burden
    "non-health", "non-hep",
    # Systemic failure framing
    "sporadic", "inefficien",
    # Housing / deployment absence framing
    "no house",
    # Challenge/difficulty stem (matches "challenge", "challenged", "challenging")
    "challeng",
    # Skill/resource mismatch framing
    "mismatch",
    # Workload / task burden framing
    "overload",
    # Off-role tasks (HEWs doing work not related to health)
    "not related",
    # Demotivation as barrier to attendance/performance
    "demotivat",
    # Gender-role / maternity deployment barrier
    "maternity",
)

# Fallback keywords checked against the item's *statement* when the snippet is empty or
# lacks primary barrier keywords. These capture operational cost/complexity language that
# the LLM may express in the statement even when the source snippet is brief or empty.
_OB_BARRIER_STMT_KEYWORDS = (
    "lengthy", "time-intensive", "time-consuming", "resources", "requir", "resource-intensive",
    "constraint", "challeng", "hurdle", "difficult", "burdensome",
    "inefficien", "weak",
    # Explicit barrier label in statement
    "barrier",
    # Adequacy / sufficiency framing in statement
    "inadequate", "insufficient",
    # Timeliness / limiting framing
    "not timely", "limit",
)

# Keywords that signal downstream impact/consequence framing.
_CI_IMPACT_KEYWORDS = (
    "consequence", "resulted in", "led to", "increased", "delayed",
    "burden", "cost", "workload", "quality", "access", "reduced",
    "overwhelm", "overwhelmed", "stress", "strain",
    # Expanded: common health-literature impact framing
    "impact", "profound", "suffering", "harm", "patient safety",
    "outcomes", "compromised", "risk", "mortality", "morbidity",
    # HRH-specific consequence framing
    "absenteeism", "part-time", "closed",
    # Availability / performance deterioration
    "sporadic", "deteriorat", "declin",
    # Negative impact framing
    "negatively",
)

# Broad terms used in the fallback check: if a snippet contains one of these AND
# the item's statement contains a primary impact keyword, the item is accepted.
# This handles cases where the snippet is truncated before the impact keyword appears.
_CI_IMPACT_BROAD = (
    "workload", "access", "cost", "delay", "burden",
    "quality", "care", "patient", "community", "staff",
)


def _validate_domain_lessons_barrier_snippets(payload: Dict[str, Any], schema_file: Path) -> None:
    """operational_barriers items must have at least one citation snippet with barrier framing.

    Items whose snippets only describe causes or statistical determinants (e.g. "causes
    included insufficient supervision") should be in lessons_learnt instead.
    """
    for domain in payload.get("domains", []):
        d_id = domain.get("domain_id", "?")
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id", "?")
            for item in fa.get("operational_barriers", []):
                item_id = item.get("item_id", "?")
                snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]
                has_keyword = any(
                    kw in snip.lower()
                    for snip in snippets
                    for kw in _OB_BARRIER_KEYWORDS
                )
                if not has_keyword:
                    # Fallback: accept if the item's statement itself uses barrier/cost language.
                    # This handles cases where the LLM cannot reproduce the exact source phrase
                    # (e.g. snippet is empty or truncated) but the statement clearly frames the
                    # item as an operational constraint rather than a cause or consequence.
                    statement = item.get("statement", "").lower()
                    if any(kw in statement for kw in _OB_BARRIER_STMT_KEYWORDS):
                        continue

                    has_impact = any(
                        kw in snip.lower()
                        for snip in snippets
                        for kw in _CI_IMPACT_KEYWORDS
                    )
                    if has_impact:
                        suggestion = (
                            "if this describes a downstream outcome/impact, use consequences_impacts instead; "
                            "if it describes a cause or determinant, use lessons_learnt "
                            "(evidence_type=determinant_mechanism) instead"
                        )
                    else:
                        suggestion = (
                            "if this describes a cause or determinant, use lessons_learnt "
                            "(evidence_type=determinant_mechanism) instead"
                        )
                    raise SchemaValidationError(
                        schema_path=str(schema_file),
                        message=(
                            f"operational_barriers item '{item_id}' in domain='{d_id}', "
                            f"focus_area='{fa_id}' has no citation snippet with barrier framing — "
                            f"{suggestion}"
                        ),
                        errors=[
                            f"None of the {len(snippets)} snippet(s) contain a barrier keyword "
                            f"({', '.join(repr(k) for k in _OB_BARRIER_KEYWORDS)}). "
                            f"Snippet(s): " + "; ".join(f'"{s[:100]}"' for s in snippets)
                        ],
                    )


def _validate_domain_lessons_impact_snippets(payload: Dict[str, Any], schema_file: Path) -> None:
    """consequences_impacts items must have impact framing in their snippet or statement.

    Primary check: at least one citation snippet contains an impact keyword.
    Fallback: the item statement contains an impact keyword AND at least one snippet
    contains a broad impact-related term (handles snippets truncated before the keyword).

    Items whose snippets and statement only describe barriers or causes should be in
    operational_barriers or lessons_learnt instead.
    """
    for domain in payload.get("domains", []):
        d_id = domain.get("domain_id", "?")
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id", "?")
            for item in fa.get("consequences_impacts", []):
                item_id = item.get("item_id", "?")
                snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]

                # Primary check: impact keyword in any snippet
                has_keyword = any(
                    kw in snip.lower()
                    for snip in snippets
                    for kw in _CI_IMPACT_KEYWORDS
                )
                if has_keyword:
                    continue

                # Fallback: statement has impact keyword + snippet has broad impact term
                statement = item.get("statement", "").lower()
                has_stmt_keyword = any(kw in statement for kw in _CI_IMPACT_KEYWORDS)
                has_broad_snip = any(
                    term in snip.lower()
                    for snip in snippets
                    for term in _CI_IMPACT_BROAD
                )
                if has_stmt_keyword and has_broad_snip:
                    continue

                raise SchemaValidationError(
                    schema_path=str(schema_file),
                    message=(
                        f"consequences_impacts item '{item_id}' in domain='{d_id}', "
                        f"focus_area='{fa_id}' has no citation snippet with impact framing — "
                        f"if this describes a barrier, use operational_barriers instead; "
                        f"if it describes a cause, use lessons_learnt (evidence_type=determinant_mechanism)"
                    ),
                    errors=[
                        f"None of the {len(snippets)} snippet(s) contain an impact keyword "
                        f"({', '.join(repr(k) for k in _CI_IMPACT_KEYWORDS)}); "
                        f"fallback also failed (statement impact keyword={has_stmt_keyword}, "
                        f"snippet broad term={has_broad_snip}). "
                        "Snippet(s): " + "; ".join(f'"{s[:100]}"' for s in snippets)
                    ],
                )


def _validate_proven_interventions_are_actions(payload: Dict[str, Any], schema_file: Path) -> None:
    """proven_interventions must not contain items with evidence_type=determinant_mechanism.

    Such items describe causes, correlates, or barriers — not implementable actions.
    They should be placed in lessons_learnt, operational_barriers, or consequences_impacts.
    """
    for domain in payload.get("domains", []):
        d_id = domain.get("domain_id", "?")
        for fa in domain.get("focus_areas", []):
            fa_id = fa.get("focus_area_id", "?")
            bad: list[str] = []
            for item in fa.get("proven_interventions", []):
                if item.get("evidence_type") == "determinant_mechanism":
                    bad.append(item.get("item_id", "?"))
            if bad:
                raise SchemaValidationError(
                    schema_path=str(schema_file),
                    message=(
                        f"proven_interventions items in domain='{d_id}', focus_area='{fa_id}' "
                        f"have evidence_type='determinant_mechanism' — these describe causes or "
                        f"barriers, not implementable actions. Move them to lessons_learnt, "
                        f"operational_barriers, or consequences_impacts."
                    ),
                    errors=[
                        f"Item '{iid}' has evidence_type='determinant_mechanism' but is in proven_interventions"
                        for iid in bad
                    ],
                )


def validate_output(payload: Dict[str, Any], schema_path: str, base_dir: Optional[str] = None) -> None:
    """
    Validate an output payload against a JSON Schema (Draft 2020-12).

    - schema_path: path like 'schemas/phase1_discovery_qa.schema.json'
    - base_dir: optional base directory; defaults to current working directory
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    schema_file = (base / schema_path).resolve()

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema not found: {schema_file}")

    schema_dir = schema_file.parent
    registry = _build_registry_for_dir(schema_dir)

    schema = _load_json(schema_file)
    validator = Draft202012Validator(schema, registry=registry)

    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        formatted = []
        for e in errors:
            loc = "$"
            for part in e.path:
                if isinstance(part, int):
                    loc += f"[{part}]"
                else:
                    loc += f".{part}"
            formatted.append(f"{loc}: {e.message}")
        raise SchemaValidationError(
            schema_path=str(schema_file),
            message="Output failed schema validation",
            errors=formatted,
        )

    # Job-specific semantic validation
    if payload.get("job_id") == "domain_solutions_from_evidence":
        _validate_domain_solutions_citations(payload, schema_file)

    if payload.get("job_id") == "domain_lessons_option_b":
        _validate_domain_lessons_item_id_uniqueness(payload, schema_file)
        _validate_proven_interventions_are_actions(payload, schema_file)
        _validate_domain_lessons_barrier_snippets(payload, schema_file)
        _validate_domain_lessons_impact_snippets(payload, schema_file)

    # Optional strict gate: citations must have real identifiers
    if _strict_citations_enabled():
        def walk(obj, path="$"):
            if isinstance(obj, dict):
                # If this dict looks like a citation, enforce identifier
                if "source_title" in obj and "locator" in obj:
                    su = obj.get("source_url")
                    ref = obj.get("reference")
                    doi = obj.get("doi")
                    isbn = obj.get("isbn")

                    sid = obj.get("source_id")
                    did = obj.get("doc_id")  # LocalCitation identifier (domain_lessons jobs)
                    has_source_id = isinstance(sid, str) and sid.strip() != ""
                    has_doc_id = isinstance(did, str) and did.strip() != ""
                    has_http_url = isinstance(su, str) and _is_http_url(su)
                    has_ref = isinstance(ref, str) and ref.strip() != ""
                    has_doi = isinstance(doi, str) and doi.strip() != ""
                    has_isbn = isinstance(isbn, str) and isbn.strip() != ""

                    if not (has_source_id or has_doc_id or has_http_url or has_ref or has_doi or has_isbn):
                        raise SchemaValidationError(
                            schema_path=str(schema_file),
                            message="Strict citation validation failed (HRH_STRICT_CITATIONS=1)",
                            errors=[f"{path} must include either a valid source_id, doc_id, http(s) source_url, or a non-empty reference/doi/isbn."],
                        )
                for k, v in obj.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")

        walk(payload)

    # Optional allowed sources enforcement: citations must reference curated sources
    if _enforce_allowed_sources_enabled():
        allowed_ids = _get_allowed_source_ids()
        if allowed_ids:
            def walk_sources(obj, path="$"):
                if isinstance(obj, dict):
                    # If this dict looks like a citation, check source_id
                    if "source_title" in obj and "locator" in obj:
                        source_id = obj.get("source_id")
                        if not source_id:
                            raise SchemaValidationError(
                                schema_path=str(schema_file),
                                message="Source ID enforcement failed (HRH_ENFORCE_ALLOWED_SOURCES=1)",
                                errors=[f"{path}: Citation must include 'source_id' field when using curated sources."],
                            )
                        if source_id not in allowed_ids:
                            raise SchemaValidationError(
                                schema_path=str(schema_file),
                                message="Source ID enforcement failed (HRH_ENFORCE_ALLOWED_SOURCES=1)",
                                errors=[f"{path}: source_id '{source_id}' is not in allowed sources: {sorted(allowed_ids)}"],
                            )
                    for k, v in obj.items():
                        walk_sources(v, f"{path}.{k}")
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        walk_sources(v, f"{path}[{i}]")

            walk_sources(payload)
