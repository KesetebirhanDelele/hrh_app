from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.jobs.benchmark_stub_runner import run_benchmark_stub
from app.jobs.briefs_stub_runner import run_briefs_stub
from app.jobs.phase1_stub_runner import run_phase1_stub
from app.jobs.rrr_stub_runner import run_rrr_stub
from app.jobs.table2_stub_runner import run_table2_stub
from app.jobs.table3_stub_runner import run_table3_stub


@dataclass(frozen=True)
class RunResult:
    job_id: str
    output_path: Path


def run_job_stub(
    job_id: str,
    spec_id: str,
    country_name: Optional[str] = None,
    country_iso3: Optional[str] = None,
) -> RunResult:
    """
    Stub execution router. Add new jobs here as you implement their stub runners.
    """
    if job_id == "phase1_discovery_qa":
        if not country_name:
            raise ValueError("country_name is required for phase1_discovery_qa")
        out_path = run_phase1_stub(spec_id=spec_id, country_name=country_name, country_iso3=country_iso3)
        return RunResult(job_id=job_id, output_path=out_path)

    if job_id == "rrr_evidence_matrix":
        out_path = run_rrr_stub(spec_id=spec_id)
        return RunResult(job_id=job_id, output_path=out_path)

    if job_id == "table2_root_cause_mapping":
        out_path = run_table2_stub(spec_id=spec_id)
        return RunResult(job_id=job_id, output_path=out_path)

    if job_id == "table3_intervention_framework":
        out_path = run_table3_stub(spec_id=spec_id)
        return RunResult(job_id=job_id, output_path=out_path)

    if job_id == "benchmark_country_scoring":
        out_path = run_benchmark_stub(spec_id=spec_id)
        return RunResult(job_id=job_id, output_path=out_path)

    if job_id == "country_learning_briefs":
        if not country_name:
            raise ValueError("country_name is required for country_learning_briefs")
        out_path = run_briefs_stub(spec_id=spec_id, country_name=country_name, country_iso3=country_iso3)
        return RunResult(job_id=job_id, output_path=out_path)

    raise KeyError(f"Stub runner not implemented for job_id '{job_id}'")
