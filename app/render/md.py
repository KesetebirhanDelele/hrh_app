from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _md_escape(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _render_citations(citations: List[Dict[str, Any]]) -> str:
    if not citations:
        return ""
    lines = ["**Citations**:"]
    for i, c in enumerate(citations, start=1):
        title = c.get("source_title", "Unknown source")
        locator = c.get("locator", "")
        url = c.get("source_url")
        published = c.get("published_date")
        parts = [f"{i}. {title}"]
        if published:
            parts.append(f"({published})")
        if locator:
            parts.append(f"— {locator}")
        if url:
            parts.append(f"— {url}")
        lines.append(" ".join(parts))
        quote = c.get("quote")
        if quote:
            lines.append(f"   - _Quote_: {quote}")
    return "\n".join(lines)


def render_markdown(job_id: str, payload: Dict[str, Any]) -> str:
    """
    Job-aware markdown renderer. Keeps it simple and readable.
    Assumes payload already validated by schema.
    """
    title = f"# {job_id}\n"
    meta = []
    if payload.get("spec_id"):
        meta.append(f"- **spec_id**: {payload['spec_id']}")
    if payload.get("generated_at"):
        meta.append(f"- **generated_at**: {payload['generated_at']}")
    if payload.get("country", {}).get("name"):
        c = payload["country"]
        meta.append(f"- **country**: {c.get('name')}{' (' + c.get('iso3') + ')' if c.get('iso3') else ''}")
    header = title + ("\n".join(meta) + "\n\n" if meta else "\n")

    if job_id == "phase1_discovery_qa":
        out = [header, "## Questions\n"]
        for q in payload.get("questions", []):
            out.append(f"### {q.get('question_id', '')}\n")
            out.append(f"**Q:** {_md_escape(q.get('question',''))}\n\n")
            out.append(f"**A:** {_md_escape(q.get('answer',''))}\n\n")
            ev = q.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
        return "".join(out).strip() + "\n"

    if job_id == "rrr_evidence_matrix":
        out = [header, "## Solutions\n\n"]
        for s in payload.get("solutions", []):
            out.append(f"### {s.get('solution_id','')}: {_md_escape(s.get('solution',''))}\n\n")
            out.append(f"**Mechanism:** {_md_escape(s.get('mechanism',''))}\n\n")
            out.append(f"**Feasibility (resource-constrained):** {s.get('feasibility_resource_constrained','')}\n\n")
            if s.get("risks"):
                out.append("**Risks:** " + "; ".join(s["risks"]) + "\n\n")
            if s.get("implementation_notes"):
                out.append(f"**Implementation notes:** {_md_escape(s.get('implementation_notes',''))}\n\n")
            ev = s.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
        return "".join(out).strip() + "\n"

    if job_id == "table2_root_cause_mapping":
        out = [header, "## Framework items\n\n"]
        for it in payload.get("framework_items", []):
            out.append(f"### {it.get('item_id','')}: {_md_escape(it.get('root_cause',''))}\n\n")
            out.append(f"- **Category:** {_md_escape(it.get('category',''))}\n")
            out.append(f"- **Definition:** {_md_escape(it.get('definition',''))}\n\n")
            ev = it.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
        return "".join(out).strip() + "\n"

    if job_id == "table3_intervention_framework":
        out = [header, "## Interventions\n\n"]
        for it in payload.get("interventions", []):
            out.append(f"### {it.get('intervention_id','')}: {_md_escape(it.get('intervention',''))}\n\n")
            out.append(f"- **Lever:** {_md_escape(it.get('lever',''))}\n")
            out.append(f"- **Mechanism:** {_md_escape(it.get('mechanism',''))}\n\n")
            if it.get("dependencies"):
                out.append("**Dependencies:** " + "; ".join(it["dependencies"]) + "\n\n")
            if it.get("risks"):
                out.append("**Risks:** " + "; ".join(it["risks"]) + "\n\n")
            if it.get("implementation_notes"):
                out.append(f"**Implementation notes:** {_md_escape(it.get('implementation_notes',''))}\n\n")
            ev = it.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
        return "".join(out).strip() + "\n"

    if job_id == "benchmark_country_scoring":
        out = [header, "## Countries\n\n"]
        for c in payload.get("countries", []):
            out.append(f"### {_md_escape(c.get('country_name',''))} ({c.get('iso3','')})\n\n")
            overall = c.get("overall_score", {})
            out.append(f"**Overall score:** {overall.get('score','')}\n\n")
            ev = overall.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
            out.append("#### Dimensions\n\n")
            for d in c.get("dimensions", []):
                sn = d.get("score_note", {})
                out.append(f"- **{_md_escape(d.get('label',''))}** ({d.get('dimension_id','')}): {sn.get('score','')}\n")
                dev = sn.get("evidence", {})
                out.append(f"  - quality: {dev.get('quality','')}\n")
                out.append(f"  - rationale: {_md_escape(dev.get('rationale',''))}\n")
            out.append("\n")
        return "".join(out).strip() + "\n"

    if job_id == "country_learning_briefs":
        out = [header, "## Learning domains\n\n"]
        for d in payload.get("domains", []):
            out.append(f"### {d.get('domain_id','')}: {_md_escape(d.get('domain',''))}\n\n")
            out.append(f"**Summary:** {_md_escape(d.get('summary',''))}\n\n")
            out.append("**Key questions:**\n")
            for q in d.get("key_questions", []):
                out.append(f"- {_md_escape(q)}\n")
            out.append("\n")
            ev = d.get("evidence", {})
            out.append(f"**Evidence quality:** {ev.get('quality','')}\n\n")
            out.append(f"**Rationale:** {_md_escape(ev.get('rationale',''))}\n\n")
            out.append(_render_citations(ev.get("citations", [])) + "\n\n")
        return "".join(out).strip() + "\n"

    raise KeyError(f"render_markdown: unsupported job_id '{job_id}'")


def render_md_file(job_id: str, input_json_path: str, output_md_path: Optional[str] = None) -> Path:
    inp = Path(input_json_path).resolve()
    if not inp.exists():
        raise FileNotFoundError(f"Input file not found: {inp}")
    payload = _read_json(inp)
    md = render_markdown(job_id, payload)
    out = Path(output_md_path).resolve() if output_md_path else inp.with_suffix(".md")
    out.write_text(md, encoding="utf-8")
    return out
