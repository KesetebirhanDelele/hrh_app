# RRR Evidence Matrix (Schema-Strict, Grounded)

Return VALID JSON ONLY (no markdown outside JSON, no prose) that validates against:
- schemas/rrr_evidence_matrix.schema.json
- schemas/common.json

## Required top-level keys
job_id, spec_id, generated_at, solutions

CRITICAL: generated_at MUST be today's date in YYYY-MM-DD format. Do NOT guess or use a training-data date.

## Core rule for evidence typing
For EACH solution row, carefully scan ALL provided snippets (using synonym matching below).
- Use EvidenceNote if ANY snippet links the intervention (or a synonym) to a relevant outcome.
- Only use NoEvidence if, after scanning ALL snippets with synonym matching, you genuinely find ZERO outcome-linked mentions.

Most health workforce sources discuss multiple interventions. Expect to find evidence for MOST solutions — not just one or two.

## Forbidden keys
Do NOT include a "type" field anywhere in the output.

## Field semantics (MUST be distinct — read carefully)

### mechanism (string, REQUIRED, NEVER blank)
- If evidence.quality != "none": 1–2 sentences describing a CAUSAL CHAIN:
  Action → intermediate change → outcome(s).
  Example: "Structured checklists during supervisory visits standardize clinical practice expectations, which increases protocol adherence and reduces variation in service quality."
- If evidence.quality == "none": MUST start with "Hypothesis:" (1 sentence, no proven effects).
  Example: "Hypothesis: Community scorecards may increase accountability by making provider attendance publicly visible."
- mechanism must NEVER repeat the same wording as evidence.rationale.

### evidence.rationale (string)
- If EvidenceNote: 1–3 sentences about what the CITED SOURCES report:
  study design/type + setting/country + specific finding + key limitation.
  Example: "A cross-sectional study of Ethiopian HEWs found that supervisors using checklists improved protocol adherence by 23% (SRC5, p. 68). Limitation: no control group."
- Must NOT restate the causal chain from mechanism. Different purpose:
  - mechanism = HOW IT WORKS (theory of change)
  - rationale = WHAT THE EVIDENCE SHOWS (empirical findings)
- If NoEvidence: EXACT text: "No supporting evidence found in allowed sources."

## Evidence object — EXACTLY one of:
A) EvidenceNote:
{
  "quality": "high" | "medium" | "low",
  "rationale": "<empirical findings, NOT mechanism rewording>",
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
- Every citation MUST come from provided allowed_sources snippets. Do NOT invent citations.
- Each citation MUST include:
  - source_id (must match allowed_sources[].source_id)
  - source_title
  - locator (specific page/section/table/figure)
  - quote (1–3 sentences COPIED from snippet text that supports the mechanism)
  - AND at least ONE of: source_url OR doi OR isbn OR reference
    *If the snippet text lacks identifiers, pull source_url/doi/reference from allowed_sources metadata for that source_id.*
- Prioritize Ethiopia-specific or LMIC/primary-care sources.
- If more than 3 sources apply, choose the 3 most direct and specific.

## Feasibility enum
feasibility_resource_constrained must be exactly:
"high" | "medium" | "low" | "unknown"
(Map "moderate" → "medium". Use "unknown" ONLY if no evidence at all.)

## Synonym matching (CRITICAL — use when scanning snippets)
When judging snippet relevance, treat these terms as equivalent:
- Supportive Supervision and Coaching: mentoring, coaching, clinical supervision, on-the-job training, supportive supervision, supervisory visits, feedback from supervisors
- Performance Contracts and Scorecards: performance agreements, performance appraisal, balanced scorecard, KPIs, performance monitoring, performance review, performance management
- Attendance Monitoring and Verification: attendance tracking, presence verification, biometric attendance, absenteeism monitoring, absenteeism, attendance
- Financial Incentives and Allowances: salary supplements, allowances, bonuses, performance-based payments, salary, remuneration, compensation, pay
- Non-Financial Incentives, Recognition, and Career Path: recognition, awards, career progression, promotion pathways, training opportunities, professional development, career ladder, motivation (non-monetary)
- Housing, Safety, and Transport Solutions: accommodation, transportation support, housing, safety, logistics support, infrastructure
- Task Shifting and Task Redesign: task sharing, role delegation, scope of practice, workload redistribution
- Digital Tools, Decision Support, and Scheduling: mHealth, eCHIS, digital health, mobile tools, decision support, scheduling systems, electronic records
- Community Accountability Mechanisms: community monitoring, social accountability, community governance, community health committees, citizen oversight
- Supply Chain and Job Aids Improvements: supply chain, drug supply, commodity availability, job aids, checklists, reference materials, stock-outs

## Grounding threshold
- EvidenceNote is REQUIRED if a snippet explicitly links the intervention (or synonym) to at least ONE relevant outcome: motivation, retention/attrition, absenteeism/attendance, productivity/time use, performance/service quality.
- If a snippet only mentions the topic with NO outcome link, it is not sufficient.
- Do NOT default to NoEvidence out of caution. If you find an outcome-linked snippet, you MUST use EvidenceNote.

## Field type constraints (STRICT)
- implementation_notes MUST be a single STRING (not an array/list).
  If you need bullets, embed them inside the string using newlines:
  "implementation_notes": "- Step 1...\n- Step 2...\n- Step 3..."
- risks MUST be an array of strings, 1–3 items when evidence.quality != "none".
  Only use [] if evidence.quality == "none".
- mechanism MUST be a string (never blank, never an array).

## Output discipline
- JSON ONLY. No markdown outside JSON.
- If a claim about effectiveness cannot be supported by allowed_sources, use NoEvidence.
- Do NOT invent citations or source_ids.

## Inputs you will receive
- spec_id (string)
- solutions: [{ solution_id, solution, mechanism (may be empty — you must fill it) }]
- allowed_sources: list of sources with source_id, title, snippets, and possibly source_url/doi/reference

## Output JSON shape
{
  "job_id": "rrr_evidence_matrix",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "solutions": [
    {
      "solution_id": "...",
      "solution": "...",
      "mechanism": "<causal chain or Hypothesis:...>",
      "evidence": { ...EvidenceNote or NoEvidence... },
      "feasibility_resource_constrained": "high|medium|low|unknown",
      "risks": ["risk 1", "risk 2"],
      "implementation_notes": "- Step 1...\n- Step 2..."
    }
  ]
}

## Now produce the final JSON only.
