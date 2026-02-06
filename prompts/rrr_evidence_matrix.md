# RRR Evidence Matrix (Schema-Strict)

You MUST output valid JSON ONLY (no markdown, no prose) that validates against:
- schemas/rrr_evidence_matrix.schema.json
- schemas/common.json

## Output rules
- Output must contain: job_id, spec_id, generated_at, solutions
- Each solutions[] row MUST include evidence:
  - Use EvidenceNote with citations[] if sources are available
  - Otherwise use NoEvidence with quality="none" and citations=[]

## STRICT CONSTRAINTS (must follow exactly)
- Do NOT include a "type" field anywhere in the output (evidence.type, citation.type, etc.). Those keys are forbidden.
- evidence must be EXACTLY one of:
  A) EvidenceNote:
     {
       "quality": "high" | "medium" | "low",
       "rationale": "<string>",
       "citations": [
         {
           "source_title": "<string>",
           "locator": "<string>",
           "source_url": "<valid https://... URL>" (if available),
           "reference": "<Full citation string>" (if no URL),
           "doi": "<DOI>" (if academic paper),
           "isbn": "<ISBN>" (if book),
           "published_date": "YYYY-MM-DD" (optional),
           "quote": "<string>" (optional)
         }
       ]
     }
     CRITICAL: Each citation MUST have at least ONE of: source_url, reference, doi, or isbn
  B) NoEvidence:
     {
       "quality": "none",
       "rationale": "<string>",
       "citations": []
     }

- feasibility_resource_constrained must be exactly one of:
  "high" | "medium" | "low" | "unknown"
  (Do NOT use "moderate". Map "moderate" to "medium".)

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string)
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

If you cannot provide any of the above identifiers, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs, every citation MUST include:
- `source_id`: must match one of `allowed_sources[].source_id` (e.g., SRC1, SRC2)
- You may ONLY cite from `allowed_sources`. Do not invent or reference sources outside this list.
- If you cannot find supporting evidence in `allowed_sources`, use NoEvidence.

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
