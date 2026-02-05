from app.jobs.benchmark_stub_runner import run_benchmark_stub
from app.core.validators import validate_output
from app.jobs.registry import get_job
import json
from pathlib import Path


def test_benchmark_stub_runs_and_validates() -> None:
    out_path = run_benchmark_stub(spec_id="benchmark_country_scoring_v1")
    job = get_job("benchmark_country_scoring")
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
