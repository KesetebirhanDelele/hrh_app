# HRH App

Human Resources for Health (HRH) evidence extraction and analysis tool. Uses LLM-powered document analysis to extract structured evidence from source documents and render decision-ready deliverables (Excel, Word, Markdown) for country health workforce assessments.

## Contents

- [Quickstart](#quickstart)
- [Jobs Overview](#jobs-overview)
- [Domain Lessons Extraction Pipeline](#domain-lessons-extraction-pipeline)
- [Running a Job](#running-a-job)
- [Sources and RAG](#sources-and-rag)
- [Rendering Outputs](#rendering-outputs)
- [Multi-Country Batch Analysis](#multi-country-batch-analysis)
- [Environment Variables](#environment-variables)
- [CLI Reference](#cli-reference)
- [Development](#development)

---

## Quickstart

### 1. Create environment

```bash
# conda (recommended)
conda create -n hrh_app python=3.10
conda activate hrh_app

# or venv
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

### 2. Install

```bash
pip install -e .
```

### 3. Configure credentials

```bash
# Required
export HRH_LLM_PROVIDER=openai
export OPENAI_API_KEY=your-key

# Windows PowerShell
$env:HRH_LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your-key"
```

### 4. Run a job

```bash
# Grounded extraction with source documents
python -m app.app run \
  --job domain_lessons_option_b \
  --mode llm_planned \
  --spec-id domain_lessons_option_b_v2 \
  --country-name "Global" \
  --sources data/sources/global_sources.json

# Render Excel MENU output
python -m app.app render-xlsx \
  --job domain_lessons_option_b \
  --file outputs/domain_lessons_option_b/Global_20260320_120000/output_llm_planned.json
```

### 5. Run tests

```bash
pytest -q
```

---

## Jobs Overview

| Job ID | Description | Output formats | Mode |
|--------|-------------|----------------|------|
| `domain_lessons_option_b` | 10-category HRH evidence extraction → 10-column lean MENU + CITATIONS | json, xlsx | `llm_planned` |
| `domain_solutions_from_evidence` | Solution extraction by HRH domain | json, xlsx | `llm` / `llm_planned` |
| `phase1_discovery_qa` | Discovery Q&A for country assessment | json, md, docx | `llm` / `stub` |
| `rrr_evidence_matrix` | RRR solutions evidence matrix | json, md, xlsx | `llm` / `stub` |
| `table2_root_cause_mapping` | Root cause framework mapping | json, md, xlsx | `llm` / `stub` |
| `table3_intervention_framework` | Integrated intervention framework | json, md, xlsx | `llm` / `stub` |
| `benchmark_country_scoring` | Benchmark country scoring | json, md, xlsx | `llm` / `stub` |
| `country_learning_briefs` | Country learning domain briefs | json, md, docx | `llm` / `stub` |

The primary production job is **`domain_lessons_option_b`** with `--mode llm_planned`. All other jobs use `--mode llm` or `--mode stub`.

---

## Domain Lessons Extraction Pipeline

`domain_lessons_option_b` is the most complex job. It runs a multi-stage planned extraction pipeline:

### Extraction modes

| Mode | Description |
|------|-------------|
| `stub` | Returns synthetic hardcoded output. No LLM or source files needed. |
| `llm` | Single LLM call with all provided source excerpts. |
| `llm_planned` | Multi-stage pipeline: planner → batched extractor → expansion sweep → delta sweep → merge. |

### llm_planned pipeline stages

```
Stage 1 — Planner
  Reads all source excerpts and assigns locators to extraction batches.
  Groups by source document; up to 10 excerpts per batch.

Stage 1.5 — Keyword enforcement (optional)
  Checks batches against keyword families (supervision, incentives, etc.)
  Ensures evidence-rich excerpts are included.

Stage 2 — Batched extractor
  For each batch: calls LLM with the rendered prompt + batch excerpts.
  Validates output against domain_lessons_option_b.schema.json.
  Schema failures trigger up to 3 repair attempts with error feedback.

Stage 2.5 — Expansion sweep (auto-triggered)
  If fewer than 5 locators cited after extraction AND batch has ≥8 locators,
  runs a second LLM call on the same batch with an expansion suffix prompt.

Stage 3 — Locator delta sweep (auto-triggered)
  If cited locators < min(5, ceil(total * 0.5)) after expansion,
  runs targeted single-locator LLM calls for uncited excerpts.
  Prioritises locators with the most keyword-family hits.
  Capped at 6 delta calls per batch.

Stage 4 — Merge
  Merges all batch payloads (original + expansion + delta) into one output.
  Deduplication key: normalised(title) + evidence_type.
  Citations merged and capped at 5 per item.
  Intervention IDs assigned deterministically after merge.
```

### Coverage logging

Every batch emits coverage log lines:
```
[COVERAGE] batch 1: 4/8 locators cited after extraction
[EXPANSION] batch 1: 4 cited / 8 available — running expansion sweep...
[COVERAGE] batch 1: 6/8 locators cited after expansion
[DELTA SWEEP] batch 1: cited=6 < threshold=4; sweeping 2/2 uncited locators
[DELTA SWEEP] batch 1: swept 2; ~3 items added; newly cited: ['p.12', 'p.15']
[COVERAGE] batch 1: 8/8 locators cited FINAL
```

### Running domain_lessons_option_b

```powershell
# Global sources (production)
python -m app.app run `
  --job domain_lessons_option_b `
  --mode llm_planned `
  --spec-id domain_lessons_option_b_v2 `
  --country-name "Global" `
  --sources data/sources/global_sources.json

# Ethiopia sources
python -m app.app run `
  --job domain_lessons_option_b `
  --mode llm_planned `
  --spec-id domain_lessons_option_b_v2 `
  --country-name "Ethiopia" `
  --country-iso3 ETH `
  --sources data/sources/eth_sources.json

# Render Excel MENU output
python -m app.app render-xlsx `
  --job domain_lessons_option_b `
  --file outputs/domain_lessons_option_b/ETH_20260320_120000/output_llm_planned.json
```

### MENU output (Excel)

The rendered XLSX contains two sheets:

**MENU sheet — 10-column lean sheet; one row per proven intervention or recommendation:**

| # | Column | Source |
|---|--------|--------|
| 1 | Intervention ID | Computed at render time: `{d_id[:3]}_{fa_id[:6]}_{status_abbrev}_{n:03d}` |
| 2 | Title | `item.title` |
| 3 | HRH-II Package Component | `domain_id → focus_area_id` |
| 4 | Description | `item.statement` |
| 5 | Evidence status | `proven` (from `proven_interventions`) or `recommendation_only` (from `recommendations`) |
| 6 | Strength of evidence | `item.evidence_strength` |
| 7 | Evidence design/type | `item.evidence_design_type` (default: `"unknown"`) |
| 8 | Target cadre & setting | `item.target_cadre_setting` (default: `"unspecified"`) |
| 9 | Implementation considerations | `item.intervention_risks` bullet list (item-anchored only) |
| 10 | Expected impact | `item.expected_impact` (fallback: `"Observed: {statement}"` or `"Intended to: {statement}"`) |

**CITATIONS sheet — one row per citation from MENU rows (5 columns):**
`Intervention ID | doc_id | source_title | locator | snippet`

**MENU eligibility rules:**
- Only `proven_interventions` and `recommendations` produce MENU rows
- Items with `evidence_type = determinant_mechanism` are excluded even if in `proven_interventions`
- Every MENU row must have ≥1 citation
- Evidence status is derived from the source category array, not the `evidence_type` field

---

## Sources and RAG

### Sources JSON format

The `--sources` flag points to a JSON file that lists source documents with pre-extracted snippets. This grounds the extraction — the LLM can only cite documents in this list.

```json
{
  "sources": [
    {
      "source_id": "SRC1",
      "source_title": "Ethiopia Health Sector Transformation Plan II",
      "reference": "Federal Ministry of Health (Ethiopia). HSTP II, 2020/21–2024/25.",
      "published_date": "2021-01-01",
      "snippets": [
        {
          "locator": "Section 4.2, p. 45",
          "text": "Exact text from the document..."
        }
      ]
    }
  ]
}
```

### Auto-generate sources from PDF/DOCX files

```bash
# Scan PDF/DOCX files in data/sources/ETH/
python -m app.app sources-scan --country-iso3 ETH
# → writes data/sources/eth_sources.json

# Or scan without text extraction (metadata only)
python -m app.app sources-scan --country-iso3 ETH --no-extract
```

### Build a vector search index (RAG)

```bash
python -m app.app sources-index \
  --sources data/sources/eth_sources.json \
  --output data/sources/eth_index.json
```

The RAG index is used in `llm` mode to retrieve the most relevant excerpts per query before each LLM call. In `llm_planned` mode the planner assigns excerpts directly.

---

## Rendering Outputs

All render commands accept `--file` (path to JSON output) and optional `--out` (output path).

```bash
# Markdown
python -m app.app render-md \
  --job domain_lessons_option_b \
  --file outputs/domain_lessons_option_b/ETH_20260320_120000/output_llm_planned.json

# Excel
python -m app.app render-xlsx \
  --job domain_lessons_option_b \
  --file outputs/domain_lessons_option_b/ETH_20260320_120000/output_llm_planned.json

# Word
python -m app.app render-docx \
  --job phase1_discovery_qa \
  --file outputs/phase1_discovery_qa/ETH_20260320_120000/output_llm.json

# Render all formats for all jobs at once
python -m app.app render-all --mode llm --country-name Ethiopia --country-iso3 ETH
```

---

## Multi-Country Batch Analysis

### PowerShell batch script

```powershell
.\run_all_countries.ps1
```

The script auto-discovers all ISO3 country folders under `data/sources/`, generates sources JSON files, runs all jobs with LLM, and renders all outputs. No configuration needed — just add a new `data/sources/{ISO3}/` folder.

**Folder layout required:**
```
data/sources/
├── ETH/
│   ├── pdf/
│   └── docx/
├── KEN/
│   ├── pdf/
│   └── docx/
```

**Output structure:**
```
outputs/
  domain_lessons_option_b/
    ETH_20260320_120000/
      output_llm_planned.json
      output_llm_planned.xlsx
    KEN_20260320_130000/
      output_llm_planned.json
      output_llm_planned.xlsx
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `HRH_LLM_PROVIDER` | Must be `openai` |
| `OPENAI_API_KEY` | OpenAI API key |

### Model

| Variable | Default | Description |
|----------|---------|-------------|
| `HRH_OPENAI_MODEL` | `gpt-4o` | OpenAI model for extraction |

### Rate limiting and retries

| Variable | Default | Description |
|----------|---------|-------------|
| `HRH_RL_BACKOFF_BASE_SECONDS` | `1.0` | Base backoff on 429 RateLimitError |
| `HRH_RL_BACKOFF_MAX_SECONDS` | `30.0` | Max backoff cap |
| `HRH_RL_JITTER_SECONDS` | `1.0` | Random jitter added to backoff |
| `HRH_RL_MAX_RETRIES` | `5` | Max retry attempts per LLM call |
| `HRH_SOFT_RPS` | _(disabled)_ | Soft request-per-second limit (pre-call sleep) |

Sleeps only occur on actual 429/connection errors. Successful calls never sleep.

### Extraction tuning (llm_planned mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `HRH_MAX_EXCERPTS_PER_CALL` | `10` | Max excerpt snippets per extractor batch |
| `HRH_MAX_CHARS_PER_CALL` | `16000` | Max total chars per extractor batch |
| `HRH_MAX_EXTRACT_BATCHES_PER_SOURCE` | `10` | Max extraction batches per source document |
| `HRH_MAX_DELTA_CALLS_PER_SOURCE` | `6` | Max locator delta sweep calls per batch |
| `HRH_SKIP_EXPANSION_WHEN_DELTA` | `1` | Skip expansion pass if delta sweep will run |

### RAG retrieval

| Variable | Default | Description |
|----------|---------|-------------|
| `HRH_RAG_TOP_K` | `40` | Number of excerpts retrieved per RAG query |

### Validation

| Variable | Description |
|----------|-------------|
| `HRH_STRICT_CITATIONS` | `1` = require source_url / doi / isbn / reference on every citation |
| `HRH_ENFORCE_ALLOWED_SOURCES` | Auto-set when `--sources` used. Requires `source_id` on all citations |
| `HRH_ALLOWED_SOURCE_IDS` | Comma-separated list of valid source IDs (auto-set from sources file) |

---

## CLI Reference

```
python -m app.app <command> [options]
```

| Command | Key options | Purpose |
|---------|------------|---------|
| `run` | `--job`, `--mode`, `--spec-id`, `--country-name`, `--country-iso3`, `--sources`, `--index` | Run one job |
| `run-all` | `--mode`, `--spec-id`, `--country-name`, `--country-iso3`, `--sources` | Run all jobs |
| `render-md` | `--job`, `--file`, `--out` | Render JSON → Markdown |
| `render-xlsx` | `--job`, `--file`, `--out` | Render JSON → Excel |
| `render-docx` | `--job`, `--file`, `--out` | Render JSON → Word |
| `render-all` | `--mode`, `--country-name`, `--country-iso3` | Render all jobs |
| `validate` | `--job`, `--file` | Validate JSON against schema |
| `sources-scan` | `--country-iso3`, `--no-extract` | Scan PDF/DOCX → sources JSON |
| `sources-index` | `--sources`, `--output` | Build RAG embedding index |

---

## Output Folder Structure

```
outputs/
  {job_id}/
    {COUNTRY}_{TIMESTAMP}/
      output_{mode}.json
      output_{mode}.md
      output_{mode}.xlsx
      output_{mode}.docx
```

- `COUNTRY`: ISO3 code (ETH) or country name (Ethiopia) or `run` if unspecified
- `TIMESTAMP`: UTC datetime `YYYYMMDD_HHMMSS`
- `mode`: `llm`, `llm_planned`, or `stub`

---

## Project Structure

```
hrh_app/
├── app/
│   ├── app.py                  # CLI entry point + all pipeline orchestration
│   ├── analyze/
│   │   ├── llm.py              # OpenAI integration + adaptive rate limiting
│   │   ├── prompting.py        # Prompt template rendering
│   │   ├── extractors.py       # Spec parsers per job type
│   │   ├── merger.py           # Multi-batch output merging + deduplication
│   │   └── runner.py           # Orchestration helpers
│   ├── core/
│   │   └── validators.py       # JSON schema + semantic validation
│   ├── ingest/
│   │   ├── loader.py           # PDF/DOCX text extraction
│   │   ├── chunker.py          # Text chunking
│   │   └── indexer.py          # Embedding index builder
│   ├── jobs/
│   │   ├── registry.py         # Job registry loader
│   │   └── *_stub_runner.py    # Synthetic stub data per job
│   └── render/
│       ├── md.py               # Markdown renderer
│       ├── xlsx.py             # Excel renderer
│       └── docx.py             # Word renderer
├── configs/
│   └── job_registry.yaml       # Job definitions (spec, prompt, schema, output paths)
├── data/sources/               # Source documents (PDF/DOCX) and generated manifests
├── docs/                       # Architecture, specifications, and data model docs
├── outputs/                    # Generated outputs (gitignored)
├── prompts/                    # LLM prompt templates (Markdown)
├── schemas/                    # JSON output validation schemas
├── specs/                      # Job extraction specifications
├── tests/                      # pytest test suite (329 tests)
├── tools/
│   ├── comparator_index.py     # Country similarity scoring
│   └── similarity_index.py     # Simplified similarity index
├── pyproject.toml
├── run_all_countries.ps1       # Multi-country PowerShell batch script
└── README.md
```

---

## Development

```bash
# Run all tests
pytest -q

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_domain_lessons_option_b_schema.py -q

# Type check
mypy app/

# Lint
ruff check app/
```

**Detailed documentation:**
- [docs/architecture.md](docs/architecture.md) — system architecture, pipeline stages, design decisions
- [docs/specifications.md](docs/specifications.md) — job specifications and extraction rules
- [docs/datamodel.md](docs/datamodel.md) — JSON schema data model, field definitions, MENU columns
