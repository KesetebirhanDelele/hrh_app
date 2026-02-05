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
