# Table 2 Root Cause Mapping (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/table2_root_cause_mapping.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, framework_items
- Each framework_items[] entry MUST include evidence (EvidenceNote or NoEvidence).

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

## Inputs you will receive
- spec_id (string)
- framework_items: list with fields like item_id/category/root_cause/definition (or similar)

## JSON template (shape)
{
  "job_id": "table2_root_cause_mapping",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "framework_items": [
    {
      "item_id": "...",
      "category": "...",
      "root_cause": "...",
      "definition": "...",
      "evidence": { "quality": "none", "rationale": "...", "citations": [] },
      "tags": []
    }
  ]
}

## Now produce the final JSON only.
