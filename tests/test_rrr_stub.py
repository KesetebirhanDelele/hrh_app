from app.jobs.rrr_stub_runner import run_rrr_stub
from app.core.validators import validate_output
from app.jobs.registry import get_job


def test_rrr_stub_runs_and_validates() -> None:
    out_path = run_rrr_stub(spec_id="rrr_solutions_resource_constrained_v1")
    job = get_job("rrr_evidence_matrix")
    payload = __import__("json").loads(out_path.read_text(encoding="utf-8"))
    schema_rel = str(job.output_schema.relative_to(__import__("pathlib").Path.cwd()))
    validate_output(payload, schema_rel)
