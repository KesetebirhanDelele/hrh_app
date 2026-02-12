from app.jobs.table3_stub_runner import run_table3_stub
from app.analyze.extractors import extract_table3_items
from app.analyze.prompting import _read_json
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


def test_table3_no_placeholder_interventions() -> None:
    """Regression: intervention text must not contain 'Sample intervention'."""
    job = get_job("table3_intervention_framework")
    spec = _read_json(job.spec_file)
    items = extract_table3_items(spec)

    assert len(items) >= 1
    for it in items:
        assert "Sample intervention" not in it.intervention, (
            f"Placeholder found in intervention_id={it.intervention_id}: {it.intervention}"
        )
        assert "stub placeholder" not in it.mechanism.lower(), (
            f"Stub placeholder found in mechanism for {it.intervention_id}: {it.mechanism}"
        )
        # Each item should have a meaningful lever
        assert it.lever.strip() != ""


def test_table3_known_lever_has_real_intervention() -> None:
    """At least the 'Enabling Environment' lever must have a non-placeholder intervention."""
    job = get_job("table3_intervention_framework")
    spec = _read_json(job.spec_file)
    items = extract_table3_items(spec)

    levers = {it.lever for it in items}
    assert "Enabling Environment" in levers, f"Expected 'Enabling Environment' in levers: {levers}"

    ee_item = next(it for it in items if it.lever == "Enabling Environment")
    assert "Sample" not in ee_item.intervention
    assert "interventions" in ee_item.intervention.lower()
