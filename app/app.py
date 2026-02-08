from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.core.validators import SchemaValidationError, validate_output
from app.jobs.executor import run_job_stub
from app.jobs.registry import get_job, load_registry
from app.render.md import render_md_file
from app.render.xlsx import render_xlsx_file
from app.render.docx import render_docx_file
from app.utils import auto_output_name


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read JSON file '{path}': {e}") from e


def cmd_validate(args: argparse.Namespace) -> int:
    job = get_job(args.job)
    file_path = Path(args.file).resolve()

    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 2

    payload = _read_json(file_path)

    try:
        schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    except Exception:
        schema_rel = str(job.output_schema)

    try:
        validate_output(payload, schema_rel)
        print("VALID ✅")
        return 0
    except SchemaValidationError as e:
        print(str(e), file=sys.stderr)
        return 3


def cmd_run(args: argparse.Namespace) -> int:
    if args.mode == "stub":
        res = run_job_stub(
            job_id=args.job,
            spec_id=args.spec_id,
            country_name=getattr(args, "country_name", None),
            country_iso3=getattr(args, "country_iso3", None),
        )
        print(f"Wrote: {res.output_path}")

        job = get_job(args.job)
        try:
            schema_rel = str(job.output_schema.relative_to(Path.cwd()))
        except Exception:
            schema_rel = str(job.output_schema)

        payload = _read_json(res.output_path)
        validate_output(payload, schema_rel)
        print("VALID ✅")
        return 0

    if args.mode == "llm":
        from app.analyze.llm import LLMNotConfigured, generate_json
        from app.analyze.prompting import render_prompt_for_job
        import json as _json

        job = get_job(args.job)

        # Extract allowed source IDs if sources provided
        sources_path = getattr(args, "sources", None)
        if sources_path:
            try:
                sources_data = _read_json(Path(sources_path))
                allowed_ids = [src.get("source_id") for src in sources_data.get("sources", []) if src.get("source_id")]
                if allowed_ids:
                    os.environ["HRH_ALLOWED_SOURCE_IDS"] = ",".join(allowed_ids)
                    os.environ["HRH_ENFORCE_ALLOWED_SOURCES"] = "1"
            except Exception as e:
                print(f"Warning: Could not load sources for validation: {e}", file=sys.stderr)

        try:
            rendered_prompt = render_prompt_for_job(
                job_id=args.job,
                template_path=str(job.prompt_template),
                spec_path=str(job.spec_file),
                spec_id=args.spec_id,
                country_name=getattr(args, "country_name", None),
                country_iso3=getattr(args, "country_iso3", None),
                sources_path=sources_path,
            )
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2

        try:
            schema_rel = str(job.output_schema.relative_to(Path.cwd()))
        except Exception:
            schema_rel = str(job.output_schema)

        job.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate auto-named JSON output with timestamp and country
        out_filename = auto_output_name(
            job.output_dir,
            "json",
            mode="llm",
            country_name=getattr(args, "country_name", None),
            country_iso3=getattr(args, "country_iso3", None),
        )
        out_path = Path(out_filename)

        max_attempts = 3  # initial + 2 repairs
        repair_notes = None

        for attempt in range(1, max_attempts + 1):
            try:
                llm = generate_json(rendered_prompt, repair_instructions=repair_notes)
            except LLMNotConfigured as e:
                print(str(e), file=sys.stderr)
                return 2

            try:
                payload = _json.loads(llm.text)
            except Exception as e:
                repair_notes = f"Your output was not valid JSON. Error: {e}"
                if attempt == max_attempts:
                    print(repair_notes, file=sys.stderr)
                    return 3
                continue

            out_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            try:
                validate_output(payload, schema_rel)
                print(f"Wrote: {out_path}")
                print("VALID ✅")
                return 0
            except Exception as e:
                repair_notes = str(e)
                if attempt == max_attempts:
                    print(repair_notes, file=sys.stderr)
                    print(f"Wrote (invalid): {out_path}", file=sys.stderr)
                    return 3
                continue

    print(f"Unknown mode: {args.mode}", file=sys.stderr)
    return 2


def cmd_run_all(args: argparse.Namespace) -> int:
    """Run all jobs from the registry with the same mode and parameters."""
    registry = load_registry()

    results = []
    sources_path = getattr(args, "sources", None)
    country_name = getattr(args, "country_name", None)
    country_iso3 = getattr(args, "country_iso3", None)

    print(f"Running {len(registry.jobs)} job(s) in {args.mode} mode...")
    print()

    for job_id, job_def in registry.jobs.items():
        print(f"[{job_id}] Starting...")

        # Create a mock args namespace for this job
        # Use provided spec_id or default to job_id
        spec_id = getattr(args, "spec_id", None) or job_id

        job_args = argparse.Namespace(
            job=job_id,
            mode=args.mode,
            spec_id=spec_id,
            country_name=country_name,
            country_iso3=country_iso3,
            sources=sources_path,
        )

        try:
            result = cmd_run(job_args)
            if result == 0:
                print(f"[{job_id}] VALID ✅")
                results.append((job_id, "SUCCESS"))
            else:
                print(f"[{job_id}] FAILED ❌ (exit code: {result})")
                results.append((job_id, f"FAILED (code {result})"))
        except Exception as e:
            print(f"[{job_id}] ERROR ❌: {e}")
            results.append((job_id, f"ERROR: {str(e)[:50]}"))

        print()

    # Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for job_id, status in results:
        icon = "✅" if status == "SUCCESS" else "❌"
        print(f"{icon} {job_id}: {status}")

    # Return 0 if all succeeded, 1 if any failed
    failed_count = sum(1 for _, status in results if status != "SUCCESS")
    return 1 if failed_count > 0 else 0


def cmd_render_all(args: argparse.Namespace) -> int:
    """Render deliverables (md/xlsx/docx) for all jobs from existing outputs."""
    registry = load_registry()
    mode = args.mode
    pattern = f"output_{mode}*.json"

    country_name = getattr(args, "country_name", None)
    country_iso3 = getattr(args, "country_iso3", None)

    print(f"Rendering deliverables for {len(registry.jobs)} job(s) from {pattern} files...")
    print()

    results = []

    for job_id, job_def in registry.jobs.items():
        print(f"[{job_id}] Starting...")

        # Find most recent matching JSON file
        matching_files = sorted(job_def.output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

        if not matching_files:
            print(f"[{job_id}] SKIP: no {pattern} files found in {job_def.output_dir}")
            results.append((job_id, "SKIP"))
            print()
            continue

        input_file = matching_files[0]  # Use most recent
        print(f"[{job_id}] Using: {input_file.name}")

        try:
            # Narrative jobs -> MD + DOCX
            if job_id in ("phase1_discovery_qa", "country_learning_briefs"):
                # Generate auto-named outputs with timestamps
                md_out = auto_output_name(str(input_file), "md", country_name, country_iso3)
                docx_out = auto_output_name(str(input_file), "docx", country_name, country_iso3)

                md_path = render_md_file(job_id, str(input_file), md_out)
                docx_path = render_docx_file(job_id, str(input_file), docx_out)
                print(f"[{job_id}] Wrote: {md_path}")
                print(f"[{job_id}] Wrote: {docx_path}")

            # Table jobs -> MD + XLSX
            elif job_id in (
                "rrr_evidence_matrix",
                "table2_root_cause_mapping",
                "table3_intervention_framework",
                "benchmark_country_scoring",
            ):
                # Generate auto-named outputs with timestamps
                md_out = auto_output_name(str(input_file), "md", country_name, country_iso3)
                xlsx_out = auto_output_name(str(input_file), "xlsx", country_name, country_iso3)

                md_path = render_md_file(job_id, str(input_file), md_out)
                xlsx_path = render_xlsx_file(job_id, str(input_file), xlsx_out)
                print(f"[{job_id}] Wrote: {md_path}")
                print(f"[{job_id}] Wrote: {xlsx_path}")

            else:
                print(f"[{job_id}] SKIP: no renderer mapping")
                results.append((job_id, "SKIP"))
                print()
                continue

            print(f"[{job_id}] DONE OK")
            results.append((job_id, "SUCCESS"))

        except Exception as e:
            print(f"[{job_id}] ERROR: {e}")
            results.append((job_id, f"ERROR: {str(e)[:50]}"))

        print()

    # Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for job_id, status in results:
        if status == "SUCCESS":
            print(f"[OK] {job_id}: {status}")
        elif status == "SKIP":
            print(f"[SKIP] {job_id}: {status}")
        else:
            print(f"[ERROR] {job_id}: {status}")

    # Return 0 if all succeeded, 1 if any failed/skipped
    failed_count = sum(1 for _, status in results if status != "SUCCESS")
    return 1 if failed_count > 0 else 0


def cmd_sources_scan(args: argparse.Namespace) -> int:
    iso3 = args.country_iso3.upper()
    sources_dir = Path("data/sources").resolve()

    # Scan directories
    pdf_dir = sources_dir / iso3 / "pdf"
    docx_dir = sources_dir / iso3 / "docx"

    sources = []
    source_counter = 1

    # Scan PDF files
    if pdf_dir.exists():
        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            source_title = pdf_file.stem  # filename without extension
            rel_path = pdf_file.relative_to(Path.cwd().resolve())
            sources.append({
                "source_id": f"SRC{source_counter}",
                "source_title": source_title,
                "source_type": "pdf",
                "file_path": str(rel_path).replace("\\", "/"),
                "reference": f"{source_title} (PDF document)",
                "snippets": []
            })
            source_counter += 1

    # Scan DOCX files
    if docx_dir.exists():
        for docx_file in sorted(docx_dir.glob("*.docx")):
            source_title = docx_file.stem
            rel_path = docx_file.relative_to(Path.cwd().resolve())
            sources.append({
                "source_id": f"SRC{source_counter}",
                "source_title": source_title,
                "source_type": "docx",
                "file_path": str(rel_path).replace("\\", "/"),
                "reference": f"{source_title} (DOCX document)",
                "snippets": []
            })
            source_counter += 1

    if not sources:
        print(f"No PDF or DOCX files found in:", file=sys.stderr)
        print(f"  {pdf_dir}", file=sys.stderr)
        print(f"  {docx_dir}", file=sys.stderr)
        return 1

    # Write output JSON
    output_data = {"sources": sources}
    output_file = sources_dir / f"{iso3.lower()}_sources.json"

    sources_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Scanned {len(sources)} file(s)")
    print(f"Wrote: {output_file}")
    return 0


def cmd_render_md(args: argparse.Namespace) -> int:
    """Render markdown with auto-generated output name if --out not provided."""
    out_path = args.out
    if not out_path:
        out_path = auto_output_name(
            args.file,
            "md",
            getattr(args, "country_name", None),
            getattr(args, "country_iso3", None)
        )
    result = render_md_file(args.job, args.file, out_path)
    print(f"Wrote: {result}")
    return 0


def cmd_render_xlsx(args: argparse.Namespace) -> int:
    """Render xlsx with auto-generated output name if --out not provided."""
    out_path = args.out
    if not out_path:
        out_path = auto_output_name(
            args.file,
            "xlsx",
            getattr(args, "country_name", None),
            getattr(args, "country_iso3", None)
        )
    result = render_xlsx_file(args.job, args.file, out_path)
    print(f"Wrote: {result}")
    return 0


def cmd_render_docx(args: argparse.Namespace) -> int:
    """Render docx with auto-generated output name if --out not provided."""
    out_path = args.out
    if not out_path:
        out_path = auto_output_name(
            args.file,
            "docx",
            getattr(args, "country_name", None),
            getattr(args, "country_iso3", None)
        )
    result = render_docx_file(args.job, args.file, out_path)
    print(f"Wrote: {result}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hrh_app")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="Validate an output JSON file against a job schema")
    v.add_argument("--job", required=True, help="Job id (e.g., phase1_discovery_qa)")
    v.add_argument("--file", required=True, help="Path to output JSON file to validate")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="Run a job (stub mode for now)")
    r.add_argument("--job", required=True, help="Job id (e.g., phase1_discovery_qa)")
    r.add_argument("--mode", required=True, choices=["stub", "llm"], help="Execution mode")
    r.add_argument("--spec-id", required=True, help="Spec identifier string to embed in output")
    r.add_argument("--country-name", default=None, help="Country name (Phase 1 only for now)")
    r.add_argument("--country-iso3", default=None, help="ISO3 (Phase 1 only for now)")
    r.add_argument("--sources", default=None, help="Optional path to curated sources JSON file")
    r.set_defaults(func=cmd_run)

    ra = sub.add_parser("run-all", help="Run all jobs from registry in batch")
    ra.add_argument("--mode", required=True, choices=["stub", "llm"], help="Execution mode")
    ra.add_argument("--spec-id", default=None, help="Spec identifier (defaults to job_id for each job)")
    ra.add_argument("--country-name", default=None, help="Country name (for country-specific jobs)")
    ra.add_argument("--country-iso3", default=None, help="ISO3 country code (for country-specific jobs)")
    ra.add_argument("--sources", default=None, help="Optional path to curated sources JSON file")
    ra.set_defaults(func=cmd_run_all)

    ra2 = sub.add_parser("render-all", help="Render deliverables for all jobs (md/xlsx/docx) from existing outputs")
    ra2.add_argument("--mode", required=True, choices=["stub", "llm"], help="Which output files to render (stub or llm)")
    ra2.add_argument("--country-name", default=None, help="Country name (for auto-generated filename)")
    ra2.add_argument("--country-iso3", default=None, help="ISO3 country code (for auto-generated filename)")
    ra2.set_defaults(func=cmd_render_all)

    s = sub.add_parser("sources-scan", help="Scan PDF/DOCX files and generate sources JSON")
    s.add_argument("--country-iso3", required=True, help="ISO3 country code (e.g., ETH, KEN)")
    s.set_defaults(func=cmd_sources_scan)

    m = sub.add_parser("render-md", help="Render a validated output JSON to Markdown")
    m.add_argument("--job", required=True, help="Job id")
    m.add_argument("--file", required=True, help="Path to output JSON file")
    m.add_argument("--out", default=None, help="Optional output .md path (auto-generated if not provided)")
    m.add_argument("--country-name", default=None, help="Country name (for auto-generated filename)")
    m.add_argument("--country-iso3", default=None, help="ISO3 country code (for auto-generated filename)")
    m.set_defaults(func=cmd_render_md)

    x = sub.add_parser("render-xlsx", help="Render a validated output JSON to XLSX (table jobs)")
    x.add_argument("--job", required=True, help="Job id")
    x.add_argument("--file", required=True, help="Path to output JSON file")
    x.add_argument("--out", default=None, help="Optional output .xlsx path (auto-generated if not provided)")
    x.add_argument("--country-name", default=None, help="Country name (for auto-generated filename)")
    x.add_argument("--country-iso3", default=None, help="ISO3 country code (for auto-generated filename)")
    x.set_defaults(func=cmd_render_xlsx)

    d = sub.add_parser("render-docx", help="Render a validated output JSON to DOCX (narrative jobs)")
    d.add_argument("--job", required=True, help="Job id")
    d.add_argument("--file", required=True, help="Path to output JSON file")
    d.add_argument("--out", default=None, help="Optional output .docx path (auto-generated if not provided)")
    d.add_argument("--country-name", default=None, help="Country name (for auto-generated filename)")
    d.add_argument("--country-iso3", default=None, help="ISO3 country code (for auto-generated filename)")
    d.set_defaults(func=cmd_render_docx)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
