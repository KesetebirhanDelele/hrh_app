from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _autosize(ws) -> None:
    for col in range(1, ws.max_column + 1):
        max_len = 0
        for row in range(1, ws.max_row + 1):
            v = ws.cell(row=row, column=col).value
            if v is None:
                continue
            max_len = max(max_len, len(str(v)))
        ws.column_dimensions[get_column_letter(col)].width = min(max(12, max_len + 2), 60)


def _write_header(ws, headers: List[str]) -> None:
    ws.append(headers)
    for i in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True)
        c.alignment = Alignment(vertical="top", wrap_text=True)


def _flatten_citations(evidence: Dict[str, Any]) -> str:
    cits = evidence.get("citations") or []
    parts = []
    for c in cits:
        title = c.get("source_title", "")
        locator = c.get("locator", "")
        url = c.get("source_url", "")
        bits = [b for b in [title, locator, url] if b]
        if bits:
            parts.append(" | ".join(bits))
    return "\n".join(parts)


def render_xlsx(job_id: str, payload: Dict[str, Any], out_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    if job_id == "rrr_evidence_matrix":
        headers = [
            "solution_id", "solution", "mechanism",
            "feasibility_resource_constrained",
            "evidence_quality", "evidence_rationale", "citations",
            "risks", "implementation_notes"
        ]
        _write_header(ws, headers)
        for s in payload.get("solutions", []):
            ev = s.get("evidence", {})
            ws.append([
                s.get("solution_id", ""),
                s.get("solution", ""),
                s.get("mechanism", ""),
                s.get("feasibility_resource_constrained", ""),
                ev.get("quality", ""),
                ev.get("rationale", ""),
                _flatten_citations(ev),
                "; ".join(s.get("risks", []) or []),
                s.get("implementation_notes", "") or "",
            ])

    elif job_id == "table2_root_cause_mapping":
        headers = [
            "item_id", "category", "root_cause", "definition",
            "evidence_quality", "evidence_rationale", "citations", "tags"
        ]
        _write_header(ws, headers)
        for it in payload.get("framework_items", []):
            ev = it.get("evidence", {})
            ws.append([
                it.get("item_id", ""),
                it.get("category", ""),
                it.get("root_cause", ""),
                it.get("definition", ""),
                ev.get("quality", ""),
                ev.get("rationale", ""),
                _flatten_citations(ev),
                "; ".join(it.get("tags", []) or []),
            ])

    elif job_id == "table3_intervention_framework":
        headers = [
            "intervention_id", "lever", "intervention", "mechanism",
            "implementation_notes", "dependencies", "risks",
            "evidence_quality", "evidence_rationale", "citations"
        ]
        _write_header(ws, headers)
        for it in payload.get("interventions", []):
            ev = it.get("evidence", {})
            ws.append([
                it.get("intervention_id", ""),
                it.get("lever", ""),
                it.get("intervention", ""),
                it.get("mechanism", ""),
                it.get("implementation_notes", "") or "",
                "; ".join(it.get("dependencies", []) or []),
                "; ".join(it.get("risks", []) or []),
                ev.get("quality", ""),
                ev.get("rationale", ""),
                _flatten_citations(ev),
            ])

    elif job_id == "benchmark_country_scoring":
        # Sheet 1: per-country overview
        ws.title = "countries"
        _write_header(ws, ["country_name", "iso3", "overall_score", "overall_quality", "overall_rationale", "overall_citations"])
        for c in payload.get("countries", []):
            overall = c.get("overall_score", {})
            ev = overall.get("evidence", {})
            ws.append([
                c.get("country_name", ""),
                c.get("iso3", ""),
                overall.get("score", ""),
                ev.get("quality", ""),
                ev.get("rationale", ""),
                _flatten_citations(ev),
            ])
        _autosize(ws)

        # Sheet 2: dimension breakdown (long format)
        ws2 = wb.create_sheet("dimensions")
        _write_header(ws2, ["country_name", "iso3", "dimension_id", "label", "score", "quality", "rationale", "citations"])
        for c in payload.get("countries", []):
            for d in c.get("dimensions", []):
                sn = d.get("score_note", {})
                ev = sn.get("evidence", {})
                ws2.append([
                    c.get("country_name", ""),
                    c.get("iso3", ""),
                    d.get("dimension_id", ""),
                    d.get("label", ""),
                    sn.get("score", ""),
                    ev.get("quality", ""),
                    ev.get("rationale", ""),
                    _flatten_citations(ev),
                ])
        _autosize(ws2)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
        return out_path

    elif job_id == "domain_solutions_from_evidence":
        # Sheet 1: one row per solution (flat)
        ws.title = "solutions"
        headers = [
            "domain_id", "focus_area_id", "solution_id", "title",
            "evidence_strength", "description", "mechanism",
            "implementation_conditions", "risks", "implementation_notes", "citations",
        ]
        _write_header(ws, headers)
        for domain in payload.get("domains", []):
            d_id = domain.get("domain_id", "")
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                for sol in fa.get("solutions", []):
                    conds = "\n".join(sol.get("implementation_conditions", []) or [])
                    risks = "; ".join(sol.get("risks", []) or [])
                    cit_lines = "\n".join(
                        f"{c.get('source_title') or c.get('doc_id', '')} | {c.get('locator', '')}"
                        for c in sol.get("citations", [])
                    )
                    ws.append([
                        d_id,
                        fa_id,
                        sol.get("solution_id", ""),
                        sol.get("title", ""),
                        sol.get("evidence_strength", ""),
                        sol.get("description", ""),
                        sol.get("mechanism", ""),
                        conds,
                        risks,
                        sol.get("implementation_notes", "") or "",
                        cit_lines,
                    ])
        _autosize(ws)
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # Sheet 2: one row per citation (long format)
        ws2 = wb.create_sheet("citations")
        _write_header(ws2, [
            "domain_id", "focus_area_id", "solution_id", "title",
            "source_title", "doc_id", "locator", "snippet",
        ])
        for domain in payload.get("domains", []):
            d_id = domain.get("domain_id", "")
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                for sol in fa.get("solutions", []):
                    for cit in sol.get("citations", []):
                        ws2.append([
                            d_id,
                            fa_id,
                            sol.get("solution_id", ""),
                            sol.get("title", ""),
                            cit.get("source_title", "") or cit.get("doc_id", ""),
                            cit.get("doc_id", ""),
                            cit.get("locator", ""),
                            cit.get("snippet", ""),
                        ])
        _autosize(ws2)
        for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, min_col=1, max_col=ws2.max_column):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
        return out_path

    elif job_id == "domain_lessons_option_b":
        _ITEM_CATS = (
            "proven_interventions", "lessons_learnt", "recommendations", "prerequisites",
            "operational_barriers", "governance_process_dependencies",
            "evidence_gaps_uncertainty", "equity_implications", "consequences_impacts",
        )
        _COST_CAT = "costs_resource_intensity"

        # Sheet 1: items — one row per Item across all 8 Item categories
        ws.title = "items"
        _write_header(ws, [
            "domain_id", "focus_area_id", "category", "item_id", "title",
            "evidence_type", "evidence_strength", "statement", "mechanism",
            "applicable_countries", "citations",
        ])
        for domain in payload.get("domains", []):
            d_id = domain.get("domain_id", "")
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                for cat in _ITEM_CATS:
                    for item in fa.get(cat, []):
                        cit_lines = "\n".join(
                            f"{c.get('source_title') or c.get('doc_id', '')} | {c.get('locator', '')}"
                            for c in item.get("citations", [])
                        )
                        countries = ", ".join(item.get("applicable_countries") or [])
                        ws.append([
                            d_id, fa_id, cat,
                            item.get("item_id", ""),
                            item.get("title", ""),
                            item.get("evidence_type", ""),
                            item.get("evidence_strength", ""),
                            item.get("statement", ""),
                            item.get("mechanism", "") or "",
                            countries,
                            cit_lines,
                        ])
        _autosize(ws)
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # Sheet 2: costs — one row per CostItem
        ws2 = wb.create_sheet("costs")
        _write_header(ws2, [
            "domain_id", "focus_area_id", "item_id", "title",
            "intensity", "cost_drivers", "statement", "applicable_countries", "citations",
        ])
        for domain in payload.get("domains", []):
            d_id = domain.get("domain_id", "")
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                for item in fa.get(_COST_CAT, []):
                    cit_lines = "\n".join(
                        f"{c.get('source_title') or c.get('doc_id', '')} | {c.get('locator', '')}"
                        for c in item.get("citations", [])
                    )
                    countries = ", ".join(item.get("applicable_countries") or [])
                    ws2.append([
                        d_id, fa_id,
                        item.get("item_id", ""),
                        item.get("title", ""),
                        item.get("intensity", ""),
                        "; ".join(item.get("cost_drivers", []) or []),
                        item.get("statement", ""),
                        countries,
                        cit_lines,
                    ])
        _autosize(ws2)
        for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, min_col=1, max_col=ws2.max_column):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # Sheet 3: citations — long format, one row per citation across all categories
        ws3 = wb.create_sheet("citations")
        _write_header(ws3, [
            "domain_id", "focus_area_id", "category", "item_id", "title",
            "source_title", "doc_id", "locator", "snippet",
        ])
        for domain in payload.get("domains", []):
            d_id = domain.get("domain_id", "")
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                for cat in _ITEM_CATS + (_COST_CAT,):
                    for item in fa.get(cat, []):
                        for cit in item.get("citations", []):
                            ws3.append([
                                d_id, fa_id, cat,
                                item.get("item_id", ""),
                                item.get("title", ""),
                                cit.get("source_title", "") or cit.get("doc_id", ""),
                                cit.get("doc_id", ""),
                                cit.get("locator", ""),
                                cit.get("snippet", ""),
                            ])
        _autosize(ws3)
        for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row, min_col=1, max_col=ws3.max_column):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
        return out_path

    else:
        raise KeyError(f"render_xlsx: unsupported job_id '{job_id}'")

    # Wrap + autosize
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    _autosize(ws)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def render_xlsx_file(job_id: str, input_json_path: str, output_xlsx_path: Optional[str] = None) -> Path:
    inp = Path(input_json_path).resolve()
    if not inp.exists():
        raise FileNotFoundError(f"Input file not found: {inp}")
    payload = _read_json(inp)
    out = Path(output_xlsx_path).resolve() if output_xlsx_path else inp.with_suffix(".xlsx")
    return render_xlsx(job_id, payload, out)
