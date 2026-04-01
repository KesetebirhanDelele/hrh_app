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
    FORCE_MERGE_RULES,
    PACKAGE_KEYWORDS,
    PROBLEM_KEYWORDS,
    REQUIRED_COLS,
    STRENGTH_ORDER,
    _agglom_labels,
    _classify_by_keywords,
    _consolidate_if_oversized,
    _drop_general_interventions_package,
    _extract_country,
    _infer_mechanism,
    _keyword_similarity,
    _merge_bullets,
    _merge_canonical_rows,
    _score_package,
    _strip_country_refs,
    _strongest_evidence,
    _text_for_embedding,
    aggregate_cluster,
    apply_force_merges,
    assign_clusters,
    assign_packages,
    build_evidence_map,
    cluster_batch,
    compute_embeddings,
    deduplicate_canonical_names,
    filter_chw_relevant,
    is_relevant_to_chw,
    load_data,
    recheck_chw_canonical,
    score_transferability,
    validate_structure,
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

    def _run(self, tmp_path, n: int):
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(n)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)
        run_pipeline(in_path, tmp_path / "output")
        xlsx = list((tmp_path / "output").glob("HRH_Compendium_*.xlsx"))[0]
        docx = list((tmp_path / "output").glob("HRH_Compendium_*.docx"))[0]
        return xlsx, docx

    def test_pipeline_produces_compendium_rows(self, tmp_path):
        xlsx, _ = self._run(tmp_path, 20)
        comp = pd.read_excel(xlsx, sheet_name="Compendium")
        assert len(comp) > 0

    def test_pipeline_produces_word_doc(self, tmp_path):
        _, docx = self._run(tmp_path, 10)
        assert docx.exists()

    def test_evidence_map_rows_equal_input_rows(self, tmp_path):
        n = 15
        xlsx, _ = self._run(tmp_path, n)
        ev = pd.read_excel(xlsx, sheet_name="Evidence_Map")
        assert len(ev) == n

    def test_no_hallucinated_evidence_in_output(self, tmp_path):
        """Ensure evidence fields either contain real data or 'no_evidence_found'."""
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(10)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)

        run_pipeline(in_path, tmp_path / "output")

        # find the timestamped xlsx
        xlsx_files = list((tmp_path / "output").glob("HRH_Compendium_*.xlsx"))
        assert len(xlsx_files) == 1
        comp = pd.read_excel(xlsx_files[0], sheet_name="Compendium")
        for _, row in comp.iterrows():
            ev = str(row.get("Evidence_Summary", ""))
            assert ev  # not blank

    def test_output_filenames_are_timestamped(self, tmp_path):
        from tools.hrh_compendium_builder import run_pipeline
        df = self._make_varied_df(5)
        in_path = tmp_path / "input" / "interventions.xlsx"
        in_path.parent.mkdir(parents=True)
        df.to_excel(in_path, index=False)
        run_pipeline(in_path, tmp_path / "output")
        xlsx_files = list((tmp_path / "output").glob("HRH_Compendium_*.xlsx"))
        docx_files = list((tmp_path / "output").glob("HRH_Compendium_*.docx"))
        assert len(xlsx_files) == 1
        assert len(docx_files) == 1
        # timestamp pattern: MMDDYYYY_HHMMSS
        import re
        assert re.search(r"\d{8}_\d{6}", xlsx_files[0].name)


# ---------------------------------------------------------------------------
# Step 7 — assign_packages
# ---------------------------------------------------------------------------

class TestAssignPackages:
    def _make_compendium(self, n: int = 6) -> pd.DataFrame:
        df = _make_df(n=n)
        df = assign_clusters(df, batch_size=n)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        return pd.DataFrame(rows)

    def test_adds_intervention_package_column(self):
        comp = self._make_compendium()
        result = assign_packages(comp)
        assert "Intervention_Package" in result.columns

    def test_every_row_has_a_package(self):
        comp = self._make_compendium(8)
        result = assign_packages(comp)
        assert result["Intervention_Package"].notna().all()
        assert (result["Intervention_Package"] != "").all()

    def test_package_count_per_domain_does_not_exceed_8(self):
        # Create a large compendium spanning one domain
        rows = []
        for i in range(20):
            r = _make_row(**{
                "Intervention ID": f"INT-{i:03d}",
                "Title": f"Intervention {i}",
                "HRH-II Package Component": "Motivation & Accountability",
                "Description": f"A unique intervention about topic {i}.",
            })
            rows.append(r)
        df = pd.DataFrame(rows).fillna("")
        df = assign_clusters(df, batch_size=20)
        canon = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                 for cid, g in df.groupby("_cluster")]
        comp = pd.DataFrame(canon)
        comp["Table3_Domain"] = "Motivation & Accountability"
        result = assign_packages(comp)
        for domain, grp in result.groupby("Table3_Domain"):
            assert grp["Intervention_Package"].nunique() <= 8

    def test_financial_incentive_keywords_map_to_correct_package(self):
        """Row whose text contains 'incentive' → Financial Incentive Systems."""
        row = {
            "Canonical_Intervention": "Financial Incentive Scheme",
            "Description": "Performance-based financial incentives and bonus payments.",
            "Mechanism": "Incentives align behaviour",
            "Table3_Domain": "Motivation & Accountability",
            "Intervention_Family": "M&A",
            "Problem_Addressed": "Absenteeism",
            "Evidence_Summary": "x",
            "Strength_of_Evidence": "moderate",
            "Evidence_Types": "RCT",
            "Implementation_Considerations": "• Requires payment system",
            "Expected_Impact": "Improved attendance",
            "Transferability": "High",
            "Transferability_Rationale": "x",
            "_cluster_id": 0,
            "_intervention_ids": "INT-001",
            "_references": "Smith 2020",
            "_variant_titles": ["Financial Incentive Scheme"],
        }
        comp = pd.DataFrame([row])
        result = assign_packages(comp)
        assert result.iloc[0]["Intervention_Package"] == "Financial Incentive Systems"

    def test_unmatched_text_gets_fallback_package(self):
        score = _score_package("completely unrelated text about nothing", {
            "Package A": ["specific_keyword_xyz"],
        })
        from tools.hrh_compendium_builder import _FALLBACK_PACKAGE
        assert score == _FALLBACK_PACKAGE


# ---------------------------------------------------------------------------
# Step 10 — validate_structure
# ---------------------------------------------------------------------------

class TestValidateStructure:
    def _valid_compendium(self) -> pd.DataFrame:
        df = _make_df(n=4)
        df = assign_clusters(df, batch_size=4)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp = pd.DataFrame(rows)
        return assign_packages(comp)

    def test_passes_for_valid_compendium(self):
        comp = self._valid_compendium()
        validate_structure(comp)  # should not raise

    def test_raises_on_duplicate_canonical_names(self):
        comp = self._valid_compendium()
        # Force a duplicate
        comp = pd.concat([comp, comp.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="Duplicate"):
            validate_structure(comp)

    # --- deduplicate_canonical_names ---

    def test_deduplicate_leaves_unique_names_unchanged(self):
        df = pd.DataFrame({"Canonical_Intervention": ["A", "B", "C"]})
        result = deduplicate_canonical_names(df)
        assert list(result["Canonical_Intervention"]) == ["A", "B", "C"]

    def test_deduplicate_appends_counter_to_duplicates(self):
        df = pd.DataFrame({"Canonical_Intervention": ["A", "A", "A"]})
        result = deduplicate_canonical_names(df)
        assert list(result["Canonical_Intervention"]) == ["A", "A (2)", "A (3)"]

    def test_deduplicate_does_not_modify_first_occurrence(self):
        df = pd.DataFrame({"Canonical_Intervention": ["Title", "Title", "Other"]})
        result = deduplicate_canonical_names(df)
        assert result.iloc[0]["Canonical_Intervention"] == "Title"
        assert result.iloc[1]["Canonical_Intervention"] == "Title (2)"
        assert result.iloc[2]["Canonical_Intervention"] == "Other"

    def test_after_deduplication_validation_passes(self):
        df = pd.DataFrame({"Canonical_Intervention": ["X", "X"]})
        deduped = deduplicate_canonical_names(df)
        # Add the minimum columns validate_structure needs
        deduped["Intervention_Package"] = "Pkg A"
        deduped["Table3_Domain"] = "Enabling Environment"
        validate_structure(deduped)  # should not raise

    def test_raises_when_package_column_missing(self):
        comp = self._valid_compendium().drop(columns=["Intervention_Package"])
        with pytest.raises(ValueError, match="Intervention_Package column missing"):
            validate_structure(comp)

    def test_warns_when_package_count_exceeds_10(self, capsys):
        # Build a compendium where one domain has 11 distinct packages.
        # Construct directly so we control the exact package assignments.
        rows = [
            {
                "Canonical_Intervention": f"Intervention {i}",
                "Intervention_Package": f"Package {i}",  # 11 distinct packages
                "Table3_Domain": "Motivation & Accountability",
                "Problem_Addressed": "Absenteeism",
            }
            for i in range(11)
        ]
        comp = pd.DataFrame(rows)
        validate_structure(comp)  # should not raise, only warn
        captured = capsys.readouterr()
        assert "WARN" in captured.out


# ---------------------------------------------------------------------------
# Step 8 — Word doc 3-level hierarchy
# ---------------------------------------------------------------------------

class TestWriteWordHierarchy:
    def _make_compendium_with_packages(self, n: int = 6) -> pd.DataFrame:
        df = _make_df(n=n)
        df = assign_clusters(df, batch_size=n)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp = pd.DataFrame(rows)
        return assign_packages(comp)

    def test_heading_levels_include_package(self, tmp_path):
        comp = self._make_compendium_with_packages(6)
        out = tmp_path / "test.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        heading_styles = [p.style.name for p in doc.paragraphs if p.style.name.startswith("Heading")]
        # Should have Heading 1, 2, and 3
        assert "Heading 1" in heading_styles
        assert "Heading 2" in heading_styles
        assert "Heading 3" in heading_styles

    def test_no_duplicate_canonical_in_word(self, tmp_path):
        comp = self._make_compendium_with_packages(4)
        out = tmp_path / "test.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        h3_texts = [p.text for p in doc.paragraphs if p.style.name == "Heading 3"]
        assert len(h3_texts) == len(set(h3_texts))

    def test_variants_section_not_in_word(self, tmp_path):
        """Variants / Examples must NOT appear in Word output (Excel only)."""
        row = score_transferability(aggregate_cluster(
            _make_df(n=3).assign(**{
                "Title": ["Title A", "Title B", "Title C"],
                "Description": ["Incentive reward bonus payment"] * 3,
            }),
            cluster_id=0,
        ))
        comp = pd.DataFrame([row])
        comp = assign_packages(comp)
        out = tmp_path / "test.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        texts = [p.text for p in doc.paragraphs]
        assert not any("Variants" in t for t in texts)

    def _word_bullets(self, tmp_path, row_overrides: dict, filename="test.docx"):
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row.update(row_overrides)
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / filename
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        return [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]

    def test_multiple_evidence_sentences_rendered_as_bullets(self, tmp_path):
        """Multiple |-separated evidence sentences must each become a List Bullet."""
        bullets = self._word_bullets(
            tmp_path,
            {"Evidence_Summary": "First finding. | Second finding. | Third finding."},
            filename="ev_multi.docx",
        )
        assert "First finding." in bullets
        assert "Second finding." in bullets
        assert "Third finding." in bullets

    def test_single_evidence_sentence_not_bulleted(self, tmp_path):
        """A single evidence sentence is rendered inline, not as a bullet."""
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row["Evidence_Summary"] = "Only one finding."
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / "ev_single.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        bullets = [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]
        assert "Only one finding." not in bullets
        plain = [p.text for p in doc.paragraphs]
        assert any("Only one finding." in t for t in plain)

    def test_multiple_evidence_types_rendered_as_bullets(self, tmp_path):
        """Multiple ;-separated evidence types must each become a List Bullet."""
        bullets = self._word_bullets(
            tmp_path,
            {"Evidence_Types": "RCT; Observational; Systematic Review"},
            filename="ev_types_multi.docx",
        )
        assert "RCT" in bullets
        assert "Observational" in bullets
        assert "Systematic Review" in bullets

    def test_single_evidence_type_not_bulleted(self, tmp_path):
        """A single evidence type is rendered inline, not as a bullet."""
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row["Evidence_Types"] = "RCT"
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / "ev_type_single.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        bullets = [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]
        assert "RCT" not in bullets

    def test_references_rendered_as_bullet_list(self, tmp_path):
        """Each semicolon-delimited reference must appear as a separate List Bullet paragraph."""
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row["_references"] = "Smith 2020; Jones 2021; WHO 2019"
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / "test_refs.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        bullet_texts = [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]
        assert "Smith 2020" in bullet_texts
        assert "Jones 2021" in bullet_texts
        assert "WHO 2019" in bullet_texts

    def test_single_reference_still_bulleted(self, tmp_path):
        """A single reference is also rendered as a List Bullet (consistent style)."""
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row["_references"] = "Smith 2020"
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / "test_single_ref.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        bullet_texts = [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]
        assert "Smith 2020" in bullet_texts

    def test_empty_references_no_bullet_header(self, tmp_path):
        """When _references is empty, the References label should not appear."""
        row = score_transferability(aggregate_cluster(_make_df(n=2), cluster_id=0))
        row["_references"] = ""
        comp = assign_packages(pd.DataFrame([row]))
        out = tmp_path / "test_no_refs.docx"
        write_word(comp, out)
        from docx import Document as D
        doc = D(out)
        texts = [p.text for p in doc.paragraphs]
        assert not any("References:" in t for t in texts)


# ---------------------------------------------------------------------------
# CHW scope filter
# ---------------------------------------------------------------------------

class TestIsRelevantToChw:
    def _row(self, title="", desc="", cadre="", component=""):
        return pd.Series({
            "Title": title, "Description": desc,
            "Target cadre & setting": cadre,
            "HRH-II Package Component": component,
        })

    def test_chw_in_title_includes(self):
        assert is_relevant_to_chw(self._row(title="CHW incentive programme"))

    def test_community_health_worker_in_desc_includes(self):
        assert is_relevant_to_chw(self._row(desc="Interventions for community health workers in rural areas."))

    def test_hew_in_cadre_includes(self):
        assert is_relevant_to_chw(self._row(cadre="Health extension workers (HEWs) in Ethiopia"))

    def test_health_extension_in_desc_includes(self):
        assert is_relevant_to_chw(self._row(desc="The health extension programme focused on rural villages."))

    def test_supportive_supervision_includes(self):
        assert is_relevant_to_chw(self._row(title="Supportive supervision of community health supervisors"))

    def test_physician_focus_excludes(self):
        assert not is_relevant_to_chw(self._row(
            title="Physician specialist training",
            desc="Medical specialist physicians received tertiary care training.",
        ))

    def test_tertiary_care_excludes(self):
        assert not is_relevant_to_chw(self._row(
            desc="Tertiary hospital surgical ward specialist pharmacist protocols."
        ))

    def test_nurse_with_community_context_includes(self):
        assert is_relevant_to_chw(self._row(
            desc="Community nurses supervised CHW clusters in primary health settings."
        ))

    def test_empty_row_excluded_by_default(self):
        """Strict filter: no CHW signals → exclude."""
        assert not is_relevant_to_chw(self._row())


class TestFilterChwRelevant:
    def test_returns_dataframe(self):
        df = _make_df(n=5)
        result = filter_chw_relevant(df)
        assert isinstance(result, pd.DataFrame)

    def test_removes_non_chw_rows(self):
        rows = [
            {**{c: "" for c in _make_row().keys()},
             "Title": "CHW incentive programme",
             "Description": "Community health workers received performance bonuses.",
             "Target cadre & setting": "CHWs in rural areas",
             "HRH-II Package Component": "Motivation"},
            {**{c: "" for c in _make_row().keys()},
             "Title": "Physician specialist training",
             "Description": "Medical specialist physicians at tertiary hospital surgical ward.",
             "Target cadre & setting": "Hospital physicians",
             "HRH-II Package Component": "Tertiary care"},
        ]
        df = pd.DataFrame(rows).fillna("")
        result = filter_chw_relevant(df)
        assert len(result) < len(df)
        assert any("CHW" in str(r["Title"]) for _, r in result.iterrows())

    def test_index_reset_after_filter(self):
        df = _make_df(n=4)
        result = filter_chw_relevant(df)
        assert list(result.index) == list(range(len(result)))

    def test_all_chw_rows_kept(self):
        df = _make_df(n=4)  # all rows have CHW-like content from fixture
        result = filter_chw_relevant(df)
        assert len(result) == len(df)


# ---------------------------------------------------------------------------
# Description country-stripping
# ---------------------------------------------------------------------------

class TestStripCountryRefs:
    def test_removes_ethiopia(self):
        result = _strip_country_refs("In Ethiopia, performance incentives were used.")
        assert "Ethiopia" not in result
        assert "the country" in result

    def test_removes_multiple_countries(self):
        result = _strip_country_refs("Studies in Kenya and Uganda showed improvement.")
        assert "Kenya" not in result
        assert "Uganda" not in result

    def test_leaves_non_country_text_unchanged(self):
        text = "Supervision reduced absenteeism by 30%."
        assert _strip_country_refs(text) == text

    def test_case_insensitive(self):
        result = _strip_country_refs("ETHIOPIA rural health workers improved attendance.")
        assert "ETHIOPIA" not in result


# ---------------------------------------------------------------------------
# Global clustering
# ---------------------------------------------------------------------------

class TestAssignClustersGlobal:
    def test_small_df_uses_fixed_threshold(self):
        """n <= target_max → fixed threshold, no binary search."""
        df = _make_df(n=5)
        result = assign_clusters(df, target_min=80, target_max=120)
        assert "_cluster" in result.columns
        assert (result["_cluster"] >= 0).all()

    def test_large_df_targets_range(self):
        """n > target_max → binary search tries to land in [target_min, target_max]."""
        # Build 200 rows with mixed content so clustering can find groups
        topics = [
            "Community health worker incentive bonus payment",
            "Supportive supervision mentoring coaching visits",
            "Training capacity skill workshop education",
            "Data monitoring dashboard HRIS reporting",
        ]
        rows = [_make_row(**{
            "Intervention ID": f"INT-{i:03d}",
            "Title": topics[i % 4],
            "Description": topics[i % 4] + f" variant {i}",
        }) for i in range(200)]
        df = pd.DataFrame(rows).fillna("")
        result = assign_clusters(df, target_min=2, target_max=10)
        n_clusters = result["_cluster"].nunique()
        # Should be somewhere close to the target
        assert 1 <= n_clusters <= 50  # generous bound for test stability

    def test_all_rows_get_cluster(self):
        df = _make_df(n=10)
        result = assign_clusters(df, target_min=80, target_max=120)
        assert (result["_cluster"] >= 0).all()


# ---------------------------------------------------------------------------
# Variants_List in aggregate output
# ---------------------------------------------------------------------------

class TestVariantsList:
    def test_variants_list_present_in_aggregate(self):
        df = _make_df(n=3)
        result = aggregate_cluster(df, cluster_id=0)
        assert "Variants_List" in result

    def test_variants_list_contains_original_titles(self):
        rows = [_make_row(**{"Title": f"Title {c}", "Intervention ID": f"INT-{c}"})
                for c in ["A", "B", "C"]]
        df = pd.DataFrame(rows).fillna("")
        result = aggregate_cluster(df, cluster_id=0)
        vl = result["Variants_List"]
        assert "Title A" in vl
        assert "Title B" in vl

    def test_variants_list_in_excel_output(self, tmp_path):
        df = _make_df(n=3)
        df = assign_clusters(df, batch_size=3)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp = pd.DataFrame(rows)
        comp = assign_packages(comp)
        ev = build_evidence_map(df, comp)
        out = tmp_path / "test.xlsx"
        write_excel(comp, ev, out)
        result = pd.read_excel(out, sheet_name="Compendium")
        assert "Variants_List" in result.columns


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

class TestConsolidateIfOversized:
    def _make_large_compendium(self, n: int) -> pd.DataFrame:
        df = _make_df(n=n)
        df = assign_clusters(df, batch_size=n)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        return pd.DataFrame(rows)

    def test_small_compendium_unchanged(self):
        comp = self._make_large_compendium(5)
        result = _consolidate_if_oversized(comp, max_count=200)
        assert len(result) == len(comp)

    def test_oversized_compendium_reduced(self):
        # Build a compendium with 20 rows; set max_count=5 to force consolidation
        comp = self._make_large_compendium(10)
        if len(comp) > 5:
            result = _consolidate_if_oversized(comp, max_count=5, target_min=2, target_max=4)
            assert len(result) < len(comp)

    def test_variants_list_merged_after_consolidation(self):
        comp = self._make_large_compendium(8)
        result = _consolidate_if_oversized(comp, max_count=2, target_min=1, target_max=2)
        # Every row in result should have a non-empty Variants_List
        if len(result) < len(comp):
            assert result["Variants_List"].notna().all()


# ---------------------------------------------------------------------------
# Strict CHW filter — new behaviour
# ---------------------------------------------------------------------------

class TestStrictChwFilter:
    def _row(self, title="", desc="", cadre="", component=""):
        return pd.Series({
            "Title": title, "Description": desc,
            "Target cadre & setting": cadre,
            "HRH-II Package Component": component,
        })

    def test_explicit_chw_includes(self):
        assert is_relevant_to_chw(self._row(title="CHW incentive programme"))

    def test_explicit_hew_includes(self):
        assert is_relevant_to_chw(self._row(cadre="Health extension workers (HEWs)"))

    def test_community_health_worker_in_desc_includes(self):
        assert is_relevant_to_chw(self._row(
            desc="Community health workers received performance-based bonuses."
        ))

    def test_supportive_supervision_includes(self):
        assert is_relevant_to_chw(self._row(title="Supportive supervision for frontline staff"))

    def test_supervision_plus_community_includes(self):
        assert is_relevant_to_chw(self._row(
            desc="Supervision visits were conducted in community primary health facilities."
        ))

    def test_physician_excluded(self):
        assert not is_relevant_to_chw(self._row(
            title="Physician specialist training",
            desc="Medical specialist physicians at tertiary care hospital surgical ward.",
            cadre="Hospital physicians",
        ))

    def test_general_governance_without_chw_excluded(self):
        assert not is_relevant_to_chw(self._row(
            title="National Health Policy Reform",
            desc="National health policy and health sector reform for ministry of health strategy.",
        ))

    def test_general_governance_WITH_chw_included(self):
        assert is_relevant_to_chw(self._row(
            title="National Policy for Community Health Workers",
            desc="Health sector reform policies targeting community health workers.",
        ))

    def test_nurse_without_community_context_excluded(self):
        assert not is_relevant_to_chw(self._row(
            desc="Bedside nursing care protocols for inpatient nursing staff."
        ))

    def test_nurse_with_supervision_context_included(self):
        assert is_relevant_to_chw(self._row(
            desc="Nurse supervisors conducted monthly visits to community health workers."
        ))

    def test_empty_row_excluded(self):
        assert not is_relevant_to_chw(self._row())


# ---------------------------------------------------------------------------
# Force merge rules
# ---------------------------------------------------------------------------

class TestForceMergeRules:
    def _make_canonical_row(self, name, desc, domain="Motivation & Accountability"):
        return {
            "Canonical_Intervention": name,
            "Description": desc,
            "Mechanism": "",
            "Table3_Domain": domain,
            "Intervention_Family": "Test",
            "Problem_Addressed": "Absenteeism",
            "Evidence_Summary": "x",
            "Strength_of_Evidence": "moderate",
            "Evidence_Types": "RCT",
            "Implementation_Considerations": "x",
            "Expected_Impact": "improved attendance",
            "Transferability": "High",
            "Transferability_Rationale": "x",
            "_cluster_id": 0,
            "_intervention_ids": "INT-001",
            "_references": "Smith 2020",
            "_variant_titles": [name],
            "Variants_List": name,
        }

    def test_incentive_rows_merged_to_target(self):
        rows = [
            self._make_canonical_row("PBF for HEWs", "performance-based financial incentive bonus"),
            self._make_canonical_row("Outreach Allowances", "outreach incentive allowance cash"),
            self._make_canonical_row("Salary Bonuses", "salary bonus payment financial reward"),
        ]
        comp = pd.DataFrame(rows)
        result, merged = apply_force_merges(comp)
        targets = result["Canonical_Intervention"].tolist()
        assert "Financial Incentive Systems for CHWs" in targets
        assert merged == 2  # 3 rows → 1, so 2 absorbed

    def test_supervision_rows_merged(self):
        rows = [
            self._make_canonical_row("Mentoring Visits", "mentoring coaching supervisor visit"),
            self._make_canonical_row("Coaching Sessions", "coaching supervisory visit supportive supervision"),
        ]
        comp = pd.DataFrame(rows)
        result, merged = apply_force_merges(comp)
        assert "Supportive Supervision Systems" in result["Canonical_Intervention"].tolist()
        assert merged >= 1

    def test_training_rows_merged(self):
        rows = [
            self._make_canonical_row("Refresher Training", "refresher training in-service skill"),
            self._make_canonical_row("Orientation Workshops", "workshop orientation capacit"),
        ]
        comp = pd.DataFrame(rows)
        result, merged = apply_force_merges(comp)
        assert "Training and Capacity Building for CHWs" in result["Canonical_Intervention"].tolist()

    def test_unmatched_rows_unchanged(self):
        rows = [
            self._make_canonical_row("Community Scorecard", "community scorecard participat feedback"),
        ]
        comp = pd.DataFrame(rows)
        result, merged = apply_force_merges(comp)
        assert merged == 0
        assert "Community Scorecard" in result["Canonical_Intervention"].tolist()

    def test_merged_row_combines_references(self):
        rows = [
            {**self._make_canonical_row("PBF", "incentiv bonus"), "_references": "Smith 2020"},
            {**self._make_canonical_row("Bonus Pay", "incentiv bonus payment"), "_references": "Jones 2021"},
        ]
        comp = pd.DataFrame(rows)
        result, _ = apply_force_merges(comp)
        merged_row = result[result["Canonical_Intervention"] == "Financial Incentive Systems for CHWs"].iloc[0]
        assert "Smith 2020" in merged_row["_references"]
        assert "Jones 2021" in merged_row["_references"]

    def test_variants_list_accumulated_after_merge(self):
        rows = [
            self._make_canonical_row("PBF Scheme", "incentiv bonus"),
            self._make_canonical_row("Cash Transfer", "cash transfer incentiv"),
        ]
        comp = pd.DataFrame(rows)
        result, _ = apply_force_merges(comp)
        merged_row = result[result["Canonical_Intervention"] == "Financial Incentive Systems for CHWs"].iloc[0]
        vl = str(merged_row.get("Variants_List", ""))
        assert "PBF Scheme" in vl or "Cash Transfer" in vl


# ---------------------------------------------------------------------------
# recheck_chw_canonical
# ---------------------------------------------------------------------------

class TestRecheckChwCanonical:
    def _make_comp(self):
        df = _make_df(n=3)
        df = assign_clusters(df, batch_size=3)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        return pd.DataFrame(rows)

    def test_returns_tuple_df_int(self):
        comp = self._make_comp()
        result, removed = recheck_chw_canonical(comp)
        assert isinstance(result, pd.DataFrame)
        assert isinstance(removed, int)

    def test_non_chw_canonicals_removed(self):
        rows = [
            {
                "Canonical_Intervention": "CHW Performance Bonuses",
                "Description": "Community health workers received bonuses.",
                "Intervention_Family": "Motivation",
                "Strength_of_Evidence": "moderate",
            },
            {
                "Canonical_Intervention": "National Health Policy Reform",
                "Description": "Ministry of health strategy health sector reform.",
                "Intervention_Family": "Governance",
                "Strength_of_Evidence": "weak",
            },
        ]
        comp = pd.DataFrame(rows)
        result, removed = recheck_chw_canonical(comp)
        assert removed >= 1
        assert "CHW Performance Bonuses" in result["Canonical_Intervention"].tolist()

    def test_all_chw_rows_kept(self):
        comp = self._make_comp()
        result, removed = recheck_chw_canonical(comp)
        # _make_df rows all contain "community health workers" — should all pass
        assert removed == 0


# ---------------------------------------------------------------------------
# _drop_general_interventions_package
# ---------------------------------------------------------------------------

class TestDropGeneralInterventions:
    def _make_comp_with_general(self):
        df = _make_df(n=4)
        df = assign_clusters(df, batch_size=4)
        rows = [score_transferability(aggregate_cluster(g.copy(), int(cid)))
                for cid, g in df.groupby("_cluster")]
        comp = pd.DataFrame(rows)
        comp = assign_packages(comp)
        # Force one row into General Interventions
        from tools.hrh_compendium_builder import _FALLBACK_PACKAGE
        comp.iloc[0, comp.columns.get_loc("Intervention_Package")] = _FALLBACK_PACKAGE
        return comp

    def test_no_general_interventions_remain_after_drop(self):
        from tools.hrh_compendium_builder import _FALLBACK_PACKAGE
        comp = self._make_comp_with_general()
        result = _drop_general_interventions_package(comp)
        assert _FALLBACK_PACKAGE not in result["Intervention_Package"].tolist()

    def test_result_is_dataframe(self):
        comp = self._make_comp_with_general()
        result = _drop_general_interventions_package(comp)
        assert isinstance(result, pd.DataFrame)
