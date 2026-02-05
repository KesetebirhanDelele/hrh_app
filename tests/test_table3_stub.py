from app.jobs.table3_stub_runner import run_table3_stub
from app.core.validators import validate_output
from app.jobs.registry import get_job
import json
from pathlib import Path


def test_table3_stub_runs_and_validates() -> None:
    out_path = run_table3_stub(spec_id="table3_intervention_framework_v1")
    job = get_job("table3_intervention_framework")
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
