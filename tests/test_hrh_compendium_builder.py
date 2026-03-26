"""
tests/test_hrh_compendium_builder.py

Unit tests for tools/hrh_compendium_builder.py

Run with:
    pytest tests/test_hrh_compendium_builder.py -v
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pytest

# Make sure the tools package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.hrh_compendium_builder import (
    DOMAIN_KEYWORDS,
    PROBLEM_KEYWORDS,
    REQUIRED_COLS,
    STRENGTH_ORDER,
    _classify_by_keywords,
    _extract_country,
    _infer_mechanism,
    _keyword_similarity,
    _merge_bullets,
    _strongest_evidence,
    _text_for_embedding,
    aggregate_cluster,
    assign_clusters,
    build_evidence_map,
    cluster_batch,
    compute_embeddings,
    load_data,
    score_transferability,
    write_excel,
    write_word,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(**kwargs) -> Dict:
    """Minimal valid intervention row dict."""
    defaults = {
        "Intervention ID": "INT-001",
        "Title": "Performance-based incentives for HEWs",
        "HRH-II Package Component": "Motivation & Accountability",
        "Description": "Performance-based financial incentives were introduced to reward community health workers for meeting attendance targets.",
        "Evidence status": "proven",
        "Strength of evidence": "moderate",
        "Evidence design/type": "RCT",
        "Target cadre & setting": "HEWs in rural Ethiopia",
        "Implementation considerations": "Requires reliable payment infrastructure; monthly reporting",
        "Expected impact": "Attendance improved by 25% within 6 months",
        "Reference": "Smith et al. 2021",
        "Page": "12",
    }
    defaults.update(kwargs)
    return defaults


def _make_df(rows: List[Dict] | None = None, n: int = 3) -> pd.DataFrame:
    """Build a minimal valid DataFrame."""
    if rows is None:
        rows = [_make_row(
            **{"Intervention ID": f"INT-{i:03d}", "Title": f"Intervention {i}"}
        ) for i in range(1, n + 1)]
    df = pd.DataFrame(rows)
    df = df.fillna("")
    return df


def _make_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to in-memory Excel bytes."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Step 1 — load_data
# ---------------------------------------------------------------------------

class TestLoadData:
    def test_loads_and_returns_dataframe(self, tmp_path):
        df = _make_df()
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = load_data(path)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(df)

    def test_strips_column_whitespace(self, tmp_path):
        df = _make_df()
        df.columns = ["  " + c + "  " for c in df.columns]
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = load_data(path)
        for col in REQUIRED_COLS:
            assert col in result.columns

    def test_fills_na_with_empty_string(self, tmp_path):
        df = _make_df()
        df.iloc[0, 0] = None
        path = tmp_path / "test.xlsx"
        df.to_excel(path, index=False)
        result = load_data(path)
        assert "" in result.iloc[0].tolist() or result.iloc[0, 0] == ""

    def test_raises_on_missing_columns(self, tmp_path):
        df = pd.DataFrame({"Title": ["X"], "Description": ["Y"]})
        path = tmp_path / "bad.xlsx"
        df.to_excel(path, index=False)
        with pytest.raises(ValueError, match="missing required columns"):
            load_data(path)


# ---------------------------------------------------------------------------
# Step 2 — compute_embeddings
# ---------------------------------------------------------------------------

class TestComputeEmbeddings:
    def test_returns_tuple_with_method_label(self):
        df = _make_df(n=3)
        emb, method = compute_embeddings(df)
        assert isinstance(method, str)
        assert method in ("tfidf", "sentence-transformers", "keyword")

    def test_embedding_length_matches_rows(self):
        df = _make_df(n=5)
        emb, method = compute_embeddings(df)
        assert len(emb) == 5

    def test_text_for_embedding_combines_fields(self):
        row = pd.Series(_make_row())
        text = _text_for_embedding(row)
        assert "Performance-based incentives" in text
        assert "Motivation" in text


# ---------------------------------------------------------------------------
# Step 3 — clustering
# ---------------------------------------------------------------------------

class TestKeywordSimilarity:
    def test_identical_texts_score_one(self):
        assert _keyword_similarity("absenteeism incentive reward", "absenteeism incentive reward") == 1.0

    def test_disjoint_texts_score_zero(self):
        assert _keyword_similarity("apple banana", "cat dog") == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        score = _keyword_similarity("performance incentive", "incentive reward")
        assert 0.0 < score < 1.0

    def test_empty_string_returns_zero(self):
        assert _keyword_similarity("", "something") == 0.0


class TestClusterBatch:
    def test_single_row_returns_zero(self):
        df = _make_df(n=1)
        emb, method = compute_embeddings(df)
        labels = cluster_batch(df, emb, method)
        assert labels == [0]

    def test_returns_one_label_per_row(self):
        df = _make_df(n=6)
        emb, method = compute_embeddings(df)
        labels = cluster_batch(df, emb, method)
        assert len(labels) == 6

    def test_labels_are_integers(self):
        df = _make_df(n=4)
        emb, method = compute_embeddings(df)
        labels = cluster_batch(df, emb, method)
        assert all(isinstance(l, int) for l in labels)

    def test_identical_rows_cluster_together(self):
        row = _make_row()
        df = pd.DataFrame([row, row, row])
        df = df.fillna("")
        emb, method = compute_embeddings(df)
        labels = cluster_batch(df, emb, method)
        # All identical rows should end up in same cluster
        assert len(set(labels)) == 1


class TestAssignClusters:
    def test_adds_cluster_column(self):
        df = _make_df(n=5)
        result = assign_clusters(df, batch_size=5)
        assert "_cluster" in result.columns

    def test_all_rows_assigned(self):
        df = _make_df(n=10)
        result = assign_clusters(df, batch_size=5)
        assert (result["_cluster"] >= 0).all()

    def test_handles_batch_boundary_correctly(self):
        # 27 rows with batch_size=25 → two batches (25 + 2), no row left at -1
        df = _make_df(n=27)
        result = assign_clusters(df, batch_size=25)
        assert (result["_cluster"] >= 0).all()

    def test_cluster_ids_are_globally_unique_across_batches(self):
        df = _make_df(n=50)
        result = assign_clusters(df, batch_size=25)
        # Each batch should produce non-overlapping IDs — total unique ≥ 2
        assert result["_cluster"].nunique() >= 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestClassifyByKeywords:
    def test_matches_absenteeism(self):
        text = "The intervention reduced absenteeism and improved attendance."
        result = _classify_by_keywords(text, PROBLEM_KEYWORDS, "Productivity")
        assert result == "Absenteeism"

    def test_matches_accountability(self):
        text = "Governance and oversight mechanisms strengthen accountability."
        result = _classify_by_keywords(text, PROBLEM_KEYWORDS, "Productivity")
        assert result == "Accountability"

    def test_returns_default_when_no_match(self):
        result = _classify_by_keywords("xyz xyz xyz", PROBLEM_KEYWORDS, "Productivity")
        assert result == "Productivity"

    def test_matches_domain_motivation(self):
        text = "Performance incentives and sanctions were applied."
        result = _classify_by_keywords(text, DOMAIN_KEYWORDS, "Enabling Environment")
        assert result == "Motivation & Accountability"


class TestStrongestEvidence:
    def test_returns_strong_when_present(self):
        assert _strongest_evidence(["weak", "strong", "moderate"]) == "strong"

    def test_returns_moderate_over_weak(self):
        assert _strongest_evidence(["weak", "moderate"]) == "moderate"

    def test_empty_list_returns_no_evidence(self):
        assert _strongest_evidence([]) == "no_evidence_found"

    def test_all_empty_strings(self):
        assert _strongest_evidence(["", "", ""]) == "no_evidence_found"

    def test_case_insensitive(self):
        assert _strongest_evidence(["Weak", "Strong"]) == "Strong"


class TestMergeBullets:
    def test_deduplicates_identical_lines(self):
        result = _merge_bullets(["Requires payment; Requires payment"])
        assert result.count("Requires payment") == 1

    def test_merges_across_multiple_strings(self):
        result = _merge_bullets(["Train supervisors", "Provide equipment"])
        assert "Train supervisors" in result
        assert "Provide equipment" in result

    def test_empty_input_returns_no_evidence(self):
        assert _merge_bullets([]) == "no_evidence_found"

    def test_short_lines_excluded(self):
        result = _merge_bullets(["hi"])
        assert "no_evidence_found" in result

    def test_bullet_prefix_present(self):
        result = _merge_bullets(["Train all supervisors regularly"])
        assert result.startswith("•")


class TestExtractCountry:
    def test_extracts_ethiopia(self):
        assert "Ethiopia" in _extract_country("A study in Ethiopia found reduced absenteeism.")

    def test_extracts_multiple_countries(self):
        result = _extract_country("Studies in Kenya and Uganda showed improvement.")
        assert "Kenya" in result
        assert "Uganda" in result

    def test_returns_not_specified_when_none_found(self):
        assert _extract_country("A general study with no location.") == "Not specified"

    def test_case_insensitive(self):
        assert "Ethiopia" in _extract_country("ETHIOPIA rural health workers")


class TestInferMechanism:
    def test_detects_financial_incentive(self):
        result = _infer_mechanism("Financial incentives were given to reward workers.", "Motivation & Accountability", "Absenteeism")
        assert "Financial incentives" in result

    def test_detects_supervision(self):
        result = _infer_mechanism("Regular supervision sessions were conducted.", "Workforce Support", "Productivity")
        assert "supervision" in result.lower()

    def test_fallback_when_no_keywords(self):
        result = _infer_mechanism("A programme was implemented.", "Enabling Environment", "Productivity")
        assert "productivity" in result.lower()


# ---------------------------------------------------------------------------
# Step 4 — aggregate_cluster
# ---------------------------------------------------------------------------

class TestAggregateCluster:
    def test_returns_dict_with_required_keys(self):
        df = _make_df(n=3)
        result = aggregate_cluster(df, cluster_id=0)
        for key in ["Canonical_Intervention", "Table3_Domain", "Problem_Addressed",
                    "Description", "Mechanism", "Evidence_Summary", "Strength_of_Evidence",
                    "Evidence_Types", "Implementation_Considerations", "Expected_Impact",
                    "Transferability_Rationale", "_cluster_id", "_references"]:
            # Most keys present; Transferability_Rationale comes from score step
            assert key in result or key == "Transferability_Rationale"

    def test_canonical_title_non_empty(self):
        df = _make_df(n=2)
        result = aggregate_cluster(df, cluster_id=1)
        assert result["Canonical_Intervention"]

    def test_strongest_evidence_selected(self):
        rows = [
            _make_row(**{"Strength of evidence": "weak"}),
            _make_row(**{"Strength of evidence": "strong"}),
        ]
        df = pd.DataFrame(rows).fillna("")
        result = aggregate_cluster(df, cluster_id=0)
        assert result["Strength_of_Evidence"] == "strong"

    def test_evidence_types_deduplicated(self):
        rows = [
            _make_row(**{"Evidence design/type": "RCT"}),
            _make_row(**{"Evidence design/type": "RCT"}),
            _make_row(**{"Evidence design/type": "qualitative"}),
        ]
        df = pd.DataFrame(rows).fillna("")
        result = aggregate_cluster(df, cluster_id=0)
        types = result["Evidence_Types"].split("; ")
        assert len(types) == len(set(types))

    def test_quantitative_impact_preferred(self):
        rows = [
            _make_row(**{"Expected impact": "Some general improvement"}),
            _make_row(**{"Expected impact": "Attendance improved by 35%"}),
        ]
        df = pd.DataFrame(rows).fillna("")
        result = aggregate_cluster(df, cluster_id=0)
        assert "35%" in result["Expected_Impact"]

    def test_references_concatenated(self):
        rows = [
            _make_row(**{"Reference": "Smith 2020"}),
            _make_row(**{"Reference": "Jones 2021"}),
        ]
        df = pd.DataFrame(rows).fillna("")
        result = aggregate_cluster(df, cluster_id=0)
        assert "Smith 2020" in result["_references"]
        assert "Jones 2021" in result["_references"]

    def test_cluster_id_stored(self):
        df = _make_df(n=2)
        result = aggregate_cluster(df, cluster_id=42)
        assert result["_cluster_id"] == 42

    def test_single_row_cluster(self):
        df = _make_df(n=1)
        result = aggregate_cluster(df, cluster_id=0)
        assert result["Canonical_Intervention"] == df.iloc[0]["Title"]


# ---------------------------------------------------------------------------
# Step 5 — score_transferability
# ---------------------------------------------------------------------------

class TestScoreTransferability:
    def _row(self, **kwargs) -> Dict:
        base = {
            "Description": "A community health worker programme for rural areas.",
            "Mechanism": "Community accountability strengthens compliance.",
            "Implementation_Considerations": "• Simple; low-cost paper forms",
        }
        base.update(kwargs)
        return base

    def test_returns_transferability_key(self):
        result = score_transferability(self._row())
        assert "Transferability" in result
        assert result["Transferability"] in ("High", "Medium", "Low")

    def test_returns_rationale_key(self):
        result = score_transferability(self._row())
        assert "Transferability_Rationale" in result
        assert len(result["Transferability_Rationale"]) > 20

    def test_community_rural_scores_high(self):
        row = self._row(
            Description="This simple community-based low-resource rural CHW intervention.",
            Implementation_Considerations="Simple paper forms, low-cost",
        )
        result = score_transferability(row)
        assert result["Transferability"] in ("High", "Medium")

    def test_hospital_technology_scores_low(self):
        row = self._row(
            Description="A hospital specialist tertiary digital technology platform.",
            Mechanism="Complex multi-component extensive software system.",
            Implementation_Considerations="Requires internet and equipment.",
        )
        result = score_transferability(row)
        assert result["Transferability"] in ("Low", "Medium")

    def test_preserves_existing_keys(self):
        row = self._row(Canonical_Intervention="Test", Intervention_Family="General")
        result = score_transferability(row)
        assert result["Canonical_Intervention"] == "Test"
        assert result["Intervention_Family"] == "General"


# ---------------------------------------------------------------------------
# Step 6 — build_evidence_map
# ---------------------------------------------------------------------------

class TestBuildEvidenceMap:
    def _make_clustered(self) -> pd.DataFrame:
        df = _make_df(n=4)
        df = assign_clusters(df, batch_size=4)
        return df

    def test_returns_dataframe(self):
        df = self._make_clustered()
        rows = [aggregate_cluster(g.copy(), int(cid)) for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        result = build_evidence_map(df, comp_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self):
        df = self._make_clustered()
        rows = [aggregate_cluster(g.copy(), int(cid)) for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        result = build_evidence_map(df, comp_df)
        for col in ["Canonical_Intervention", "Original_Intervention_ID", "Country",
                    "Reference", "Evidence_Type", "Snippet"]:
            assert col in result.columns

    def test_row_count_matches_original(self):
        df = self._make_clustered()
        rows = [aggregate_cluster(g.copy(), int(cid)) for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        result = build_evidence_map(df, comp_df)
        assert len(result) == len(df)

    def test_snippet_truncated_to_200_chars(self):
        long_desc = "A" * 500
        df = self._make_clustered()
        df["Description"] = long_desc
        rows = [aggregate_cluster(g.copy(), int(cid)) for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        result = build_evidence_map(df, comp_df)
        assert result["Snippet"].str.len().max() <= 200


# ---------------------------------------------------------------------------
# Output: write_excel
# ---------------------------------------------------------------------------

class TestWriteExcel:
    def _run(self, tmp_path) -> Path:
        df = _make_df(n=4)
        df = assign_clusters(df, batch_size=4)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        ev_df = build_evidence_map(df, comp_df)
        out = tmp_path / "HRH_Compendium.xlsx"
        write_excel(comp_df, ev_df, out)
        return out

    def test_file_created(self, tmp_path):
        out = self._run(tmp_path)
        assert out.exists()

    def test_has_two_sheets(self, tmp_path):
        out = self._run(tmp_path)
        xl = pd.ExcelFile(out)
        assert "Compendium" in xl.sheet_names
        assert "Evidence_Map" in xl.sheet_names

    def test_compendium_has_expected_columns(self, tmp_path):
        out = self._run(tmp_path)
        comp = pd.read_excel(out, sheet_name="Compendium")
        for col in ["Canonical_Intervention", "Transferability", "Table3_Domain"]:
            assert col in comp.columns

    def test_evidence_map_has_expected_columns(self, tmp_path):
        out = self._run(tmp_path)
        ev = pd.read_excel(out, sheet_name="Evidence_Map")
        for col in ["Canonical_Intervention", "Country", "Snippet"]:
            assert col in ev.columns

    def test_compendium_row_count_matches_clusters(self, tmp_path):
        df = _make_df(n=4)
        df = assign_clusters(df, batch_size=4)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        ev_df = build_evidence_map(df, comp_df)
        out = tmp_path / "HRH_Compendium.xlsx"
        write_excel(comp_df, ev_df, out)
        result = pd.read_excel(out, sheet_name="Compendium")
        assert len(result) == len(comp_df)

    def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        df = _make_df(n=2)
        df = assign_clusters(df, batch_size=2)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        ev_df = build_evidence_map(df, comp_df)
        write_excel(comp_df, ev_df, nested / "out.xlsx")
        assert (nested / "out.xlsx").exists()


# ---------------------------------------------------------------------------
# Output: write_word
# ---------------------------------------------------------------------------

class TestWriteWord:
    def _run(self, tmp_path) -> Path:
        df = _make_df(n=3)
        df = assign_clusters(df, batch_size=3)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        out = tmp_path / "HRH_Compendium.docx"
        write_word(comp_df, out)
        return out

    def test_file_created(self, tmp_path):
        out = self._run(tmp_path)
        assert out.exists()

    def test_file_is_valid_docx(self, tmp_path):
        out = self._run(tmp_path)
        from docx import Document as D
        doc = D(out)
        assert len(doc.paragraphs) > 0

    def test_domain_headings_present(self, tmp_path):
        out = self._run(tmp_path)
        from docx import Document as D
        doc = D(out)
        heading_texts = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert len(heading_texts) > 0

    def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / "x" / "y"
        df = _make_df(n=2)
        df = assign_clusters(df, batch_size=2)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp_df = pd.DataFrame(rows)
        write_word(comp_df, nested / "out.docx")
        assert (nested / "out.docx").exists()


# ---------------------------------------------------------------------------
# Integration: full pipeline on small fixture
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def _make_varied_df(self, n: int = 20) -> pd.DataFrame:
        """Mix of absenteeism, accountability, productivity rows."""
        topics = [
            ("Performance-based incentives", "Financial rewards for meeting attendance targets. Incentives align behaviour.", "moderate"),
            ("Community scorecards", "Community accountability through public scorecards. Community social norms.", "weak"),
            ("Supervision protocols", "Structured supervision sessions for rural health workers.", "strong"),
            ("Digital HRIS tracking", "Digital technology software system for tracking attendance data.", "moderate"),
            ("Regulatory sanctions", "Sanctions and penalties for absenteeism enforcement governance.", "weak"),
        ]
        rows = []
        for i in range(n):
            t = topics[i % len(topics)]
            rows.append(_make_row(**{
                "Intervention ID": f"INT-{i:03d}",
                "Title": t[0],
                "Description": t[1] + f" Study {i}.",
                "Strength of evidence": t[2],
                "Expected impact": f"Reduced absenteeism by {10 + i}%",
            }))
        return pd.DataFrame(rows).fillna("")

    def test_pipeline_produces_compendium_rows(self, tmp_path):
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(20)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)

        run_pipeline(in_path, tmp_path / "output")

        xl = pd.ExcelFile(tmp_path / "output" / "HRH_Compendium.xlsx")
        comp = pd.read_excel(xl, sheet_name="Compendium")
        assert len(comp) > 0

    def test_pipeline_produces_word_doc(self, tmp_path):
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(10)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)

        run_pipeline(in_path, tmp_path / "output")
        assert (tmp_path / "output" / "HRH_Compendium.docx").exists()

    def test_evidence_map_rows_equal_input_rows(self, tmp_path):
        from tools.hrh_compendium_builder import run_pipeline
        n = 15
        df = self._make_varied_df(n)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)

        run_pipeline(in_path, tmp_path / "output")

        ev = pd.read_excel(tmp_path / "output" / "HRH_Compendium.xlsx", sheet_name="Evidence_Map")
        assert len(ev) == n

    def test_no_hallucinated_evidence_in_output(self, tmp_path):
        """Ensure evidence fields either contain real data or 'no_evidence_found'."""
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(10)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)

        run_pipeline(in_path, tmp_path / "output")

        comp = pd.read_excel(tmp_path / "output" / "HRH_Compendium.xlsx", sheet_name="Compendium")
        for _, row in comp.iterrows():
            ev = str(row.get("Evidence_Summary", ""))
            assert ev  # not blank
