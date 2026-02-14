# RRR Evidence Matrix (Schema-Strict, Grounded)

Return VALID JSON ONLY (no markdown outside JSON, no prose) that validates against:
- schemas/rrr_evidence_matrix.schema.json
- schemas/common.json

## Required top-level keys
job_id, spec_id, generated_at, solutions

## Core rule for evidence typing
For EACH solution row:
- Use EvidenceNote ONLY if you can provide 1–3 valid citations that DIRECTLY support the mechanism.
- Otherwise use NoEvidence with:
  evidence.quality = "none"
  evidence.rationale = "No supporting evidence found in allowed sources."
  evidence.citations = []

## Forbidden keys
Do NOT include a "type" field anywhere.

## Field semantics (MUST be distinct)
- mechanism (string, REQUIRED, NEVER blank)
  - If evidence.quality != "none": 1–2 sentences of causal chain:
    Action → intermediate change → outcome(s)
    Must be supported by citations.
  - If evidence.quality == "none": mechanism MUST start with "Hypothesis:" and be exactly 1 sentence.
    Must NOT claim proven effects.

- evidence.rationale (string)
  - If EvidenceNote: 1–3 sentences describing what the cited sources report:
    setting/context + what was observed/measured + key limitation.
  - Must NOT restate the causal chain wording from mechanism.
  - If NoEvidence: EXACT sentence:
    "No supporting evidence found in allowed sources."

## Evidence object must be EXACTLY one of:
A) EvidenceNote:
{
  "quality": "high" | "medium" | "low",
  "rationale": "<string>",
  "citations": [ <1 to 3 citations> ]
}
B) NoEvidence:
{
  "quality": "none",
  "rationale": "No supporting evidence found in allowed sources.",
  "citations": []
}

## Citations (STRICT)
- HARD CAP: max 3 citations per solution.
- If evidence.quality != "none": citations length MUST be 1–3.
- If evidence.quality == "none": citations MUST be [].
- Every citation MUST come from provided allowed_sources snippets.
- Each citation MUST include:
  - source_id (must match allowed_sources[].source_id)
  - source_title
  - locator (specific page/section/table/figure)
  - quote (1–3 sentences copied from snippet text that supports the mechanism)
  - AND at least ONE of: source_url OR doi OR isbn OR reference
    *If the snippet text lacks identifiers, pull source_url/doi/reference from allowed_sources metadata for that source_id.*

## Feasibility enum
feasibility_resource_constrained must be exactly:
"high" | "medium" | "low" | "unknown"
(Map "moderate" → "medium")

## Synonym matching (for snippet evaluation)
When judging snippet relevance, treat these as equivalent:
- Performance Contracts and Scorecards: performance agreements, appraisal, balanced scorecard, KPIs, performance monitoring
- Attendance Monitoring and Verification: attendance tracking, presence verification, biometric attendance, absenteeism monitoring
- Non-financial incentives: recognition, awards, career progression, promotion pathways, training opportunities, professional development
- Supportive Supervision: mentoring, coaching, clinical supervision, on-the-job training
- Financial Incentives: salary supplements, allowances, bonuses, performance-based payments
- Housing and Transport: accommodation, transportation support, logistics/infrastructure support

## Grounding threshold (avoid false “NoEvidence” but prevent overclaim)
- EvidenceNote is allowed if the snippet explicitly links the intervention (or synonym) to at least ONE relevant outcome:
  motivation, retention/attrition, absenteeism/attendance, productivity/time use, performance/service quality.
- If a snippet only mentions the topic with no outcome link, it is NOT sufficient for EvidenceNote.

## Output discipline
- JSON ONLY.
- Keep risks as an array of strings (0–3 items), grounded when possible.
- implementation_notes: 1–3 concrete steps; if not supported by sources, keep generic but plausible.

## Inputs you will receive
- spec_id (string)
- solutions: [{ solution_id, solution, mechanism (optional) }]
- allowed_sources: list of sources with source_id, title, and possibly source_url/doi/reference
- retrieved_snippets: text chunks with source_id, source_title, locator, text

## Output JSON shape
{
  "job_id": "rrr_evidence_matrix",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "solutions": [
    {
      "solution_id": "...",
      "solution": "...",
      "mechanism": "...",
      "evidence": { ...EvidenceNote or NoEvidence... },
      "feasibility_resource_constrained": "unknown",
      "risks": [],
      "implementation_notes": ""
    }
  ]
}

