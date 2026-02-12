# Benchmark Country Scoring (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/benchmark_country_scoring.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, countries
- Each score must include evidence (EvidenceNote or NoEvidence).
- If you cannot justify a score with sources, use NoEvidence and keep score conservative.

## Grounding requirements (CRITICAL)
For each country and each dimension:
- rationale MUST explicitly connect:
  - the score value to a specific evidence statement
  - and why nearby scores (higher/lower) were not chosen given evidence limits
- If the spec implies cross-country comparison but allowed_sources are country-only:
  - use NoEvidence and assign conservative scores
- locator MUST be specific (page/section/table/figure). Avoid vague references.

### DETAIL & GRANULARITY (CRITICAL)
- When source snippets contain tables, data breakdowns, or indicator scores:
  - REPRODUCE the table or data in your rationale (use markdown table format)
  - Include ALL rows and columns — do NOT summarize or condense
  - Preserve specific numbers, rankings, percentages, and indicator values
- Score rationale should be 3–6 sentences with specific data points justifying the score
- Include concrete comparisons, benchmarks, or thresholds from the sources

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string)
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

Strongly preferred:
- quote (short excerpt 1–3 sentences supporting the scoring rationale)

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
