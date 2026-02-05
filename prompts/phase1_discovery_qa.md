# Phase 1 Discovery Q&A (Schema-Strict)

You are generating a JSON output that MUST validate against:
- schemas/phase1_discovery_qa.schema.json
and shared definitions:
- schemas/common.json

## Output rules (non-negotiable)
1) Output MUST be valid JSON and MUST be the ONLY thing you output.
   - No markdown fences, no commentary, no extra keys.
2) Follow the schema exactly:
   - Top-level required keys: job_id, spec_id, generated_at, country, questions
3) Evidence requirements:
   - Every question item MUST include "evidence".
   - If you have supporting sources, use EvidenceNote with citations[].
   - If you do NOT have supporting sources, use NoEvidence:
     - quality = "none"
     - rationale explains what you checked and why evidence is missing
     - citations must be an empty array (or omitted; but prefer empty array)

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

Additional formatting rules:
- If you include `published_date`, it MUST be in ISO `YYYY-MM-DD`. If you only know year-month, either:
  - omit `published_date`, OR
  - set the day to "01" (e.g., 2021-04-01) and mention uncertainty in `rationale`.
- Optional fields (use when available): `source_type`, `authors`, `publisher`, `quote`

4) Be factual. If unknown, say so clearly in "answer" and use NoEvidence.

## Inputs you will receive
- country_name (string)
- country_iso3 (string, optional)
- spec_id (string)
- questions: list of objects each with:
  - question_id
  - question

## JSON shape to produce (template)
{
  "job_id": "phase1_discovery_qa",
  "spec_id": "<spec_id>",
  "generated_at": "YYYY-MM-DD",
  "country": { "name": "<country_name>", "iso3": "<ISO3 if provided>" },
  "questions": [
    {
      "question_id": "<question_id>",
      "question": "<question text>",
      "answer": "<your answer>",
      "evidence": {
        "quality": "high|medium|low",
        "rationale": "<why this quality>",
        "citations": [
          {
            "source_title": "<title>",
            "locator": "<page/section/table>",
            "source_url": "<https://... if available>",
            "published_date": "YYYY-MM-DD (if known)",
            "quote": "<optional short excerpt>"
          },
          {
            "source_title": "<report/book title without URL>",
            "locator": "<page/section>",
            "reference": "<Full citation: Author(s). Title. Publisher, Year.>",
            "published_date": "YYYY-MM-DD (if known)"
          }
        ]
      },
      "tags": ["<optional tags>"]
    }
  ]
}

## If no evidence is available for a question, use this instead:
"evidence": {
  "quality": "none",
  "rationale": "No supporting sources were available in the provided context for this claim; searched <X> and found <Y>.",
  "citations": []
}

## Now produce the final JSON only.
