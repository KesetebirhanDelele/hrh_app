# Benchmark Country Scoring (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/benchmark_country_scoring.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, countries
- Each score must include evidence (EvidenceNote or NoEvidence).
- If you cannot justify a score with sources, use NoEvidence and keep score conservative.

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string)
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

If you cannot provide any identifier, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs, every citation MUST include:
- `source_id`: must match one of `allowed_sources[].source_id` (e.g., SRC1, SRC2)
- You may ONLY cite from `allowed_sources`. Do not invent or reference sources outside this list.
- If you cannot find supporting evidence in `allowed_sources`, use NoEvidence.

## Inputs you will receive
- spec_id (string)
- countries list and dimensions list from spec

## JSON shape
{
  "job_id": "benchmark_country_scoring",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "countries": [
    {
      "country_name": "Example",
      "iso3": "XXX",
      "overall_score": { "score": 0, "evidence": { "quality": "none", "rationale": "...", "citations": [] } },
      "dimensions": [
        { "dimension_id": "d1", "label": "Example", "score_note": { "score": 0, "evidence": { "quality": "none", "rationale": "...", "citations": [] } } }
      ]
    }
  ]
}

## Now produce the final JSON only.
