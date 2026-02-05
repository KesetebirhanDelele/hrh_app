from __future__ import annotations

import argparse
from pathlib import Path

from app.jobs.registry import get_job
from app.analyze.prompting import render_phase1_prompt


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True)
    p.add_argument("--spec-id", required=True)
    p.add_argument("--country-name", required=True)
    p.add_argument("--country-iso3", default=None)
    p.add_argument("--out", default=None, help="Output file path (default: <job output_dir>/rendered_prompt.txt)")
    args = p.parse_args()

    job = get_job(args.job)

    rendered = render_phase1_prompt(
        template_path=str(job.prompt_template),
        spec_path=str(job.spec_file),
        spec_id=args.spec_id,
        country_name=args.country_name,
        country_iso3=args.country_iso3,
    )

    out_path = Path(args.out).resolve() if args.out else (job.output_dir / "rendered_prompt.txt").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
