# HRH App

Human Resources for Health (HRH) analysis tool with LLM-powered evidence extraction and multi-format rendering.

## Quickstart

### 1. Create Environment

```bash
# Using conda (recommended)
conda create -n hrh_app python=3.10
conda activate hrh_app

# Or using venv
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -e .
```

### 3. Set Environment Variables

**Required:**
```bash
export HRH_LLM_PROVIDER=openai
export OPENAI_API_KEY=your-api-key-here
```

**Optional:**
```bash
# Enforce strict citation validation (requires source_url, reference, doi, or isbn)
export HRH_STRICT_CITATIONS=1

# Use a specific OpenAI model (default: gpt-4o-mini)
export HRH_OPENAI_MODEL=gpt-4o

# Note: When using --sources flag, HRH_ENFORCE_ALLOWED_SOURCES and HRH_ALLOWED_SOURCE_IDS
# are automatically set to validate citations reference only curated sources
```

**Windows (PowerShell):**
```powershell
$env:HRH_LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your-api-key-here"
$env:HRH_STRICT_CITATIONS="1"  # optional
```

### 4. Run Jobs

```bash
# Generate output using LLM
python -m app.app run --job phase1_discovery_qa --mode llm --spec-id phase1_ethiopia_v1 --country-name Ethiopia --country-iso3 ETH

# With curated sources (for grounded citations)
python -m app.app run --job phase1_discovery_qa --mode llm --spec-id phase1_ethiopia_v1 --country-name Ethiopia --country-iso3 ETH --sources data/sources/ethiopia_sources.json

# Or generate stub output (no LLM required)
python -m app.app run --job phase1_discovery_qa --mode stub --spec-id test_spec --country-name Ethiopia --country-iso3 ETH
```

### 5. Render Outputs

```bash
# Markdown (all jobs)
python -m app.app render-md --job phase1_discovery_qa --file outputs/phase1_discovery_qa/output_llm.json

# Excel (table jobs: rrr, table2, table3, benchmark)
python -m app.app render-xlsx --job rrr_evidence_matrix --file outputs/rrr_evidence_matrix/output_llm.json

# Word (narrative jobs: phase1, learning_briefs)
python -m app.app render-docx --job phase1_discovery_qa --file outputs/phase1_discovery_qa/output_llm.json
```

### 6. Run Tests

```bash
pytest -q
```

## Security

**⚠️ NEVER commit API keys or secrets to git**

- **`.env` files are optional** but MUST be in `.gitignore` if used
- Use environment variables for secrets (recommended)
- The `.gitignore` already excludes common secret files (`.env`, credentials, etc.)
- Generated outputs (`outputs/`, `*.json`) are excluded from git

## Available Jobs

| Job ID | Type | Description | Render Formats |
|--------|------|-------------|----------------|
| `phase1_discovery_qa` | Narrative | Discovery Q&A for country assessment | md, docx |
| `rrr_evidence_matrix` | Table | RRR evidence matrix for solutions | md, xlsx |
| `table2_root_cause_mapping` | Table | Root cause framework mapping | md, xlsx |
| `table3_intervention_framework` | Table | Integrated intervention framework | md, xlsx |
| `benchmark_country_scoring` | Table | Benchmark country scoring | md, xlsx |
| `country_learning_briefs` | Narrative | Country learning domain briefs | md, docx |

## Command Examples

### Phase 1 Discovery Q&A

**Stub mode (no LLM):**
```bash
python -m app.app run --job phase1_discovery_qa --mode stub --spec-id test_spec --country-name Ethiopia --country-iso3 ETH
```

**LLM mode:**
```bash
python -m app.app run --job phase1_discovery_qa --mode llm --spec-id phase1_ethiopia_v1 --country-name Ethiopia --country-iso3 ETH
```

**Render:**
```bash
python -m app.app render-md --job phase1_discovery_qa --file outputs/phase1_discovery_qa/output_llm.json
python -m app.app render-docx --job phase1_discovery_qa --file outputs/phase1_discovery_qa/output_llm.json
```

### RRR Evidence Matrix

**Stub mode:**
```bash
python -m app.app run --job rrr_evidence_matrix --mode stub --spec-id rrr_test
```

**LLM mode:**
```bash
python -m app.app run --job rrr_evidence_matrix --mode llm --spec-id rrr_resource_constrained_v1
```

**Render:**
```bash
python -m app.app render-md --job rrr_evidence_matrix --file outputs/rrr_evidence_matrix/output_llm.json
python -m app.app render-xlsx --job rrr_evidence_matrix --file outputs/rrr_evidence_matrix/output_llm.json
```

### Table 2: Root Cause Mapping

**Stub mode:**
```bash
python -m app.app run --job table2_root_cause_mapping --mode stub --spec-id table2_test
```

**LLM mode:**
```bash
python -m app.app run --job table2_root_cause_mapping --mode llm --spec-id table2_framework_v1
```

**Render:**
```bash
python -m app.app render-md --job table2_root_cause_mapping --file outputs/table2_root_cause_mapping/output_llm.json
python -m app.app render-xlsx --job table2_root_cause_mapping --file outputs/table2_root_cause_mapping/output_llm.json
```

### Table 3: Intervention Framework

**Stub mode:**
```bash
python -m app.app run --job table3_intervention_framework --mode stub --spec-id table3_test
```

**LLM mode:**
```bash
python -m app.app run --job table3_intervention_framework --mode llm --spec-id table3_interventions_v1
```

**Render:**
```bash
python -m app.app render-md --job table3_intervention_framework --file outputs/table3_intervention_framework/output_llm.json
python -m app.app render-xlsx --job table3_intervention_framework --file outputs/table3_intervention_framework/output_llm.json
```

### Benchmark Country Scoring

**Stub mode:**
```bash
python -m app.app run --job benchmark_country_scoring --mode stub --spec-id benchmark_test
```

**LLM mode:**
```bash
python -m app.app run --job benchmark_country_scoring --mode llm --spec-id benchmark_countries_v1
```

**Render:**
```bash
python -m app.app render-md --job benchmark_country_scoring --file outputs/benchmark_country_scoring/output_llm.json
python -m app.app render-xlsx --job benchmark_country_scoring --file outputs/benchmark_country_scoring/output_llm.json
```

### Country Learning Briefs

**Stub mode:**
```bash
python -m app.app run --job country_learning_briefs --mode stub --spec-id learning_test --country-name Ethiopia --country-iso3 ETH
```

**LLM mode:**
```bash
python -m app.app run --job country_learning_briefs --mode llm --spec-id learning_domains_v1 --country-name Ethiopia --country-iso3 ETH
```

**Render:**
```bash
python -m app.app render-md --job country_learning_briefs --file outputs/country_learning_briefs/output_llm.json
python -m app.app render-docx --job country_learning_briefs --file outputs/country_learning_briefs/output_llm.json
```

## Validate Existing Output

```bash
python -m app.app validate --job phase1_discovery_qa --file outputs/phase1_discovery_qa/output_llm.json
```

## Project Structure

```
hrh_app/
├── app/
│   ├── analyze/          # LLM integration
│   ├── core/             # Schema validation
│   ├── jobs/             # Job registry and execution
│   └── render/           # Output renderers (md, xlsx, docx)
├── configs/              # Job configurations
├── data/                 # Reference data
├── outputs/              # Generated outputs (gitignored)
├── prompts/              # LLM prompt templates
├── schemas/              # JSON schemas
├── specs/                # Job specifications
├── tests/                # Test suite
├── pyproject.toml        # Dependencies
└── README.md             # This file
```

## Citation Formats

The app supports multiple citation types to accommodate various source materials:

**Web sources:**
```json
{
  "source_title": "WHO Health Report 2024",
  "locator": "Chapter 3, page 45",
  "source_url": "https://www.who.int/reports/2024"
}
```

**Books:**
```json
{
  "source_title": "Health Systems in Low-Income Countries",
  "locator": "Chapter 7, pages 123-125",
  "isbn": "978-0-123456-78-9",
  "authors": "Smith, J. and Jones, A.",
  "publisher": "Oxford University Press"
}
```

**Grey literature/reports:**
```json
{
  "source_title": "Ethiopia National Health Workforce Assessment",
  "locator": "Section 4.2",
  "reference": "Ministry of Health, Ethiopia (2023). National Health Workforce Assessment Report."
}
```

**Academic papers:**
```json
{
  "source_title": "Impact of Task Shifting on Healthcare Quality",
  "locator": "Results section",
  "doi": "10.1016/j.healthpol.2024.01.234"
}
```

Every citation **must** include at least one identifier: `source_url`, `reference`, `doi`, or `isbn`.

## Curated Sources (Grounded Generation)

For better citation quality and grounding, you can provide a curated JSON file of trusted sources with snippets. The LLM will receive these as "ALLOWED SOURCES" in the prompt.

**Create a sources file** (e.g., `data/sources/ethiopia_sources.json`):
```json
{
  "sources": [
    {
      "source_id": "SRC1",
      "source_title": "Ethiopia Health Sector Transformation Plan II",
      "reference": "Federal Ministry of Health (Ethiopia). HSTP II, 2020/21–2024/25.",
      "published_date": "2021-01-01",
      "locator_hint": "HRH chapter / performance management sections",
      "snippets": [
        {
          "locator": "HRH section",
          "quote": "Your trusted excerpt from the document..."
        }
      ]
    }
  ]
}
```

**Use with any job:**
```bash
python -m app.app run --job phase1_discovery_qa --mode llm --spec-id phase1_ethiopia_v1 --country-name Ethiopia --country-iso3 ETH --sources data/sources/ethiopia_sources.json
```

**Benefits:**
- ✅ Manual curation ensures quality sources
- ✅ LLM sees relevant context without vector search complexity
- ✅ Citations can reference your trusted sources
- ✅ No need for embeddings or vector databases (yet)

**Source ID Enforcement:**

When you use the `--sources` flag, the app automatically enforces that all citations include a `source_id` field and that the ID matches one from your curated sources. This ensures:
- Citations are grounded in your trusted sources
- No hallucinated or invalid source references
- Full traceability from claims to source documents

The LLM receives an instruction to include `source_id` in citations, and validation will fail if:
- A citation is missing the `source_id` field
- A `source_id` doesn't match any ID in your sources file (e.g., SRC1, SRC2, etc.)

Example citation with source_id:
```json
{
  "source_id": "SRC1",
  "source_title": "Ethiopia Health Sector Transformation Plan II",
  "locator": "HRH section, page 45",
  "reference": "Federal Ministry of Health (Ethiopia). HSTP II, 2020/21–2024/25."
}
```

### Auto-Generate Sources from Files

The `sources-scan` command automatically creates a sources JSON file by scanning PDF and DOCX files in country-specific directories:

**1. Organize your source files:**
```
data/sources/
└── ETH/
    ├── pdf/
    │   ├── Ethiopia Health Sector Transformation Plan II.pdf
    │   └── HRH Strategic Plan 2016-2025.pdf
    └── docx/
        └── Health Extension Program Evaluation.docx
```

**2. Run the scan command:**
```bash
python -m app.app sources-scan --country-iso3 ETH
```

**3. Output:**
```
Scanned 3 file(s)
Wrote: data/sources/eth_sources.json
```

The generated JSON includes:
- `source_id`: Auto-numbered (SRC1, SRC2, etc.)
- `source_title`: Extracted from filename
- `source_type`: pdf or docx
- `file_path`: Relative path to the file
- `reference`: Auto-generated (editable)
- `snippets`: Empty array (add manually or via future extraction tools)

**Next steps:**
1. Edit the generated JSON to improve `reference` fields
2. Add `published_date` and other optional fields
3. Manually add `snippets` with relevant quotes (or use future extraction tools)
4. Use with `--sources` flag when running jobs

## Development

**Run tests with coverage:**
```bash
pytest --cov=app --cov-report=term-missing
```

**Type checking (if using mypy):**
```bash
mypy app/
```

**Linting:**
```bash
ruff check app/
```

## License

[Add license information]

## Contact

[Add contact information]
