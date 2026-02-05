from app.jobs.briefs_stub_runner import run_briefs_stub
from app.core.validators import validate_output
from app.jobs.registry import get_job
import json
from pathlib import Path


def test_briefs_stub_runs_and_validates() -> None:
    out_path = run_briefs_stub(spec_id="key_hrh_learning_domains_v1", country_name="Ethiopia", country_iso3="ETH")
    job = get_job("country_learning_briefs")
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema_rel = str(job.output_schema.relative_to(Path.cwd()))
    validate_output(payload, schema_rel)
