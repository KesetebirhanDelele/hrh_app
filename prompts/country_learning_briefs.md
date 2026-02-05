# Country Learning Briefs (Schema-Strict)

Output MUST be valid JSON ONLY that validates against:
- schemas/country_learning_briefs.schema.json
- schemas/common.json

## Rules
- Output only JSON (no markdown/prose).
- Include: job_id, spec_id, generated_at, country, domains
- Each domains[] entry MUST include evidence (EvidenceNote or NoEvidence).

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
