from app.jobs.registry import get_job


def test_registry_loads_phase1_job() -> None:
    job = get_job("phase1_discovery_qa")
    assert job.job_id == "phase1_discovery_qa"
    assert job.spec_file.name.endswith(".json")
    assert job.prompt_template.name.endswith(".md")
    assert job.output_schema.name.endswith(".json")
