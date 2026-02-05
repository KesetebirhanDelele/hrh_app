from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass(frozen=True)
class JobDef:
    job_id: str
    label: str
    spec_file: Path
    prompt_template: Path
    output_schema: Path
    output_dir: Path


@dataclass(frozen=True)
class Registry:
    repo_root: Path
    version: str
    project: str
    jobs: Dict[str, JobDef]


def _require_str(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Missing/invalid '{key}' in registry")
    return v


def load_registry(registry_path: str = "configs/job_registry.yaml", base_dir: Optional[str] = None) -> Registry:
    """
    Load configs/job_registry.yaml and resolve all referenced paths relative to repo root.
    """
    repo_root = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
    reg_file = (repo_root / registry_path).resolve()
    if not reg_file.exists():
        raise FileNotFoundError(f"Registry not found: {reg_file}")

    data = yaml.safe_load(reg_file.read_text(encoding="utf-8")) or {}
    version = _require_str(data, "version")
    project = _require_str(data, "project")

    jobs_list: List[Dict[str, Any]] = data.get("jobs") or []
    if not isinstance(jobs_list, list) or not jobs_list:
        raise ValueError("Registry must contain non-empty 'jobs' list")

    jobs: Dict[str, JobDef] = {}
    for j in jobs_list:
        if not isinstance(j, dict):
            raise ValueError("Each job entry must be a mapping")

        job_id = _require_str(j, "job_id")
        label = _require_str(j, "label")

        spec_file = repo_root / _require_str(j, "spec_file")
        prompt_template = repo_root / _require_str(j, "prompt_template")
        output_schema = repo_root / _require_str(j, "output_schema")
        output_dir = repo_root / _require_str(j, "output_dir")

        # Validate existence for deterministic failure early
        for p, kind in [
            (spec_file, "spec_file"),
            (prompt_template, "prompt_template"),
            (output_schema, "output_schema"),
        ]:
            if not p.exists():
                raise FileNotFoundError(f"{kind} not found for job '{job_id}': {p}")

        jobs[job_id] = JobDef(
            job_id=job_id,
            label=label,
            spec_file=spec_file,
            prompt_template=prompt_template,
            output_schema=output_schema,
            output_dir=output_dir,
        )

    return Registry(repo_root=repo_root, version=version, project=project, jobs=jobs)


def get_job(job_id: str, registry_path: str = "configs/job_registry.yaml", base_dir: Optional[str] = None) -> JobDef:
    reg = load_registry(registry_path=registry_path, base_dir=base_dir)
    try:
        return reg.jobs[job_id]
    except KeyError as e:
        available = ", ".join(sorted(reg.jobs.keys()))
        raise KeyError(f"Unknown job_id '{job_id}'. Available: {available}") from e
