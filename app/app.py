from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path

# pdfminer emits "CropBox missing from /Page, defaulting to MediaBox" for many
# PDFs that omit the optional CropBox key. This is harmless — extraction is
# unaffected — so suppress it to keep scan output readable.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

from app.core.validators import SchemaValidationError, validate_output
from app.jobs.executor import run_job_stub
from app.jobs.registry import get_job, load_registry
from app.render.md import render_md_file
from app.render.xlsx import render_xlsx_file
from app.render.docx import render_docx_file
from app.ingest.loader import extract_pdf, extract_docx
from app.ingest.chunker import chunk_snippets
from app.ingest.indexer import build_index, load_index
from app.utils import auto_output_name


_GENERIC_MECHANISM_PHRASES = ("to be determined", "placeholder", "tbd")


def _build_rrr_query(solution: str, mechanism: str) -> str:
    """Build a RAG retrieval query for an RRR solution item.

    If mechanism is empty or contains generic/placeholder text, use only the
    solution name so the embedding search isn't polluted by filler words.
    """
    mech = (mechanism or "").strip().lower()
    if not mech or any(phrase in mech for phrase in _GENERIC_MECHANISM_PHRASES):
        return solution
    return f"{solution} — {mechanism}"


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
        print("VALID [OK]")
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
        print("VALID [OK]")
        return 0

    if args.mode == "llm":
        from app.analyze.llm import LLMNotConfigured, generate_json
        from app.analyze.prompting import render_prompt_for_job, render_prompt_with_rag
        from app.analyze.merger import merge_outputs
        from app.analyze.extractors import (
            extract_phase1_questions,
            extract_rrr_solutions,
            extract_table2_items,
            extract_table3_items,
            extract_learning_domains,
            extract_benchmark_dimensions_countries,
        )
        import json as _json
        import tempfile
        import time

        job = get_job(args.job)
        sources_path = getattr(args, "sources", None)
        index_path = getattr(args, "index", None)
        no_split = getattr(args, "no_split", False)

        # Load sources and set up allowed-IDs for validation
        all_sources: list[dict] = []
        if sources_path:
            try:
                sources_data = _read_json(Path(sources_path))
                all_sources = sources_data.get("sources", [])
                # domain_solutions_from_evidence uses doc_id (not source_id) in LocalCitation,
                # so source_id enforcement does not apply and would always fail validation.
                if args.job != "domain_solutions_from_evidence":
                    allowed_ids = [src.get("source_id") for src in all_sources if src.get("source_id")]
                    if allowed_ids:
                        os.environ["HRH_ALLOWED_SOURCE_IDS"] = ",".join(allowed_ids)
                        os.environ["HRH_ENFORCE_ALLOWED_SOURCES"] = "1"
            except Exception as e:
                print(f"Warning: Could not load sources for validation: {e}", file=sys.stderr)

        try:
            schema_rel = str(job.output_schema.relative_to(Path.cwd()))
        except Exception:
            schema_rel = str(job.output_schema)

        job.output_dir.mkdir(parents=True, exist_ok=True)
        out_filename = auto_output_name(
            job.output_dir, "json", mode="llm",
            country_name=getattr(args, "country_name", None),
            country_iso3=getattr(args, "country_iso3", None),
        )
        out_path = Path(out_filename)

        # ── RAG mode: per-question/item retrieval ──────────────────────
        if index_path:
            print(f"  RAG mode: loading index from {index_path}")
            index_data = load_index(index_path)
            print(f"  Index has {index_data.get('snippet_count', '?')} snippets")

            # Build hybrid retriever (vector + BM25) for better accuracy
            from app.ingest.indexer import build_retriever as _build_retriever
            _rag_retriever = _build_retriever(index_data, api_key=os.getenv("OPENAI_API_KEY", ""))
            print("  Hybrid retriever ready (vector + BM25 + RRF + MMR)")

            spec = _read_json(Path(str(job.spec_file)))
            top_k = int(os.getenv("HRH_RAG_TOP_K", "40"))
            country_name = getattr(args, "country_name", None)
            country_iso3 = getattr(args, "country_iso3", None)

            # Extract items to iterate over based on job type
            items_with_queries = _extract_rag_items(
                args.job, spec, country_name, country_iso3
            )

            print(f"  Processing {len(items_with_queries)} items via RAG...")
            all_item_results: list[dict] = []

            for item_idx, (query_text, item_inputs) in enumerate(items_with_queries, 1):
                item_label = query_text[:60].replace("\n", " ")
                print(f"  [{item_idx}/{len(items_with_queries)}] {item_label}...")

                rendered_prompt = render_prompt_with_rag(
                    job_id=args.job,
                    template_path=str(job.prompt_template),
                    spec_path=str(job.spec_file),
                    spec_id=args.spec_id,
                    query_text=query_text,
                    index_data=index_data,
                    top_k=top_k,
                    country_name=country_name,
                    country_iso3=country_iso3,
                    item_inputs=item_inputs,
                    retriever=_rag_retriever,
                )

                # LLM call — skip per-item schema validation (partial output won't
                # match the full schema; only the merged result is validated)
                payload = _llm_call_with_retry(
                    rendered_prompt, generate_json, LLMNotConfigured, _json, job_id=args.job
                )
                if payload is None:
                    print(f"  Warning: no valid output for item {item_idx}", file=sys.stderr)
                    continue

                all_item_results.append(_clean_citations(payload))

            if not all_item_results:
                print("No valid outputs produced.", file=sys.stderr)
                return 3

            # Merge all per-item results into a single output
            if len(all_item_results) == 1:
                final_payload = all_item_results[0]
            else:
                try:
                    final_payload = merge_outputs(args.job, all_item_results)
                except Exception as e:
                    print(f"Merge failed: {e}", file=sys.stderr)
                    return 3

            _stamp_run_date(args.job, final_payload)
            _log_coverage_warnings(args.job, final_payload, all_sources)
            out_path.write_text(
                _json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            try:
                validate_output(final_payload, schema_rel)
                if args.job == "domain_solutions_from_evidence" and all_sources:
                    _validate_snippet_verbatim(final_payload, all_sources)
                print(f"Wrote: {out_path}")
                print("VALID [OK]")
                return 0
            except Exception as e:
                print(str(e), file=sys.stderr)
                print(f"Wrote (invalid): {out_path}", file=sys.stderr)
                return 3

        # ── Legacy mode: per-source splitting ──────────────────────────
        # Determine source batches: per-source or single call
        sources_with_snippets = [s for s in all_sources if s.get("snippets")]
        sources_without_snippets = [s for s in all_sources if not s.get("snippets")]

        if not sources_path or no_split or len(sources_with_snippets) <= 1:
            # Single-call mode (original behavior)
            source_batches = [all_sources] if all_sources else [None]
        else:
            # Per-source mode: one batch per source that has snippets
            source_batches = [[src] + sources_without_snippets for src in sources_with_snippets]

        # Snippet sub-batching: for domain_lessons_option_b each source batch is
        # split into smaller calls so the LLM sees a manageable excerpt payload.
        _max_excerpts = int(os.getenv("HRH_MAX_EXCERPTS_PER_CALL", "5"))
        _max_chars = int(os.getenv("HRH_MAX_CHARS_PER_CALL", "16000"))
        source_batches = _expand_source_batches_for_job(
            args.job, source_batches, _max_excerpts, _max_chars
        )

        partial_outputs: list[dict] = []
        total_batches = len(source_batches)

        for batch_idx, batch in enumerate(source_batches, start=1):
            if batch and total_batches > 1:
                src_name = batch[0].get("source_title", "unknown")[:50]
                print(f"  Source {batch_idx}/{total_batches}: {src_name}")

            # Write temporary sources file for this batch
            tmp_sources_path = None
            if batch is not None:
                tmp_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                )
                _json.dump({"sources": batch}, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.close()
                tmp_sources_path = tmp_file.name

            try:
                rendered_prompt = render_prompt_for_job(
                    job_id=args.job,
                    template_path=str(job.prompt_template),
                    spec_path=str(job.spec_file),
                    spec_id=args.spec_id,
                    country_name=getattr(args, "country_name", None),
                    country_iso3=getattr(args, "country_iso3", None),
                    sources_path=tmp_sources_path or sources_path,
                )
            except Exception as e:
                print(str(e), file=sys.stderr)
                return 2
            finally:
                if tmp_sources_path:
                    Path(tmp_sources_path).unlink(missing_ok=True)

            payload = _llm_call_with_retry(
                rendered_prompt, generate_json, LLMNotConfigured, _json, schema_rel, job_id=args.job
            )
            if payload is None:
                print(f"  Warning: no valid output for batch {batch_idx}", file=sys.stderr)
            else:
                partial_outputs.append(payload)


        if not partial_outputs:
            print("No valid outputs produced.", file=sys.stderr)
            return 3

        # Merge if multiple partial outputs
        if len(partial_outputs) == 1:
            final_payload = partial_outputs[0]
        else:
            try:
                final_payload = merge_outputs(args.job, partial_outputs)
            except Exception as e:
                print(f"Merge failed: {e}", file=sys.stderr)
                return 3

        _stamp_run_date(args.job, final_payload)
        _log_coverage_warnings(args.job, final_payload, all_sources)
        out_path.write_text(
            _json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        try:
            validate_output(final_payload, schema_rel)
            if args.job == "domain_solutions_from_evidence" and all_sources:
                _validate_snippet_verbatim(final_payload, all_sources)
            print(f"Wrote: {out_path}")
            print("VALID [OK]")
            return 0
        except Exception as e:
            print(str(e), file=sys.stderr)
            print(f"Wrote (invalid): {out_path}", file=sys.stderr)
            return 3

    elif args.mode == "llm_planned":
        if args.job != "domain_lessons_option_b":
            print(
                f"--mode llm_planned is only supported for domain_lessons_option_b (got {args.job!r})",
                file=sys.stderr,
            )
            return 1
        sources_path = getattr(args, "sources", None)
        if not sources_path:
            print("--mode llm_planned requires --sources", file=sys.stderr)
            return 1

        from app.analyze.llm import LLMNotConfigured, generate_json
        from app.analyze.merger import merge_outputs
        from app.analyze.prompting import render_prompt_for_job
        import json as _json
        import tempfile
        import time

        job = get_job(args.job)
        try:
            schema_rel = str(job.output_schema.relative_to(Path.cwd()))
        except Exception:
            schema_rel = str(job.output_schema)

        all_sources: list[dict] = []
        try:
            sources_data = _read_json(Path(sources_path))
            all_sources = sources_data.get("sources", [])
        except Exception as e:
            print(f"Could not load sources: {e}", file=sys.stderr)
            return 2

        job.output_dir.mkdir(parents=True, exist_ok=True)
        out_filename = auto_output_name(
            job.output_dir, "json", mode="llm_planned",
            country_name=getattr(args, "country_name", None),
            country_iso3=getattr(args, "country_iso3", None),
        )
        out_path = Path(out_filename)

        planner_job = get_job("domain_lessons_planner")
        try:
            planner_schema_rel = str(planner_job.output_schema.relative_to(Path.cwd()))
        except Exception:
            planner_schema_rel = str(planner_job.output_schema)

        sources_by_id = {s.get("source_id", s.get("doc_id", "")): s for s in all_sources}
        sources_with_snippets = [s for s in all_sources if s.get("snippets")]
        # ── Stage 1: Planner pass ──────────────────────────────────────────────
        print(f"  Planner pass: {len(sources_with_snippets)} source(s)...")
        all_plans: list[dict] = []

        for src_idx, src in enumerate(sources_with_snippets, 1):
            src_id = src.get("source_id", src.get("doc_id", f"src_{src_idx}"))
            print(f"  [{src_idx}/{len(sources_with_snippets)}] Planning {src_id!r}...")

            planner_payload = _llm_call_with_retry(
                _build_planner_prompt(src, str(planner_job.prompt_template)),
                generate_json, LLMNotConfigured, _json,
                planner_schema_rel, job_id="domain_lessons_planner",
                label=f"planner source_id={src_id!r} title={src.get('source_title','')[:60]!r}",
            )
            if planner_payload is None:
                print(f"  Warning: planner returned no output for {src_id!r}", file=sys.stderr)
                continue

            _stamp_run_date("domain_lessons_planner", planner_payload)

            for err in _check_planner_locators(planner_payload, sources_by_id):
                print(f"  [PLANNER WARNING] {err}", file=sys.stderr)

            all_plans.extend(planner_payload.get("plans", []))

        if not all_plans:
            print("No plans produced by planner.", file=sys.stderr)
            return 3

        # ── Stage 1.5: Deterministic keyword coverage enforcement ──────────────
        # Scans full snippet text for each source and adds any uncovered locators
        # that contain keyword-family hits to the planner plans. This removes
        # dependence on the planner LLM faithfully following keyword scan rules.
        all_plans = _enforce_planner_keyword_coverage(all_plans, sources_by_id)

        # ── Stage 2: Targeted extraction ──────────────────────────────────────
        # Default is 10 (higher than the non-planned llm mode) because
        # _planner_to_batches now groups all selected locators per source;
        # more excerpts per call means the extractor sees fuller context.
        _max_excerpts = int(os.getenv("HRH_MAX_EXCERPTS_PER_CALL", "10"))
        _max_chars = int(os.getenv("HRH_MAX_CHARS_PER_CALL", "16000"))
        _max_batches_per_source = int(os.getenv("HRH_MAX_EXTRACT_BATCHES_PER_SOURCE", "10"))
        _max_delta_per_source = int(os.getenv("HRH_MAX_DELTA_CALLS_PER_SOURCE", "6"))
        extraction_batches = _planner_to_batches(
            all_plans, sources_by_id, _max_excerpts, _max_chars, _max_batches_per_source
        )
        if not extraction_batches:
            print("No extraction batches from planner output.", file=sys.stderr)
            return 3

        print(f"  Extraction pass: {len(extraction_batches)} batch(es)...")
        partial_outputs: list[dict] = []
        _delta_calls_used: dict[str, int] = {}  # source_id → delta calls consumed
        _batch_durations: list[float] = []

        for batch_idx, batch in enumerate(extraction_batches, 1):
            src_name = (batch[0].get("source_title", "unknown")[:50] if batch else "unknown")
            _batch_source_id = batch[0].get("source_id", "") if batch else ""
            batch_locators = [
                snip.get("locator", "")
                for src in batch
                for snip in src.get("snippets", [])
            ]
            print(f"  Batch {batch_idx}/{len(extraction_batches)}: {src_name} ({len(batch_locators)} locators: {batch_locators})")
            _batch_start = time.perf_counter()

            tmp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            _json.dump({"sources": batch}, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.close()
            tmp_sources_path = tmp_file.name

            try:
                rendered_prompt = render_prompt_for_job(
                    job_id=args.job,
                    template_path=str(job.prompt_template),
                    spec_path=str(job.spec_file),
                    spec_id=args.spec_id,
                    country_name=getattr(args, "country_name", None),
                    country_iso3=getattr(args, "country_iso3", None),
                    sources_path=tmp_sources_path,
                )
            except Exception as e:
                print(str(e), file=sys.stderr)
                return 2
            finally:
                Path(tmp_sources_path).unlink(missing_ok=True)

            payload = _llm_call_with_retry(
                rendered_prompt, generate_json, LLMNotConfigured, _json,
                schema_rel, job_id=args.job,
                label=f"extractor batch {batch_idx}: {src_name} locators={batch_locators}",
            )

            batch_payloads: list[dict] = []
            _batch_doc_ids = {
                src.get("source_id", src.get("doc_id", "")) for src in batch
            }

            if payload is None:
                print(f"  Warning: no valid output for batch {batch_idx}", file=sys.stderr)
            else:
                batch_payloads.append(payload)

                # ── Coverage check: decide expansion vs delta ───────────────
                _n_cited = len(_cited_locators_set(batch_payloads, _batch_doc_ids))
                print(f"  [COVERAGE] batch {batch_idx}: {_n_cited}/{len(batch_locators)} locators cited after extraction")
                _delta_threshold = min(5, math.ceil(len(batch_locators) * 0.5)) if batch_locators else 0
                _skip_exp = _skip_expansion_when_delta_enabled() and _n_cited < _delta_threshold

                # ── Expansion pass (skipped when delta is scheduled) ─────────
                if _skip_exp:
                    print(
                        f"  [EXPANSION] batch {batch_idx}: skipped — delta will run "
                        f"(cited={_n_cited} < threshold={_delta_threshold}, HRH_SKIP_EXPANSION_WHEN_DELTA=1)"
                    )
                elif _n_cited < 5 and len(batch_locators) >= 8:
                    print(
                        f"  [EXPANSION] batch {batch_idx}: {_n_cited} cited / "
                        f"{len(batch_locators)} available — running expansion sweep..."
                    )
                    exp_payload = _llm_call_with_retry(
                        rendered_prompt + _EXPANSION_SUFFIX,
                        generate_json, LLMNotConfigured, _json,
                        schema_rel, job_id=args.job,
                        label=f"expansion batch {batch_idx}",
                    )
                    if exp_payload is not None:
                        batch_payloads.append(exp_payload)

                # ── Locator Delta Sweep (grouped, keyword-prioritised) ───────
                _n_cited_post = len(_cited_locators_set(batch_payloads, _batch_doc_ids))
                print(f"  [COVERAGE] batch {batch_idx}: {_n_cited_post}/{len(batch_locators)} locators cited after expansion")
                if batch_locators and _n_cited_post < _delta_threshold:
                    _cited_before_delta = _cited_locators_set(batch_payloads, _batch_doc_ids)
                    _uncited = [loc for loc in batch_locators if loc and loc not in _cited_before_delta]
                    _uncited_ranked = _rank_locators_by_keyword(_uncited, batch)

                    # Fix B: skip entirely if no uncited locator has any keyword hit.
                    # Since _rank_locators_by_keyword sorts by hit count desc, checking
                    # only the top locator is sufficient.
                    _all_kws: tuple[str, ...] = tuple(
                        kw for kws in _PLANNER_KEYWORD_FAMILIES.values() for kw in kws
                    )
                    _locator_text: dict[str, str] = {
                        snip.get("locator", ""): snip.get("text", "").lower()
                        for src in batch
                        for snip in src.get("snippets", [])
                        if snip.get("locator")
                    }
                    _has_hits = bool(_uncited_ranked) and any(
                        kw in _locator_text.get(_uncited_ranked[0], "") for kw in _all_kws
                    )

                    if not _has_hits:
                        print(f"  [DELTA SWEEP] batch {batch_idx}: skipped — no keyword-hit uncited locators")
                    else:
                        # Group into _DELTA_GROUP_SIZE chunks; cap by batch AND per-source budget
                        _used = _delta_calls_used.get(_batch_source_id, 0)
                        _remaining = max(0, _max_delta_per_source - _used)
                        print(
                            f"  [DELTA BUDGET] source={_batch_source_id!r} "
                            f"used={_used}/{_max_delta_per_source} remaining={_remaining}"
                        )
                        if _remaining == 0:
                            print(f"  [DELTA SWEEP] batch {batch_idx}: skipped — per-source budget exhausted")
                        else:
                            _allowed = min(_MAX_DELTA_CALLS_PER_BATCH, _remaining)
                            _max_sweep = _DELTA_GROUP_SIZE * _allowed
                            _to_sweep = _uncited_ranked[:_max_sweep]
                            _groups = [
                                _to_sweep[i:i + _DELTA_GROUP_SIZE]
                                for i in range(0, len(_to_sweep), _DELTA_GROUP_SIZE)
                            ]
                            _groups = _groups[:_allowed]
                        print(
                            f"  [DELTA SWEEP] batch {batch_idx}: uncited={len(_uncited)}, "
                            f"groups={len(_groups)}, running=min({len(_groups)}, {_allowed})"
                        ) if _remaining > 0 else None
                        _delta_new_items = 0
                        _delta_new_locs: set[str] = set()
                        if _remaining == 0:
                            _groups = []
                        for grp_idx, group_locs in enumerate(_groups):
                            print(f"  [DELTA GROUP] locators={group_locs}")
                            # Build mini-sources: one entry per unique source, only this group's snippets
                            _mini_src_map: dict = {}
                            for loc in group_locs:
                                for src in batch:
                                    for snip in src.get("snippets", []):
                                        if snip.get("locator") == loc:
                                            src_id = src.get("source_id", src.get("doc_id", str(id(src))))
                                            if src_id not in _mini_src_map:
                                                _mini_src_map[src_id] = {**src, "snippets": []}
                                            _mini_src_map[src_id]["snippets"].append(snip)
                                            break
                            if not _mini_src_map:
                                continue
                            delta_tmp = tempfile.NamedTemporaryFile(
                                mode="w", suffix=".json", delete=False, encoding="utf-8"
                            )
                            _json.dump(
                                {"sources": list(_mini_src_map.values())},
                                delta_tmp, ensure_ascii=False, indent=2,
                            )
                            delta_tmp.close()
                            try:
                                delta_rendered = render_prompt_for_job(
                                    job_id=args.job,
                                    template_path=str(job.prompt_template),
                                    spec_path=str(job.spec_file),
                                    spec_id=args.spec_id,
                                    country_name=getattr(args, "country_name", None),
                                    country_iso3=getattr(args, "country_iso3", None),
                                    sources_path=delta_tmp.name,
                                )
                            except Exception as e:
                                print(f"  [DELTA GROUP] render failed for group {group_locs!r}: {e}", file=sys.stderr)
                                continue
                            finally:
                                Path(delta_tmp.name).unlink(missing_ok=True)
                            delta_payload = _llm_call_with_retry(
                                delta_rendered + _DELTA_GROUP_SUFFIX,
                                generate_json, LLMNotConfigured, _json,
                                schema_rel, job_id=args.job,
                                label=f"delta batch {batch_idx} group={group_locs}",
                            )
                            _delta_calls_used[_batch_source_id] = _delta_calls_used.get(_batch_source_id, 0) + 1
                            if delta_payload is not None:
                                _before = _cited_locators_set(batch_payloads, _batch_doc_ids)
                                batch_payloads.append(delta_payload)
                                _after = _cited_locators_set(batch_payloads, _batch_doc_ids)
                                _delta_new_locs |= (_after - _before)
                                _delta_new_items += sum(
                                    1
                                    for domain in delta_payload.get("domains", [])
                                    for fa in domain.get("focus_areas", [])
                                    for cat in _DOMAIN_LESSONS_CATEGORIES
                                    for item in fa.get(cat, [])
                                    if item.get("citations")
                                )
                        print(
                            f"  [DELTA SWEEP] batch {batch_idx}: added_items={_delta_new_items}; "
                            f"newly_cited={sorted(_delta_new_locs)}"
                        )
                _n_final = len(_cited_locators_set(batch_payloads, _batch_doc_ids))
                print(f"  [COVERAGE] batch {batch_idx}: {_n_final}/{len(batch_locators)} locators cited FINAL")

            partial_outputs.extend(batch_payloads)

            _batch_dur = time.perf_counter() - _batch_start
            _batch_durations.append(_batch_dur)
            _avg_dur = sum(_batch_durations) / len(_batch_durations)
            _remaining_batches = len(extraction_batches) - batch_idx
            print(
                f"  [BATCH TIME] batch {batch_idx}/{len(extraction_batches)} "
                f"source={src_name!r} locators={len(batch_locators)} "
                f"duration={_batch_dur:.1f}s (avg={_avg_dur:.1f}s)"
            )
            if _remaining_batches > 0:
                _eta_s = _avg_dur * _remaining_batches
                print(
                    f"  [ETA] remaining_batches={_remaining_batches} "
                    f"approx_remaining={_eta_s / 60:.1f} min"
                )

        if not partial_outputs:
            print("No valid outputs produced.", file=sys.stderr)
            return 3

        if len(partial_outputs) == 1:
            final_payload = partial_outputs[0]
        else:
            try:
                final_payload = merge_outputs(args.job, partial_outputs)
            except Exception as e:
                print(f"Merge failed: {e}", file=sys.stderr)
                return 3

        _stamp_run_date(args.job, final_payload)
        _log_coverage_warnings(args.job, final_payload, all_sources)
        out_path.write_text(
            _json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        try:
            validate_output(final_payload, schema_rel)
            print(f"Wrote: {out_path}")
            print("VALID [OK]")
            return 0
        except Exception as e:
            print(f"Validation failed: {e}", file=sys.stderr)
            return 4

    print(f"Unknown mode: {args.mode}", file=sys.stderr)
    return 2


def _clean_citations(payload: dict) -> dict:
    """Strip invalid optional fields from citations in LLM output.

    The LLM sometimes emits empty strings, nulls, or malformed values for
    optional citation fields (source_url, published_date, doi, isbn, etc.).
    Removing these prevents schema validation failures while preserving all
    valid data.
    """
    import re
    ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    OPTIONAL_STRING_FIELDS = [
        "source_url", "doi", "isbn", "reference", "authors",
        "publisher", "source_type", "quote",
    ]

    def _clean_citation(cit: dict) -> dict:
        cleaned = {}
        for k, v in cit.items():
            # Drop null values entirely
            if v is None:
                continue
            # Drop empty strings for optional string fields
            if k in OPTIONAL_STRING_FIELDS and isinstance(v, str) and not v.strip():
                continue
            # Validate published_date format
            if k == "published_date":
                if not isinstance(v, str) or not ISO_DATE_RE.match(v):
                    continue
            # Validate source_url is a real URL (not hallucinated)
            if k == "source_url":
                if not isinstance(v, str) or not v.startswith("http"):
                    continue
                if "example.com" in v:
                    continue
            # Enforce snippet ≤ 300 chars to prevent schema validation failures
            if k == "snippet" and isinstance(v, str) and len(v) > 300:
                v = _truncate_at_word_boundary(v, 300)
            cleaned[k] = v
        return cleaned

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "citations" in obj and isinstance(obj["citations"], list):
                obj["citations"] = [_clean_citation(c) for c in obj["citations"]]
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
        return obj

    return _walk(payload)


def _validate_snippet_verbatim(payload: dict, all_sources: list[dict]) -> None:
    """For domain_solutions_from_evidence: verify every citation.snippet appears
    verbatim (as a substring) in the matching source excerpt text.

    Lookup: doc_id → source_id, locator → snippets[].locator → snippets[].text.
    Collects all mismatches before raising so the repair loop sees every error.
    """
    from app.core.validators import SchemaValidationError

    # Build lookup: {source_id: {locator: text}}
    excerpt_map: dict[str, dict[str, str]] = {}
    for src in all_sources:
        sid = src.get("source_id", "")
        if not sid:
            continue
        excerpt_map[sid] = {
            snip.get("locator", ""): snip.get("text", "")
            for snip in src.get("snippets", [])
            if snip.get("locator") and snip.get("text")
        }

    errors: list[str] = []
    for domain in payload.get("domains", []):
        for fa in domain.get("focus_areas", []):
            for sol in fa.get("solutions", []):
                sol_id = sol.get("solution_id", "?")
                for cit in sol.get("citations", []):
                    doc_id = cit.get("doc_id", "")
                    locator = cit.get("locator", "")
                    snippet = cit.get("snippet", "")

                    if doc_id not in excerpt_map:
                        errors.append(
                            f"solution '{sol_id}', doc_id '{doc_id}': "
                            "not found in loaded sources"
                        )
                        continue

                    if locator not in excerpt_map[doc_id]:
                        errors.append(
                            f"solution '{sol_id}', doc_id '{doc_id}', "
                            f"locator '{locator}': not found in source excerpts"
                        )
                        continue

                    source_text = excerpt_map[doc_id][locator]
                    if snippet not in source_text:
                        prefix = snippet[:60].replace("\n", " ")
                        errors.append(
                            f"solution '{sol_id}', doc_id '{doc_id}', "
                            f"locator '{locator}': snippet not found verbatim in source text "
                            f"(snippet prefix: '{prefix}...')"
                        )

    if errors:
        raise SchemaValidationError(
            schema_path="(verbatim snippet check)",
            message="Verbatim snippet validation failed for domain_solutions_from_evidence",
            errors=errors,
        )


def _snippet_sub_batches(
    snippets: list[dict],
    max_excerpts: int,
    max_chars: int,
) -> list[list[dict]]:
    """Split a flat list of snippets into sub-batches.

    A new batch is started when adding the next snippet would exceed either
    *max_excerpts* or *max_chars*.  The very first snippet is always admitted
    even if it alone exceeds *max_chars*, so no snippet is silently dropped.

    Returns a non-empty list of batches.  An empty input returns [[]] so the
    caller still makes one LLM call (with no excerpts).
    """
    if not snippets:
        return [[]]

    batches: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for snip in snippets:
        size = len(snip.get("text", ""))
        over_count = len(current) >= max_excerpts
        over_chars = current_chars + size > max_chars and current  # never flush an empty batch
        if over_count or over_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(snip)
        current_chars += size

    if current:
        batches.append(current)

    return batches


def _expand_source_batches_for_job(
    job_id: str,
    source_batches: list,
    max_excerpts: int = 5,
    max_chars: int = 16_000,
) -> list:
    """Expand source_batches by snippet sub-batching for supported jobs.

    For *domain_lessons_option_b*, every batch element is split so that each
    resulting sub-batch contains at most *max_excerpts* snippets and at most
    *max_chars* characters of excerpt text.  Metadata-only sources (no snippets)
    are carried into every sub-batch unchanged so the LLM retains full source
    context.

    For all other jobs the input list is returned as-is.

    Each element of the returned list maps 1-to-1 to one LLM call in the
    legacy (non-RAG) path of cmd_run.
    """
    if job_id not in {"domain_lessons_option_b"}:
        return source_batches

    expanded: list = []
    for batch in source_batches:
        if batch is None:
            expanded.append(None)
            continue

        with_snips = [s for s in batch if s.get("snippets")]
        no_snips = [s for s in batch if not s.get("snippets")]

        if not with_snips:
            expanded.append(batch)
            continue

        for src in with_snips:
            for sub_snips in _snippet_sub_batches(
                src.get("snippets", []), max_excerpts, max_chars
            ):
                expanded.append([{**src, "snippets": sub_snips}] + no_snips)

    return expanded


# Jobs that are internal helpers and must not appear in run-all loops
_INTERNAL_JOBS: frozenset[str] = frozenset({"domain_lessons_planner"})


# ---------------------------------------------------------------------------
# Planner keyword families — used for deterministic coverage enforcement.
# Each family maps to the schema category that best represents its evidence type.
# Scanned against FULL snippet text (not truncated preview) after planner returns.
# ---------------------------------------------------------------------------
_PLANNER_KEYWORD_FAMILIES: dict[str, tuple[str, ...]] = {
    "prerequisites": (
        "quick", "freely available", "languages", "available in",
        "simple", "easy to administer",
    ),
    "operational_barriers": (
        "lengthy", "time-intensive", "substantial", "resources",
        "constraint", "hurdle", "challenge",
    ),
    "evidence_gaps_uncertainty": (
        "limitations", "future research", "uncertainty", "heterogeneity",
        "inconsistent", "comparability",
    ),
    "equity_implications": (
        "female", "male", "gender", "women", "men", "rural", "urban", "cadre",
    ),
    "governance_process_dependencies": (
        "responsible", "accountable", "report", "monitor", "cadence",
        "monthly", "weekly", "supervisor", "policy", "enforcement",
    ),
    "consequences_impacts": (
        "workload", "delayed", "cost", "access", "burden",
        "quality", "stress", "overwhelm",
    ),
}

_PLANNER_ENFORCEMENT_MAX_SEGMENTS = 10

# Per-family caps on how many new locators enforcement may add.
# Override any individual cap with HRH_ENFORCE_CAP_{FAMILY_UPPER} env var.
_PLANNER_ENFORCEMENT_CAPS: dict[str, int] = {
    "prerequisites":              2,
    "evidence_gaps_uncertainty":  3,
    "governance_process_dependencies": 3,
    "operational_barriers":       5,
    "equity_implications":        5,
    "consequences_impacts":       5,
}


def _enforcement_cap(family: str) -> int:
    """Return the per-family enforcement cap, respecting env overrides."""
    env_key = f"HRH_ENFORCE_CAP_{family.upper()}"
    default = _PLANNER_ENFORCEMENT_CAPS.get(family, 5)
    try:
        return int(os.getenv(env_key, str(default)))
    except (ValueError, TypeError):
        return default


def _enforce_planner_keyword_coverage(
    plans: list[dict],
    sources_by_id: dict,
) -> list[dict]:
    """Deterministically add locators with keyword-family hits that the planner missed.

    Scans the FULL snippet text (not truncated previews) against each keyword family.
    Any locator that matches a family keyword but is not already covered by any segment
    is appended to the highest-priority segment whose likely_categories includes the
    relevant category, or added to a new segment if none exists (up to the cap).

    Only valid locators (present in the source snippets) are added. Never invents
    locator strings. Applied only to plans already produced by the planner LLM.
    """
    _PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    for plan in plans:
        sid = plan.get("source_id", "")
        src = sources_by_id.get(sid)
        if src is None:
            continue

        segments = plan.get("segments", [])

        # Collect all locators already covered by ANY segment
        covered: set[str] = {
            loc
            for seg in segments
            for loc in seg.get("locators", [])
        }

        # Build locator → full text map for this source
        locator_text: dict[str, str] = {
            snip.get("locator", ""): snip.get("text", "")
            for snip in src.get("snippets", [])
            if snip.get("locator")
        }

        for family, keywords in _PLANNER_KEYWORD_FAMILIES.items():
            cap = _enforcement_cap(family)
            # Score each uncovered locator by distinct keyword hits for this family
            scored: list[tuple[int, str]] = []
            for loc, text in locator_text.items():
                if loc not in covered:
                    score = sum(1 for kw in keywords if kw in text.lower())
                    if score > 0:
                        scored.append((score, loc))
            if not scored:
                continue

            # Sort by score desc; stable sort preserves insertion order for ties
            scored.sort(key=lambda x: -x[0])
            to_add = [loc for _, loc in scored[:cap]]
            print(
                f"  [COVERAGE ENFORCE] source={sid!r} family={family!r} "
                f"candidates={len(scored)} added={len(to_add)} cap={cap}"
            )

            # Prefer the highest-priority existing segment that targets this category
            target_seg = next(
                (
                    seg
                    for seg in sorted(
                        segments,
                        key=lambda s: _PRIORITY_ORDER.get(s.get("priority", "low"), 2),
                    )
                    if family in seg.get("likely_categories", [])
                ),
                None,
            )

            if target_seg is not None:
                for loc in to_add:
                    if loc not in covered:
                        target_seg.setdefault("locators", []).append(loc)
                        covered.add(loc)
            elif len(segments) < _PLANNER_ENFORCEMENT_MAX_SEGMENTS:
                new_seg = {
                    "segment_id": f"seg_{len(segments) + 1:03d}",
                    "locators": [loc for loc in to_add if loc not in covered],
                    "likely_categories": [family],
                    "priority": "medium",
                    "reason": f"Deterministic keyword coverage enforcement ({family!r})",
                }
                for loc in new_seg["locators"]:
                    covered.add(loc)
                segments.append(new_seg)
            else:
                # Segment cap reached: merge into the last segment
                last_seg = segments[-1]
                for loc in to_add:
                    if loc not in covered:
                        last_seg.setdefault("locators", []).append(loc)
                        covered.add(loc)
                if family not in last_seg.get("likely_categories", []):
                    last_seg.setdefault("likely_categories", []).append(family)

        plan["segments"] = segments

    return plans


def _truncate_at_word_boundary(text: str, max_chars: int = 300) -> str:
    """Truncate *text* to at most *max_chars*, breaking at the last whitespace.

    Avoids cutting mid-word so that keyword scanners (planner coverage rules,
    snippet validators) do not miss words that straddle the cut point.
    If no whitespace is found before *max_chars*, falls back to a hard cut.
    """
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[:cut] if cut > 0 else text[:max_chars]


def _build_planner_prompt(source: dict, template_path: str) -> str:
    """Build the planner prompt for a single source.

    Reads the template, builds a locator index (locator + preview + type),
    and appends the RENDERED INPUTS block matching the pattern of render_prompt_for_job.
    Previews are truncated at a word boundary so keyword families in the planner
    coverage scan are not split mid-word.
    """
    import json as _json
    template = Path(template_path).read_text(encoding="utf-8")
    locator_index = [
        {
            "locator": snip.get("locator", ""),
            "type": snip.get("type", "text"),
            "preview": _truncate_at_word_boundary(snip.get("text", ""), 500),
        }
        for snip in source.get("snippets", [])
        if snip.get("locator")
    ]
    inputs = {
        "source_id": source.get("source_id", source.get("doc_id", "")),
        "source_title": source.get("source_title", ""),
        "locator_index": locator_index,
        "category_names": list(_DOMAIN_LESSONS_CATEGORIES),
    }
    return (
        template.rstrip()
        + "\n\n## RENDERED INPUTS (machine-generated)\n"
        + _json.dumps(inputs, ensure_ascii=False, indent=2)
        + "\n"
    )


def _check_planner_locators(planner_output: dict, sources_by_id: dict) -> list[str]:
    """Return error strings for any segment locator not present in the source snippets.

    Empty list = all locators valid.
    """
    errors: list[str] = []
    for plan in planner_output.get("plans", []):
        sid = plan.get("source_id", "")
        src = sources_by_id.get(sid)
        if src is None:
            errors.append(f"source_id={sid!r} not found in available sources")
            continue
        available = {snip.get("locator", "") for snip in src.get("snippets", [])}
        for seg in plan.get("segments", []):
            for loc in seg.get("locators", []):
                if loc and loc not in available:
                    errors.append(
                        f"source_id={sid!r} segment={seg.get('segment_id')!r} "
                        f"references unknown locator {loc!r}"
                    )
    return errors


def _planner_to_batches(
    plans: list[dict],
    sources_by_id: dict,
    max_excerpts: int = 10,
    max_chars: int = 16_000,
    max_batches_per_source: int = 10,
) -> list:
    """Convert planner segment plans into extraction source_batches.

    Collects ALL planner-selected locators for each source (across all segments,
    sorted high→medium→low priority), then applies _snippet_sub_batches to enforce
    per-call limits.  Grouping by source (rather than per-segment) gives the extractor
    fuller context per call, which improves category coverage and item classification.
    """
    _PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
    batches: list = []
    for plan in plans:
        sid = plan.get("source_id", "")
        src = sources_by_id.get(sid)
        if src is None:
            continue
        locator_to_snip = {
            snip.get("locator", ""): snip
            for snip in src.get("snippets", [])
            if snip.get("locator")
        }
        segments = sorted(
            plan.get("segments", []),
            key=lambda s: _PRIORITY_ORDER.get(s.get("priority", "low"), 2),
        )
        # Collect all selected locators across all segments, deduplicating while
        # preserving priority order so high-priority evidence appears first in each batch.
        seen_locs: set[str] = set()
        all_snips: list[dict] = []
        for seg in segments:
            for loc in seg.get("locators", []):
                if loc in locator_to_snip and loc not in seen_locs:
                    seen_locs.add(loc)
                    all_snips.append(locator_to_snip[loc])
        if not all_snips:
            continue
        source_batches: list = []
        for sub_snips in _snippet_sub_batches(all_snips, max_excerpts, max_chars):
            source_batches.append([{**src, "snippets": sub_snips}])
        if len(source_batches) > max_batches_per_source:
            included_locs: set[str] = {
                snip.get("locator", "")
                for b in source_batches[:max_batches_per_source]
                for src_item in b
                for snip in src_item.get("snippets", [])
            }
            skipped = [
                snip.get("locator", "")
                for snip in all_snips
                if snip.get("locator") not in included_locs
            ]
            print(
                f"  [BATCH CAP] source={sid!r} planned_locators={len(all_snips)}; "
                f"capped_batches={max_batches_per_source}; skipped_locators={skipped}"
            )
            source_batches = source_batches[:max_batches_per_source]
        batches.extend(source_batches)
    return batches


_DOMAIN_LESSONS_CATEGORIES = (
    "proven_interventions",
    "lessons_learnt",
    "recommendations",
    "prerequisites",
    "operational_barriers",
    "governance_process_dependencies",
    "evidence_gaps_uncertainty",
    "costs_resource_intensity",
    "equity_implications",
    "consequences_impacts",
)

# Expansion pass suffix — appended to the rendered prompt when fewer than 5 locators
# are cited from a batch of ≥8.  The second call typically recovers under-captured
# categories (prerequisites, evidence_gaps, equity, consequences) without requiring a
# separate prompt template.
_EXPANSION_SUFFIX = """\n
## EXPANSION PASS — Second extraction sweep

Your previous extraction may have under-populated some categories.
Re-scan ALL provided excerpts and output a COMPLETE JSON payload that includes
BOTH your previous items AND any additional items you now find.

Focus especially on these frequently missed categories:
- prerequisites          (enabling conditions: availability, language support, training requirements)
- operational_barriers   (resource constraints, "lengthy", "time-intensive", infrastructure gaps)
- evidence_gaps_uncertainty (limitations, measurement heterogeneity, future research calls)
- costs_resource_intensity  (programme costs, patient out-of-pocket costs, resource demands)
- governance_process_dependencies (actor + action + cadence when all three present)
- equity_implications    (named group + distributional difference in same snippet)
- consequences_impacts   (downstream effects: delayed access, increased workload, reduced quality)

Apply the Category Fill Checklist and List/Table Expansion rules from the prompt above.
Return a COMPLETE valid JSON payload — not just the new items.
"""

_DELTA_GROUP_SUFFIX = """\n
## DELTA MODE — Targeted multi-locator extraction

You have been given excerpts from a small set of locators. Instructions:
1. Extract ALL eligible items from ONLY the provided excerpts — apply the Category Fill Checklist and Granularity rules.
2. Every item's citation MUST reference one of the locators in the provided excerpts.
3. If an excerpt contains a list or table: extract EACH entry as a separate item (List/Table Expansion HARD RULE).
4. Output ONLY NEW items not already present in the earlier extraction — do NOT repeat items already extracted.
5. If an excerpt contains no eligible content, output empty category arrays — do NOT invent items.
6. Return a COMPLETE, VALID JSON payload with all domains, all focus areas, all ten category arrays.
"""

_DELTA_GROUP_SIZE: int = 4
_MAX_DELTA_CALLS_PER_BATCH: int = 2


def _count_cited_locators_in_payload(payload: dict, doc_ids: set) -> int:
    """Count unique (doc_id, locator) pairs cited in payload that belong to doc_ids.

    Used to decide whether a coverage expansion call is needed: if very few
    distinct locators are cited despite a large batch being available, a second
    sweep is likely to recover under-captured categories.
    """
    cited: set[tuple[str, str]] = set()
    for domain in payload.get("domains", []):
        for fa in domain.get("focus_areas", []):
            for cat in _DOMAIN_LESSONS_CATEGORIES:
                for item in fa.get(cat, []):
                    for cit in item.get("citations", []):
                        doc_id = cit.get("doc_id", "")
                        locator = cit.get("locator", "")
                        if doc_id in doc_ids and locator:
                            cited.add((doc_id, locator))
    return len(cited)


def _skip_expansion_when_delta_enabled() -> bool:
    """Return True when HRH_SKIP_EXPANSION_WHEN_DELTA is set (default on).

    When enabled and the delta sweep is scheduled to run (cited < delta_threshold),
    the expansion pass is skipped to avoid paying two rate-limit waits for the same
    coverage recovery work.  Set to '0' to restore the old expansion-then-delta order.
    """
    return os.getenv("HRH_SKIP_EXPANSION_WHEN_DELTA", "1").strip().lower() not in ("0", "false", "no", "off")


def _cited_locators_set(payloads: list[dict], doc_ids: set) -> set[str]:
    """Return the set of locator strings cited in any of the payloads for the given doc_ids.

    Aggregates across multiple payloads (original + expansion + prior delta calls) so
    the delta sweep only targets locators not yet converted by any earlier call.
    """
    cited: set[str] = set()
    for payload in payloads:
        for domain in payload.get("domains", []):
            for fa in domain.get("focus_areas", []):
                for cat in _DOMAIN_LESSONS_CATEGORIES:
                    for item in fa.get(cat, []):
                        for cit in item.get("citations", []):
                            if cit.get("doc_id", "") in doc_ids and cit.get("locator", ""):
                                cited.add(cit["locator"])
    return cited


def _rank_locators_by_keyword(locators: list[str], batch: list[dict]) -> list[str]:
    """Sort uncited locators by keyword-family hit count (descending).

    Locators whose full text matches more keyword-family terms from
    _PLANNER_KEYWORD_FAMILIES are swept first, maximising extraction yield
    within the delta group budget. Zero-hit locators are kept at the back.
    """
    locator_text: dict[str, str] = {
        snip.get("locator", ""): snip.get("text", "").lower()
        for src in batch
        for snip in src.get("snippets", [])
        if snip.get("locator")
    }
    all_keywords: tuple[str, ...] = tuple(
        kw for kws in _PLANNER_KEYWORD_FAMILIES.values() for kw in kws
    )

    def _hits(loc: str) -> int:
        text = locator_text.get(loc, "")
        return sum(1 for kw in all_keywords if kw in text)

    return sorted(locators, key=_hits, reverse=True)


def _log_coverage_warnings(job_id: str, payload: dict, all_sources: list[dict]) -> None:
    """Print a WARNING for each source whose citation coverage is suspiciously low.

    Applies only to domain_lessons_option_b.  For every source that has ≥ 20
    snippets in the input, if the fraction of its locators that appear in at
    least one citation in *payload* is < 10 %, a WARNING line is printed to
    stdout.  The run is NOT failed.

    Coverage = cited_unique_locators / available_snippets.
    """
    if job_id != "domain_lessons_option_b":
        return

    # Build per-source info from input: source_id → {available, title}
    source_info: dict[str, dict] = {}
    for src in all_sources:
        sid = src.get("source_id", "")
        if not sid:
            continue
        source_info[sid] = {
            "available": len(src.get("snippets", [])),
            "title": src.get("source_title", sid),
        }

    # Collect unique cited locators per doc_id from the merged output
    cited: dict[str, set[str]] = {}
    for domain in payload.get("domains", []):
        for fa in domain.get("focus_areas", []):
            for cat in _DOMAIN_LESSONS_CATEGORIES:
                for item in fa.get(cat, []):
                    for cit in item.get("citations", []):
                        doc_id = cit.get("doc_id", "")
                        locator = cit.get("locator", "")
                        if doc_id and locator:
                            cited.setdefault(doc_id, set()).add(locator)

    # Emit per-source warnings where applicable
    for sid in sorted(source_info):
        info = source_info[sid]
        available = info["available"]
        if available < 20:
            continue
        n_cited = len(cited.get(sid, set()))
        coverage = n_cited / available
        if coverage < 0.10:
            pct = round(coverage * 100, 1)
            print(
                f"[COVERAGE WARNING] source_id={sid} "
                f"source_title={info['title']!r} "
                f"available_snippets={available} "
                f"cited_locators={n_cited} "
                f"coverage={pct}%"
            )


def _stamp_run_date(job_id: str, payload: dict) -> None:
    """Overwrite payload['generated_at'] with today's date for jobs where the LLM
    must not determine the run date (avoids hallucinated or stale dates)."""
    if job_id in {"domain_solutions_from_evidence", "domain_lessons_option_b", "domain_lessons_planner"}:
        from datetime import date
        payload["generated_at"] = date.today().isoformat()


def _llm_call_with_retry(
    rendered_prompt, generate_json, LLMNotConfigured, _json,
    schema_rel=None, job_id=None, label=None,
):
    """Call the LLM with up to 3 repair attempts. Returns parsed payload or None.

    When schema_rel is None, schema validation is skipped (useful for per-item
    RAG calls where each item is a partial output that won't match the full schema).

    *label* is an optional string (e.g. "planner SRC1", "extractor batch 2") printed
    alongside the final failure warning so the caller site is identifiable in logs.
    """
    from app.core.validators import validate_output

    max_attempts = 3 if schema_rel else 1
    repair_notes = None
    payload = None

    for attempt in range(1, max_attempts + 1):
        try:
            llm = generate_json(rendered_prompt, repair_instructions=repair_notes, job_id=job_id)
        except LLMNotConfigured as e:
            print(str(e), file=sys.stderr)
            return None

        try:
            payload = _json.loads(llm.text)
        except Exception as e:
            repair_notes = f"Your output was not valid JSON. Error: {e}"
            if attempt == max_attempts:
                label_str = f" [{label}]" if label else ""
                print(f"  Warning: JSON parse failed after {max_attempts} attempts{label_str}: {repair_notes}", file=sys.stderr)
                break
            continue

        if schema_rel is None:
            return payload

        # Truncate snippets to ≤300 chars before validation so the LLM does not
        # need a repair round just for overlong snippets — corrected silently here.
        payload = _clean_citations(payload)

        try:
            validate_output(payload, schema_rel)
            return payload
        except Exception as e:
            repair_notes = str(e)
            if attempt == max_attempts:
                label_str = f" [{label}]" if label else ""
                print(f"  Warning: output invalid after {max_attempts} attempts{label_str}", file=sys.stderr)
                print(f"  Last validation error: {repair_notes}", file=sys.stderr)
            continue

    return payload  # may be invalid but best effort


def _extract_rag_items(
    job_id: str, spec: dict, country_name: str | None, country_iso3: str | None
) -> list[tuple[str, dict]]:
    """Extract (query_text, item_inputs) pairs for RAG per-item processing.

    Each tuple contains:
      - query_text: the text to embed and search against the index
      - item_inputs: dict of inputs to pass to render_prompt_with_rag
    """
    from app.analyze.extractors import (
        extract_phase1_questions,
        extract_rrr_solutions,
        extract_table2_items,
        extract_table3_items,
        extract_learning_domains,
        extract_benchmark_dimensions_countries,
    )

    items: list[tuple[str, dict]] = []

    if job_id == "phase1_discovery_qa":
        questions = extract_phase1_questions(spec)
        for q in questions:
            query = q.question
            item_inputs = {
                "country_name": country_name,
                "country_iso3": country_iso3,
                "questions": [{"question_id": q.question_id, "question": q.question}],
            }
            items.append((query, item_inputs))

    elif job_id == "rrr_evidence_matrix":
        sols = extract_rrr_solutions(spec)
        for s in sols:
            query = _build_rrr_query(s.solution, s.mechanism)
            item_inputs = {
                "solutions": [{"solution_id": s.solution_id, "solution": s.solution, "mechanism": s.mechanism}],
            }
            items.append((query, item_inputs))

    elif job_id == "table2_root_cause_mapping":
        framework_items = extract_table2_items(spec)
        for it in framework_items:
            query = f"{it.category}: {it.root_cause} — {it.definition}"
            item_inputs = {
                "framework_items": [{
                    "item_id": it.item_id,
                    "category": it.category,
                    "root_cause": it.root_cause,
                    "definition": it.definition,
                }],
            }
            items.append((query, item_inputs))

    elif job_id == "table3_intervention_framework":
        interventions = extract_table3_items(spec)
        for it in interventions:
            query = f"{it.lever}: {it.intervention} — {it.mechanism}"
            item_inputs = {
                "interventions": [{
                    "intervention_id": it.intervention_id,
                    "lever": it.lever,
                    "intervention": it.intervention,
                    "mechanism": it.mechanism,
                }],
            }
            items.append((query, item_inputs))

    elif job_id == "benchmark_country_scoring":
        dims, countries = extract_benchmark_dimensions_countries(spec)
        # For benchmarking, send all dimensions + countries as one query
        query = "HRH benchmarking: " + ", ".join(d.label for d in dims)
        item_inputs = {
            "dimensions": [{"dimension_id": d.dimension_id, "label": d.label} for d in dims],
            "countries": [{"country_name": c.country_name, "iso3": c.iso3} for c in countries],
        }
        items.append((query, item_inputs))

    elif job_id == "country_learning_briefs":
        domains = extract_learning_domains(spec)
        for d in domains:
            query = f"Learning domain: {d.domain}"
            item_inputs = {
                "country_name": country_name,
                "country_iso3": country_iso3,
                "learning_domains": [{"domain_id": d.domain_id, "domain": d.domain}],
            }
            items.append((query, item_inputs))

    elif job_id == "domain_lessons_option_b":
        # One LLM call per (domain × focus_area) — scoped retrieval per topic.
        target = country_name or country_iso3 or "Global"
        categories = spec.get("categories", {})
        for domain in spec.get("domains", []):
            domain_id = domain.get("domain_id", "")
            domain_label = domain.get("domain_label", domain_id)
            for fa in domain.get("focus_areas", []):
                fa_id = fa.get("focus_area_id", "")
                fa_label = fa.get("label", fa_id)
                query = f"{domain_label}: {fa_label}"
                item_inputs = {
                    "target_country": target,
                    "domains": [{
                        "domain_id": domain_id,
                        "domain_label": domain_label,
                        "focus_areas": [{"focus_area_id": fa_id, "label": fa_label}],
                    }],
                    "categories": categories,
                }
                items.append((query, item_inputs))

    else:
        raise KeyError(f"_extract_rag_items: unsupported job_id '{job_id}'")

    return items


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
        if job_id in _INTERNAL_JOBS:
            continue
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
            no_split=getattr(args, "no_split", False),
            index=getattr(args, "index", None),
        )

        try:
            result = cmd_run(job_args)
            if result == 0:
                print(f"[{job_id}] VALID [OK]")
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
    filename = f"output_{mode}.json"

    country_name = getattr(args, "country_name", None)
    country_iso3 = getattr(args, "country_iso3", None)

    print(f"Rendering deliverables for {len(registry.jobs)} job(s) from {filename} in timestamped folders...")
    print()

    results = []

    for job_id, job_def in registry.jobs.items():
        print(f"[{job_id}] Starting...")

        # Find all timestamped folders and look for the target JSON file
        matching_files = []
        for folder in job_def.output_dir.iterdir():
            if folder.is_dir():
                json_file = folder / filename
                if json_file.exists():
                    matching_files.append(json_file)

        if not matching_files:
            print(f"[{job_id}] SKIP: no {filename} found in timestamped folders under {job_def.output_dir}")
            results.append((job_id, "SKIP"))
            print()
            continue

        # Sort by modification time, use most recent
        matching_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        input_file = matching_files[0]
        print(f"[{job_id}] Using: {input_file.parent.name}/{input_file.name}")

        try:
            # Narrative jobs -> DOCX only
            if job_id in ("phase1_discovery_qa", "country_learning_briefs"):
                # Generate auto-named outputs with timestamps
                docx_out = auto_output_name(
                    str(input_file),
                    "docx",
                    mode=mode,
                    country_name=country_name,
                    country_iso3=country_iso3
                )

                docx_path = render_docx_file(job_id, str(input_file), docx_out)
                print(f"[{job_id}] Wrote: {docx_path}")

            # Table jobs -> XLSX only
            elif job_id in (
                "rrr_evidence_matrix",
                "table2_root_cause_mapping",
                "table3_intervention_framework",
                "benchmark_country_scoring",
            ):
                # Generate auto-named outputs with timestamps
                xlsx_out = auto_output_name(
                    str(input_file),
                    "xlsx",
                    mode=mode,
                    country_name=country_name,
                    country_iso3=country_iso3
                )

                xlsx_path = render_xlsx_file(job_id, str(input_file), xlsx_out)
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
    do_extract = not getattr(args, "no_extract", False)
    sources_dir = Path("data/sources").resolve()

    # Scan directories
    pdf_dir = sources_dir / iso3 / "pdf"
    docx_dir = sources_dir / iso3 / "docx"

    sources = []
    source_counter = 1
    total_snippets = 0

    # Scan PDF files
    if pdf_dir.exists():
        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            source_title = pdf_file.stem  # filename without extension
            rel_path = pdf_file.relative_to(Path.cwd().resolve())
            snippets: list[dict] = []

            if do_extract:
                try:
                    raw = extract_pdf(pdf_file)
                    snippets = [dict(s) for s in chunk_snippets(raw)]
                    print(f"  Extracted {len(snippets)} snippet(s) from {pdf_file.name}")
                except Exception as exc:
                    print(f"  WARNING: failed to extract {pdf_file.name}: {exc}", file=sys.stderr)

            total_snippets += len(snippets)
            sources.append({
                "source_id": f"SRC{source_counter}",
                "source_title": source_title,
                "source_type": "pdf",
                "file_path": str(rel_path).replace("\\", "/"),
                "reference": f"{source_title} (PDF document)",
                "snippets": snippets
            })
            source_counter += 1

    # Scan DOCX files
    if docx_dir.exists():
        for docx_file in sorted(docx_dir.glob("*.docx")):
            source_title = docx_file.stem
            rel_path = docx_file.relative_to(Path.cwd().resolve())
            snippets = []

            if do_extract:
                try:
                    raw = extract_docx(docx_file)
                    snippets = [dict(s) for s in chunk_snippets(raw)]
                    print(f"  Extracted {len(snippets)} snippet(s) from {docx_file.name}")
                except Exception as exc:
                    print(f"  WARNING: failed to extract {docx_file.name}: {exc}", file=sys.stderr)

            total_snippets += len(snippets)
            sources.append({
                "source_id": f"SRC{source_counter}",
                "source_title": source_title,
                "source_type": "docx",
                "file_path": str(rel_path).replace("\\", "/"),
                "reference": f"{source_title} (DOCX document)",
                "snippets": snippets
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

    print(f"Scanned {len(sources)} file(s), extracted {total_snippets} total snippet(s)")
    print(f"Wrote: {output_file}")
    return 0


def cmd_sources_index(args: argparse.Namespace) -> int:
    """Build an embedding index from a sources JSON file."""
    sources_path = args.sources
    output_path = getattr(args, "output", None)

    if not Path(sources_path).exists():
        print(f"Sources file not found: {sources_path}", file=sys.stderr)
        return 2

    try:
        result_path = build_index(sources_path, output_path)
        print(f"Wrote index: {result_path}")
        return 0
    except Exception as e:
        print(f"Failed to build index: {e}", file=sys.stderr)
        return 3


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
    r.add_argument("--mode", required=True, choices=["stub", "llm", "llm_planned"], help="Execution mode")
    r.add_argument("--spec-id", required=True, help="Spec identifier string to embed in output")
    r.add_argument("--country-name", default=None, help="Country name (Phase 1 only for now)")
    r.add_argument("--country-iso3", default=None, help="ISO3 (Phase 1 only for now)")
    r.add_argument("--sources", default=None, help="Optional path to curated sources JSON file")
    r.add_argument("--no-split", action="store_true", default=False, help="Send all sources in one LLM call instead of per-source")
    r.add_argument("--index", default=None, help="Path to embedding index for RAG retrieval (from sources-index)")
    r.set_defaults(func=cmd_run)

    ra = sub.add_parser("run-all", help="Run all jobs from registry in batch")
    ra.add_argument("--mode", required=True, choices=["stub", "llm"], help="Execution mode")
    ra.add_argument("--spec-id", default=None, help="Spec identifier (defaults to job_id for each job)")
    ra.add_argument("--country-name", default=None, help="Country name (for country-specific jobs)")
    ra.add_argument("--country-iso3", default=None, help="ISO3 country code (for country-specific jobs)")
    ra.add_argument("--sources", default=None, help="Optional path to curated sources JSON file")
    ra.add_argument("--no-split", action="store_true", default=False, help="Send all sources in one LLM call instead of per-source")
    ra.add_argument("--index", default=None, help="Path to embedding index for RAG retrieval (from sources-index)")
    ra.set_defaults(func=cmd_run_all)

    ra2 = sub.add_parser("render-all", help="Render deliverables for all jobs (md/xlsx/docx) from existing outputs")
    ra2.add_argument("--mode", required=True, choices=["stub", "llm"], help="Which output files to render (stub or llm)")
    ra2.add_argument("--country-name", default=None, help="Country name (for auto-generated filename)")
    ra2.add_argument("--country-iso3", default=None, help="ISO3 country code (for auto-generated filename)")
    ra2.set_defaults(func=cmd_render_all)

    s = sub.add_parser("sources-scan", help="Scan PDF/DOCX files and generate sources JSON")
    s.add_argument("--country-iso3", required=True, help="ISO3 country code (e.g., ETH, KEN)")
    s.add_argument("--no-extract", action="store_true", default=False, help="Skip text extraction (metadata only)")
    s.set_defaults(func=cmd_sources_scan)

    si = sub.add_parser("sources-index", help="Build embedding index from sources JSON for RAG retrieval")
    si.add_argument("--sources", required=True, help="Path to sources JSON file (e.g., data/sources/eth_sources.json)")
    si.add_argument("--output", default=None, help="Output path for index file (defaults to <stem>_index.json)")
    si.set_defaults(func=cmd_sources_index)

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
