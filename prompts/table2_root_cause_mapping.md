# Table 2 Root Cause Mapping (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/table2_root_cause_mapping.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, framework_items
- Each framework_items[] entry MUST include evidence (EvidenceNote or NoEvidence).
- Use EvidenceNote ONLY if you have at least one valid citation after applying citation rules; otherwise use NoEvidence.

## Grounding requirements (CRITICAL)
For each framework item:
- definition MUST be concise, operational, and evidence-grounded (how it manifests in practice based on source context).
- If allowed_sources are provided, try to ground definitions in source context:
  - Look for examples, case studies, or contextual information in sources that illustrate the root cause
  - Synthesize information from multiple sources if needed
  - Direct quotes supporting the definition are strongly preferred
- evidence.rationale MUST explain how the definition is grounded in sources
- Only use NoEvidence if you genuinely cannot find ANY relevant context in allowed_sources
- locator MUST be specific (page/section/table/figure). Avoid "general discussion" or "entire document".

### DETAIL & GRANULARITY (CRITICAL)
- When source snippets contain tables, data breakdowns, or structured lists:
  - REPRODUCE the table or list in your definition (use markdown table format)
  - Include ALL rows and columns — do NOT summarize or condense
  - Preserve specific numbers, percentages, and contextual details
- Definitions should be detailed (3–8 sentences), grounded in specific source context
- Include concrete examples, case studies, or data points from the sources
- If sources contain quantitative data about the root cause, include the specific figures

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
- quote (short excerpt 1–3 sentences supporting the definition or mapping)

If you cannot provide any identifier, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs:
- Every citation MUST include `source_id` matching one of `allowed_sources[].source_id` (e.g., SRC1, SRC2)
- You may ONLY cite from `allowed_sources`. Do not invent or reference sources outside this list.
- Look for ANY relevant information in allowed_sources that helps ground the definition:
  - Examples, case studies, or contextual descriptions
  - Evidence of the root cause manifesting in practice
  - Related factors or mechanisms mentioned in sources
- Use EvidenceNote when sources provide relevant context, even if indirect
- Only use NoEvidence if you truly cannot find ANY relevant information in the allowed sources

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
      "definition": "Operational definition grounded in source context...",
      "evidence": {
        "quality": "medium",
        "rationale": "Grounded in [source context/examples]...",
        "citations": [
          {
            "source_id": "SRC1",
            "source_title": "...",
            "locator": "Page X, Section Y",
            "reference": "...",
            "quote": "Relevant excerpt supporting the definition..."
          }
        ]
      },
      "tags": ["relevant", "tags"]
    }
  ]
}

## Now produce the final JSON only.
