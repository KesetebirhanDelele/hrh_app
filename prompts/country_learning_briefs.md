# Country Learning Briefs (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/country_learning_briefs.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, country, domains
- Each domains[] entry MUST include evidence (EvidenceNote or NoEvidence).
- Use EvidenceNote ONLY if you have at least one valid citation after applying citation rules; otherwise use NoEvidence.

## Grounding & content requirements (CRITICAL)
For each domains[] entry:
1) summary MUST be specific and decision-relevant (2–6 sentences). Avoid generic “studies show”.
2) key_questions MUST be 2–5 items and should be “investigable” questions.
3) If the domain is about absenteeism/motivation/productivity/performance determinants:
   - summary MUST include a bullet list of 5–10 determinants grouped under 3+ headings.
   - Each determinant MUST be grounded by at least one citation OR omitted.
   - If no determinants can be grounded from allowed_sources, use NoEvidence for the whole domain.

## Evidence object (schema-aligned)
- EvidenceNote shape:
  {
    "quality": "high" | "medium" | "low",
    "rationale": "<string>",
    "citations": [ <one or more valid citations> ]
  }
- NoEvidence shape:
  {
    "quality": "none",
    "rationale": "<string>",
    "citations": []
  }

IMPORTANT: Do NOT include an evidence.type field.

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string) — MUST be specific (page/section/table/figure)
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

Strongly preferred:
- quote (short excerpt 1–3 sentences supporting the summary or a key determinant)

If you cannot provide any identifier, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs, every citation MUST include:
- `source_id`: must match one of `allowed_sources[].source_id` (e.g., SRC1, SRC2)
- You may ONLY cite from `allowed_sources`. Do not invent or reference sources outside this list.
- If you cannot find supporting evidence in `allowed_sources`, use NoEvidence.

## Inputs you will receive
- country_name, country_iso3 (optional)
- spec_id
- learning domains list with domain_id + domain label

## JSON shape
{
  "job_id": "country_learning_briefs",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "country": { "name": "<country_name>", "iso3": "<ISO3 if provided>" },
  "domains": [
    {
      "domain_id": "...",
      "domain": "...",
      "summary": "...",
      "key_questions": ["..."],
      "evidence": { "quality": "none", "rationale": "...", "citations": [] }
    }
  ]
}

## Now produce the final JSON only.
