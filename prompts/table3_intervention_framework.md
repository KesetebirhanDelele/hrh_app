# Table 3 Integrated Intervention Framework (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/table3_intervention_framework.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, interventions
- Each interventions[] entry MUST include evidence (EvidenceNote or NoEvidence).
- Use EvidenceNote ONLY if you have at least one valid citation after applying citation rules; otherwise use NoEvidence.

## Grounding requirements (CRITICAL)
For each intervention:
- mechanism MUST be concrete: "how it changes behavior/system" (not buzzwords).
- implementation_notes MUST list 2–5 practical steps and constraints.
- dependencies MUST be concrete enabling conditions (data, budget, staffing, governance).
- risks MUST include at least 1–3 realistic risks (gaming, burden shift, equity harms).
- evidence.rationale MUST specify what the evidence supports (e.g., improved attendance, motivation, service quality) and the limits.
- If the intervention is plausible but not supported in allowed_sources, use NoEvidence (do not fabricate).

### Field type constraints (STRICT)
- implementation_notes MUST be a single STRING (not a list/array).
  - If you need bullets, embed them inside the string using newlines, e.g.:
    "implementation_notes": "- Step 1...\n- Step 2...\n- Step 3..."
- mechanism MUST be a string.
- dependencies MUST be an array of strings.
- risks MUST be an array of strings (or objects only if schema allows; otherwise strings).

### EVIDENCE QUALITY VALUES (CRITICAL)
The evidence.quality field MUST be one of these EXACT values:
- "high" - Strong, direct evidence from multiple high-quality sources
- "medium" - Moderate evidence with some limitations (NOT "moderate")
- "low" - Weak or indirect evidence
- "none" - No evidence found in allowed sources (use NoEvidence)

CRITICAL: Use "medium" NOT "moderate". Any other value will fail validation.

### DETAIL & GRANULARITY (CRITICAL)
- When source snippets contain tables, data breakdowns, or structured lists:
  - REPRODUCE the table or list in your mechanism/implementation_notes (use markdown table format)
  - Include ALL rows and columns — do NOT summarize or condense
  - Preserve specific numbers, timelines, targets, and cadre details
- mechanism should be 3–8 sentences with specific behavioral/system change details
- implementation_notes should include specific steps with concrete targets, timelines, and resource requirements from sources
- dependencies and risks should reference specific documented constraints, not generic ones

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
- quote (short excerpt 1–3 sentences supporting the mechanism or implementation guidance)

If you cannot provide any identifier, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs:
- Every citation MUST include:
  - source_id: must match one of allowed_sources[].source_id
- You may ONLY cite from allowed_sources.
- If allowed_sources do not support the intervention, use NoEvidence.

## Inputs you will receive
- spec_id (string)
- interventions: list with fields like lever/intervention/mechanism (or similar)

## JSON template (shape)
{
  "job_id": "table3_intervention_framework",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "interventions": [
    {
      "intervention_id": "...",
      "lever": "...",
      "intervention": "...",
      "mechanism": "...",
      "evidence": { "quality": "none", "rationale": "...", "citations": [] },
      "implementation_notes": "- Step 1...\n- Step 2...\n- Step 3...",
      "dependencies": [],
      "risks": []
    }
  ]
}

## Now produce the final JSON only.
