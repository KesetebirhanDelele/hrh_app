# RRR Evidence Matrix (Schema-Strict)

You MUST output valid JSON ONLY (no markdown, no prose) that validates against:
- schemas/rrr_evidence_matrix.schema.json
- schemas/common.json

## Output rules
- Output must contain: job_id, spec_id, generated_at, solutions
- Each solutions[] row MUST include evidence:
  - Use EvidenceNote ONLY if you have at least one valid citation after applying citation rules
  - Otherwise use NoEvidence with quality="none" and citations=[]

## STRICT CONSTRAINTS (must follow exactly)
- Do NOT include a "type" field anywhere in the output (evidence.type, citation.type, etc.). Those keys are forbidden.
- evidence must be EXACTLY one of:
  A) EvidenceNote:
     {
       "quality": "high" | "medium" | "low",
       "rationale": "<string>",
       "citations": [ <one or more valid citation objects> ]
     }
     CRITICAL: Each citation MUST have at least ONE of: source_url, reference, doi, or isbn
     CRITICAL: If citations would be empty after applying rules, you MUST use NoEvidence instead.
  B) NoEvidence:
     {
       "quality": "none",
       "rationale": "<string>",
       "citations": []
     }

- feasibility_resource_constrained must be exactly one of:
  "high" | "medium" | "low" | "unknown"
  (Do NOT use "moderate". Map "moderate" to "medium".)

### Grounding specificity (CRITICAL)
- For each solution, the evidence.rationale MUST state:
  - what outcome(s) the evidence supports (e.g., attendance, motivation, productivity, quality)
  - the context limits (e.g., LMIC/primary care; not Ethiopia-specific)
- locator MUST be specific (page/section/table/figure). Avoid vague locators like "report" or "overview".
- If a claim about effectiveness cannot be supported by allowed_sources, use NoEvidence (do not guess).

### DETAIL & GRANULARITY (CRITICAL)
- When source snippets contain tables, data breakdowns, or structured lists:
  - REPRODUCE the table data in your mechanism/rationale (use markdown table format)
  - Include ALL rows and columns — do NOT summarize or condense
  - Preserve specific numbers, effect sizes, percentages, and outcome measures
- implementation_notes should include specific practical steps with concrete details from sources
- risks should reference specific documented challenges, not generic risks
- Answers should be detailed and evidence-rich, NOT brief summaries

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string) — specific page/section/table/figure
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

Strongly preferred:
- quote (short excerpt 1–3 sentences supporting the key claim)

If you cannot provide any of the above identifiers, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs:
- Every citation MUST include:
  - source_id: must match one of allowed_sources[].source_id
- You may ONLY cite from allowed_sources.
- If allowed_sources do not support the solution’s evidence claim, use NoEvidence.

## Inputs you will receive
- spec_id (string)
- solutions: list of objects with:
  - solution_id
  - solution
  - mechanism (or description)

## JSON template (shape)
{
  "job_id": "rrr_evidence_matrix",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "solutions": [
    {
      "solution_id": "...",
      "solution": "...",
      "mechanism": "...",
      "evidence": { "quality": "none", "rationale": "...", "citations": [] },
      "feasibility_resource_constrained": "unknown",
      "risks": [],
      "implementation_notes": ""
    }
  ]
}

## Now produce the final JSON only.
