# Phase 1 Discovery Q&A (Schema-Strict)

You are generating a JSON output that MUST validate against:
- schemas/phase1_discovery_qa.schema.json
- schemas/common.json

## Output rules (non-negotiable)
1) Output MUST be valid JSON and MUST be the ONLY thing you output.
   - No markdown fences, no commentary, no extra keys.
2) Follow the schema exactly:
   - Top-level required keys: job_id, spec_id, generated_at, country, questions
3) Evidence requirements:
   - Every question item MUST include "evidence".
   - Use EvidenceNote ONLY when you have at least one valid citation after applying the citation rules below.
   - If you do NOT have at least one valid citation, you MUST use NoEvidence:
     - quality = "none"
     - rationale explains what you checked in allowed_sources and why evidence is missing
     - citations = []

4) Be factual. If unknown, say so clearly in "answer" and use NoEvidence.

### Date formatting (strict)
- generated_at MUST be "YYYY-MM-DD"
- If you include published_date, it MUST be "YYYY-MM-DD"
  - If you only know year-month, either omit published_date OR set day to "01" and mention uncertainty in evidence.rationale.

---

## Grounding & specificity requirements (CRITICAL)
When writing "answer":
- Prefer concrete, checkable statements.
- If the question asks for "determinants", "drivers", "factors", "causes", or "barriers":
  - Your answer MUST include a bullet list of 5–10 determinants grouped under 3+ headings (e.g., Management, Working Conditions, Incentives, Personal/Household constraints).
  - Each determinant MUST be supported by at least one citation OR you must clearly mark it as "not evidenced in allowed_sources" and then use NoEvidence overall if no determinants can be cited.
- Avoid vague claims like “studies show…” without a locator and quote. If you cannot ground it, use NoEvidence.

### DETAIL & GRANULARITY (CRITICAL)
- When source snippets contain tables, data breakdowns, or structured lists:
  - REPRODUCE the table or list in your answer (use markdown table format)
  - Include ALL rows and columns — do NOT summarize or condense
  - Preserve specific numbers, dates, percentages, and targets
- When a question asks about staffing, allocation, or workforce:
  - Include specific cadre names, numbers, ratios, and year-by-year targets if available
  - Quote relevant tables verbatim from the sources
- Answers should be 3–10 paragraphs with specific details, NOT 1–2 sentence summaries
- If a source has a relevant table, your answer MUST include it

### CITATIONS (URL optional; traceability required)
Each citation object MUST include:
- source_title (string)
- locator (string) — MUST be specific (e.g., "p. 12", "Table 3, p. 19", "Section 2.1", "Annex A", "Figure 4")
And MUST include at least ONE of:
- source_url (valid http/https URL), OR
- reference (non-empty grey literature/book/report reference), OR
- doi, OR
- isbn

Strongly preferred (when possible):
- quote (short excerpt, 1–3 sentences) that directly supports the claim

If you cannot provide any of the above identifiers, do NOT include the citation.
If you have no citations after applying the rule, you MUST use NoEvidence (quality="none", citations=[]).

### ALLOWED SOURCES POLICY
If `allowed_sources` are provided in inputs:
- Every citation MUST include:
  - source_id: must match one of allowed_sources[].source_id (e.g., "SRC1")
- You may ONLY cite from allowed_sources.
- Do NOT invent sources or cite outside the list.
- If allowed_sources do not support the claim, use NoEvidence.

---

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
        "rationale": "<why this quality + what was checked>",
        "citations": [
          {
            "source_id": "SRC1",
            "source_title": "<title>",
            "locator": "<page/section/table/figure>",
            "source_url": "<https://... if available>",
            "reference": "<Full citation string if no URL>",
            "doi": "<DOI if applicable>",
            "isbn": "<ISBN if applicable>",
            "published_date": "YYYY-MM-DD (optional)",
            "quote": "<optional short excerpt>"
          }
        ]
      },
      "tags": ["<optional tags>"]
    }
  ]
}

## If no evidence is available for a question, use this:
"evidence": {
  "quality": "none",
  "rationale": "No supporting sources were available in allowed_sources for this claim; checked <X> sources and found no explicit support for <Y>.",
  "citations": []
}

## Now produce the final JSON only.
