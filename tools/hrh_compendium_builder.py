#!/usr/bin/env python3
"""
hrh_compendium_builder.py

Transform a raw HRH interventions Excel file into:
  1. output/HRH_Compendium.xlsx  (Compendium + Evidence_Map sheets)
  2. output/HRH_Compendium.docx  (policy-ready Word document)

Usage:
    python tools/hrh_compendium_builder.py
    python tools/hrh_compendium_builder.py --input path/to/file.xlsx --output-dir ./output
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Optional heavy imports — degrade gracefully
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.feature_extraction.text import TfidfVectorizer
    _SKLEARN = True
except ImportError:  # pragma: no cover
    _SKLEARN = False

try:
    from sentence_transformers import SentenceTransformer
    _SBERT = True
except ImportError:
    _SBERT = False

try:
    from openpyxl import Workbook as _OWB
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    _OPENPYXL = True
except ImportError:  # pragma: no cover
    _OPENPYXL = False

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    _DOCX = True
except ImportError:  # pragma: no cover
    _DOCX = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLS = [
    "Intervention ID",
    "Title",
    "HRH-II Package Component",
    "Description",
    "Evidence status",
    "Strength of evidence",
    "Evidence design/type",
    "Target cadre & setting",
    "Implementation considerations",
    "Expected impact",
    "Reference",
    "Page",
]

STRENGTH_ORDER: Dict[str, int] = {
    "strong": 3,
    "moderate": 2,
    "weak": 1,
    "": 0,
}

PROBLEM_KEYWORDS: Dict[str, List[str]] = {
    "Absenteeism": [
        "absent", "absentee", "attendance", "no-show", "truancy", "leave",
    ],
    "Accountability": [
        "account", "responsib", "oversight", "audit", "governance",
        "sanction", "penalt", "reward", "disciplin",
    ],
    "Productivity": [
        "productiv", "efficiency", "output", "performance", "workload", "utiliz",
    ],
}

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "Motivation & Accountability": [
        "incentiv", "reward", "penalt", "sanction", "motivat", "account",
    ],
    "Workforce Support": [
        "supervis", "mentor", "coach", "support", "training", "capacit",
    ],
    "Tools & Infrastructure": [
        "digital", "technolog", "hris", "software", "system", "equipment", "data",
    ],
    "Community Engagement": [
        "communit", "social", "citizen", "village", "participat", "feedback",
    ],
    "Service Delivery Processes": [
        "protocol", "guideline", "workflow", "procedure", "standard", "referral",
    ],
    "Enabling Environment": [
        "policy", "legal", "regulat", "govern", "framework", "environment",
    ],
}

_HIGH_FIT_KW = ["community", "chw", "community health worker", "low-resource", "rural"]
_LOW_FIT_KW = ["hospital", "specialist", "tertiary", "high-income"]
_RESOURCE_HEAVY_KW = ["technology", "digital", "internet", "app", "software", "equipment"]
_RESOURCE_LIGHT_KW = ["low-cost", "paper", "simple", "basic"]
_COMPLEX_KW = ["multi-component", "multifaceted", "extensive"]
_SIMPLE_KW = ["single", "straightforward", "easy"]

_COUNTRY_PATTERNS = [
    r"\b(Ethiopia[n]?|ETH)\b",
    r"\b(Kenya[n]?|KEN)\b",
    r"\b(Uganda[n]?|UGA)\b",
    r"\b(Nigeria[n]?|NGA)\b",
    r"\b(Tanzania[n]?|TZA)\b",
    r"\b(Ghana[ian]?|GHA)\b",
    r"\b(India[n]?|IND)\b",
    r"\b(Bangladesh[i]?|BGD)\b",
    r"\b(Malawi[an]?|MWI)\b",
    r"\b(Rwanda[n]?|RWA)\b",
    r"\b(Zambia[n]?|ZMB)\b",
    r"\b(Zimbabwe[an]?|ZWE)\b",
]

_COMPENDIUM_COLS = [
    "Canonical_Intervention",
    "Intervention_Family",
    "Table3_Domain",
    "Problem_Addressed",
    "Description",
    "Mechanism",
    "Evidence_Summary",
    "Strength_of_Evidence",
    "Evidence_Types",
    "Implementation_Considerations",
    "Expected_Impact",
    "Transferability",
    "Transferability_Rationale",
]

_EVIDENCE_MAP_COLS = [
    "Canonical_Intervention",
    "Original_Intervention_ID",
    "Country",
    "Reference",
    "Evidence_Type",
    "Snippet",
]


# ---------------------------------------------------------------------------
# Step 1 — Load & clean
# ---------------------------------------------------------------------------

def load_data(path: str | Path) -> pd.DataFrame:
    """Load interventions Excel and normalise column names."""
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("")
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Input file missing required columns: {missing}")
    return df


# ---------------------------------------------------------------------------
# Step 2 — Embeddings
# ---------------------------------------------------------------------------

def _text_for_embedding(row: pd.Series) -> str:
    return " ".join([
        str(row.get("Title", "")),
        str(row.get("Description", "")),
        str(row.get("HRH-II Package Component", "")),
    ])


def compute_embeddings(df: pd.DataFrame) -> Tuple:
    """Return (embeddings, method_label).

    Priority: sentence-transformers > TF-IDF (sklearn) > keyword strings.
    """
    texts = [_text_for_embedding(r) for _, r in df.iterrows()]

    if _SBERT:  # pragma: no cover
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(texts, show_progress_bar=False)
        return emb, "sentence-transformers"

    if _SKLEARN:
        vec = TfidfVectorizer(max_features=500, stop_words="english")
        emb = vec.fit_transform(texts).toarray()
        return emb, "tfidf"

    return texts, "keyword"  # pragma: no cover


# ---------------------------------------------------------------------------
# Step 3 — Clustering
# ---------------------------------------------------------------------------

def _keyword_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets (keyword fallback)."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def cluster_batch(
    batch_df: pd.DataFrame,
    embeddings,
    method: str,
    threshold: float = 0.4,
) -> List[int]:
    """Return one integer cluster label per row in this batch."""
    n = len(batch_df)
    if n == 1:
        return [0]

    if method in ("sentence-transformers", "tfidf") and _SKLEARN:
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=1.0 - threshold,
        )
        labels: List[int] = model.fit_predict(embeddings).tolist()
        return labels

    # Keyword fallback
    texts = [_text_for_embedding(r) for _, r in batch_df.iterrows()]
    labels = [-1] * n
    next_label = 0
    for i in range(n):
        if labels[i] != -1:
            continue
        labels[i] = next_label
        for j in range(i + 1, n):
            if labels[j] == -1 and _keyword_similarity(texts[i], texts[j]) >= threshold:
                labels[j] = next_label
        next_label += 1
    return labels


def assign_clusters(df: pd.DataFrame, batch_size: int = 25) -> pd.DataFrame:
    """Process in batches of `batch_size`, assign globally unique cluster IDs."""
    df = df.copy()
    df["_cluster"] = -1
    global_offset = 0

    for start in range(0, len(df), batch_size):
        end = start + batch_size
        batch = df.iloc[start:end].copy()
        emb, method = compute_embeddings(batch)
        local_labels = cluster_batch(batch, emb, method)
        df.iloc[start:end, df.columns.get_loc("_cluster")] = [
            global_offset + lbl for lbl in local_labels
        ]
        global_offset += max(local_labels) + 1 if local_labels else 0

    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_by_keywords(
    text: str,
    keyword_map: Dict[str, List[str]],
    default: str,
) -> str:
    """Return the category whose keywords score highest against `text`."""
    text_lower = text.lower()
    scores = {
        k: sum(1 for kw in kws if kw in text_lower)
        for k, kws in keyword_map.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default


def _strongest_evidence(strengths: List[str]) -> str:
    """Return the highest-ranked evidence strength string from a list."""
    best, best_score = "", -1
    for s in strengths:
        score = STRENGTH_ORDER.get(s.lower().strip(), 0)
        if score > best_score:
            best_score, best = score, s
    return best if best else "no_evidence_found"


def _merge_bullets(texts: List[str]) -> str:
    """Deduplicate and merge bullet-point style text across multiple strings."""
    seen: set = set()
    bullets: List[str] = []
    for t in texts:
        for line in re.split(r"[•\n;]", t):
            line = line.strip().strip("•-").strip()
            if len(line) > 10:
                key = re.sub(r"\s+", " ", line.lower()[:60])
                if key not in seen:
                    seen.add(key)
                    bullets.append(line)
    if not bullets:
        return "no_evidence_found"
    return "• " + "\n• ".join(bullets)


def _extract_country(text: str) -> str:
    """Extract country name(s) mentioned in text."""
    found: List[str] = []
    for pat in _COUNTRY_PATTERNS:
        found.extend(re.findall(pat, text, re.IGNORECASE))
    clean = sorted(set(f.capitalize() for f in found))
    return ", ".join(clean) if clean else "Not specified"


def _infer_mechanism(description: str, domain: str, problem: str) -> str:
    """Rule-based mechanism description from description text + domain/problem."""
    desc = description.lower()
    parts: List[str] = []
    if any(k in desc for k in ["incentiv", "reward", "bonus", "payment"]):
        parts.append("Financial incentives align individual behaviour with organisational goals")
    if any(k in desc for k in ["supervis", "mentor", "coach"]):
        parts.append("Structured supervision reduces information asymmetry and builds competency")
    if any(k in desc for k in ["data", "monitor", "track", "report", "dashboard"]):
        parts.append("Real-time data feedback enables evidence-based management decisions")
    if any(k in desc for k in ["communit", "social", "peer"]):
        parts.append("Community accountability creates social norms reinforcing expected behaviour")
    if any(k in desc for k in ["penalt", "sanction", "disciplin"]):
        parts.append("Enforcement mechanisms deter non-compliance by raising the cost of absence")
    if any(k in desc for k in ["train", "capacit", "skill"]):
        parts.append("Capacity building raises competence and intrinsic motivation")
    if not parts:
        parts.append(f"Addresses {problem.lower()} through {domain.lower()} improvements")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Step 4 — Aggregate cluster → canonical row
# ---------------------------------------------------------------------------

def aggregate_cluster(cluster_df: pd.DataFrame, cluster_id: int) -> Dict:
    """Produce one canonical intervention dict from all rows in a cluster."""
    titles = cluster_df["Title"].tolist()
    descriptions = cluster_df["Description"].tolist()
    components = cluster_df["HRH-II Package Component"].tolist()
    references = cluster_df["Reference"].tolist()
    intervention_ids = cluster_df["Intervention ID"].tolist()

    combined_text = " ".join(filter(None, titles + descriptions))

    # Canonical title: shortest non-empty title
    titles_clean = [t.strip() for t in titles if t.strip()]
    canonical_title = (
        min(titles_clean, key=len) if titles_clean
        else f"Intervention Cluster {cluster_id}"
    )

    # Intervention family: most common HRH-II Package Component
    component_counts = Counter(c.strip() for c in components if c.strip())
    family = component_counts.most_common(1)[0][0] if component_counts else "General"

    # Description: extractive — longest description, capped at 3 sentences
    desc_texts = [d for d in descriptions if d.strip()]
    if desc_texts:
        best_desc = max(desc_texts, key=len)
        sentences = re.split(r"(?<=[.!?])\s+", best_desc)
        description = " ".join(sentences[:3])
    else:
        description = "no_evidence_found"

    problem = _classify_by_keywords(combined_text, PROBLEM_KEYWORDS, "Productivity")
    domain = _classify_by_keywords(combined_text, DOMAIN_KEYWORDS, "Enabling Environment")
    mechanism = _infer_mechanism(description, domain, problem)

    # Evidence
    strengths = [r.strip() for r in cluster_df["Strength of evidence"].tolist() if r.strip()]
    strength = _strongest_evidence(strengths)

    evidence_types = sorted(set(
        t.strip()
        for t in cluster_df["Evidence design/type"].tolist()
        if t.strip()
    ))

    # Evidence summary: first sentence of each unique description (up to 3)
    seen_sents: set = set()
    ev_sentences: List[str] = []
    for d in desc_texts:
        first = re.split(r"(?<=[.!?])\s+", d.strip())[0]
        key = first.lower()[:80]
        if key not in seen_sents:
            seen_sents.add(key)
            ev_sentences.append(first)
        if len(ev_sentences) >= 3:
            break
    evidence_summary = " | ".join(ev_sentences) if ev_sentences else "no_evidence_found"

    # Implementation considerations
    impl_texts = cluster_df["Implementation considerations"].tolist()
    impl = _merge_bullets(impl_texts)

    # Expected impact — prefer sentences with quantities
    impact_texts = cluster_df["Expected impact"].tolist()
    quant_re = re.compile(r"\d+\s*%|reduced by|increased by|improvement", re.IGNORECASE)
    quant = [t for t in impact_texts if quant_re.search(t)]
    impact_pool = quant if quant else [t for t in impact_texts if t.strip()]
    impact = max(impact_pool, key=len, default="no_evidence_found")

    return {
        "Canonical_Intervention": canonical_title,
        "Intervention_Family": family,
        "Table3_Domain": domain,
        "Problem_Addressed": problem,
        "Description": description,
        "Mechanism": mechanism,
        "Evidence_Summary": evidence_summary,
        "Strength_of_Evidence": strength,
        "Evidence_Types": "; ".join(evidence_types) if evidence_types else "no_evidence_found",
        "Implementation_Considerations": impl,
        "Expected_Impact": impact,
        "_cluster_id": cluster_id,
        "_intervention_ids": "; ".join(str(i) for i in intervention_ids if str(i).strip()),
        "_references": "; ".join(dict.fromkeys(r for r in references if r.strip())),
    }


# ---------------------------------------------------------------------------
# Step 5 — Transferability scoring
# ---------------------------------------------------------------------------

def score_transferability(row: Dict) -> Dict:
    """Score transferability to Ethiopia's low-resource, rural, community HEP context."""
    text = " ".join([
        str(row.get("Description", "")),
        str(row.get("Mechanism", "")),
        str(row.get("Implementation_Considerations", "")),
    ]).lower()

    # System Fit (0–2): does it suit community-based, rural delivery?
    system_fit = 1
    if any(k in text for k in _HIGH_FIT_KW):
        system_fit = 2
    elif any(k in text for k in _LOW_FIT_KW):
        system_fit = 0

    # Resource Feasibility (0–2): can it run without heavy infrastructure?
    resource_feasibility = 1
    if any(k in text for k in _RESOURCE_LIGHT_KW):
        resource_feasibility = 2
    elif any(k in text for k in _RESOURCE_HEAVY_KW):
        resource_feasibility = 0

    # Implementation Complexity (0–2): 2 = simple, 0 = complex
    impl_complexity = 1
    if any(k in text for k in _SIMPLE_KW):
        impl_complexity = 2
    elif any(k in text for k in _COMPLEX_KW):
        impl_complexity = 0

    total = system_fit + resource_feasibility + impl_complexity

    if total >= 5:
        level = "High"
        rationale = (
            "This intervention aligns well with community-based, low-resource delivery models "
            "such as Ethiopia's HEP. It requires minimal infrastructure and fits existing cadre "
            "roles. Implementation complexity is manageable within current HEP operating conditions."
        )
    elif total >= 3:
        level = "Medium"
        rationale = (
            "This intervention is partially transferable to Ethiopia's HEP context. "
            "Some adaptation may be needed to address resource or infrastructure constraints. "
            "Pilot testing is recommended before scale-up."
        )
    else:
        level = "Low"
        rationale = (
            "Significant barriers exist for direct transfer to Ethiopia's HEP. "
            "The intervention may require substantial investment in infrastructure or specialised "
            "capacity. Contextual adaptation and a phased rollout would be necessary."
        )

    return {**row, "Transferability": level, "Transferability_Rationale": rationale}


# ---------------------------------------------------------------------------
# Step 6 — Evidence map
# ---------------------------------------------------------------------------

def build_evidence_map(
    original_df: pd.DataFrame,
    compendium_df: pd.DataFrame,
) -> pd.DataFrame:
    """Link every original row back to its canonical intervention."""
    cluster_to_canonical: Dict[int, str] = {}
    for _, row in compendium_df.iterrows():
        cluster_to_canonical[int(row["_cluster_id"])] = str(row["Canonical_Intervention"])

    records = []
    for _, row in original_df.iterrows():
        cid = int(row.get("_cluster", -1))
        canonical = cluster_to_canonical.get(cid, "Unknown")
        country = _extract_country(
            str(row.get("Description", "")) + " " + str(row.get("Reference", ""))
        )
        records.append({
            "Canonical_Intervention": canonical,
            "Original_Intervention_ID": row.get("Intervention ID", ""),
            "Country": country,
            "Reference": row.get("Reference", ""),
            "Evidence_Type": row.get("Evidence design/type", ""),
            "Snippet": str(row.get("Description", ""))[:200],
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Output: Excel
# ---------------------------------------------------------------------------

def _apply_sheet_style(ws, headers: List[str]) -> None:  # pragma: no cover
    if not _OPENPYXL:
        return
    thin = Side(style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    alt_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = border

    for col_idx in range(1, len(headers) + 1):
        max_len = max(
            (len(str(ws.cell(row=r, column=col_idx).value or "")) for r in range(1, ws.max_row + 1)),
            default=10,
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

    for row_idx in range(2, ws.max_row + 1):
        fill = alt_fill if row_idx % 2 == 0 else None
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = border
            if fill:
                cell.fill = fill

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def write_excel(
    compendium_df: pd.DataFrame,
    evidence_map_df: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cols1 = [c for c in _COMPENDIUM_COLS if c in compendium_df.columns]
    cols2 = [c for c in _EVIDENCE_MAP_COLS if c in evidence_map_df.columns]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        compendium_df[cols1].to_excel(writer, sheet_name="Compendium", index=False)
        evidence_map_df[cols2].to_excel(writer, sheet_name="Evidence_Map", index=False)

        if _OPENPYXL:
            _apply_sheet_style(writer.sheets["Compendium"], cols1)
            _apply_sheet_style(writer.sheets["Evidence_Map"], cols2)


# ---------------------------------------------------------------------------
# Output: Word
# ---------------------------------------------------------------------------

def write_word(compendium_df: pd.DataFrame, output_path: Path) -> None:
    if not _DOCX:  # pragma: no cover
        print("  [WARN] python-docx not installed — skipping Word output")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()

    heading = doc.add_heading(
        "HRH Compendium: Interventions for Ethiopia's Health Extension Program", level=0
    )
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(
        "This compendium synthesises evidence-based interventions addressing accountability, "
        "absenteeism, and productivity in community health workforce settings, with a focus on "
        "transferability to Ethiopia's Health Extension Program (HEP)."
    )

    def _bold_field(label: str, value: str) -> None:
        p = doc.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(str(value) if value else "Not specified")

    for domain, group in compendium_df.groupby("Table3_Domain"):
        doc.add_heading(str(domain), level=1)

        for _, row in group.iterrows():
            doc.add_heading(str(row.get("Canonical_Intervention", "")), level=2)

            _bold_field("Problem Addressed", row.get("Problem_Addressed", ""))
            _bold_field("Intervention Family", row.get("Intervention_Family", ""))
            _bold_field("Description", row.get("Description", ""))
            _bold_field("Mechanism", row.get("Mechanism", ""))

            # Evidence block
            p = doc.add_paragraph()
            p.add_run("Evidence: ").bold = True
            p.add_run(str(row.get("Evidence_Summary", "")))
            p2 = doc.add_paragraph()
            p2.add_run("  Strength: ").bold = True
            p2.add_run(str(row.get("Strength_of_Evidence", "")))
            p3 = doc.add_paragraph()
            p3.add_run("  Type(s): ").bold = True
            p3.add_run(str(row.get("Evidence_Types", "")))

            _bold_field("Expected Impact", row.get("Expected_Impact", ""))

            # Implementation considerations as bullets
            p = doc.add_paragraph()
            p.add_run("Implementation Considerations:").bold = True
            impl = str(row.get("Implementation_Considerations", ""))
            for bullet in impl.split("\n"):
                bullet = bullet.strip().strip("•").strip()
                if bullet:
                    doc.add_paragraph(bullet, style="List Bullet")

            _bold_field("Transferability", row.get("Transferability", ""))
            _bold_field("Rationale", row.get("Transferability_Rationale", ""))
            _bold_field("References", row.get("_references", ""))

            doc.add_paragraph("─" * 60)

    doc.save(output_path)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path: Path, output_dir: Path) -> None:
    print(f"[1/6] Loading data from {input_path} ...")
    df = load_data(input_path)
    print(f"      {len(df)} rows loaded.")

    print("[2/6] Assigning clusters (batch_size=25) ...")
    df = assign_clusters(df, batch_size=25)
    n_clusters = df["_cluster"].nunique()
    print(f"      {n_clusters} clusters identified.")

    print("[3/5] Aggregating clusters → canonical interventions ...")
    canonical_rows = []
    for cid, group in df.groupby("_cluster"):
        row = aggregate_cluster(group.copy(), int(cid))
        row = score_transferability(row)
        canonical_rows.append(row)
    compendium_df = pd.DataFrame(canonical_rows)
    print(f"      {len(compendium_df)} canonical interventions produced.")

    print("[4/6] Building evidence map ...")
    evidence_map_df = build_evidence_map(df, compendium_df)

    print(f"[5/6] Writing Excel → {output_dir / 'HRH_Compendium.xlsx'} ...")
    write_excel(compendium_df, evidence_map_df, output_dir / "HRH_Compendium.xlsx")

    print(f"[6/6] Writing Word  → {output_dir / 'HRH_Compendium.docx'} ...")
    write_word(compendium_df, output_dir / "HRH_Compendium.docx")

    print("\nDone. Output files:")
    print(f"  {output_dir / 'HRH_Compendium.xlsx'}")
    print(f"  {output_dir / 'HRH_Compendium.docx'}")


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="Build HRH Compendium from raw interventions Excel"
    )
    parser.add_argument(
        "--input",
        default="./input/interventions.xlsx",
        help="Path to input Excel file (default: ./input/interventions.xlsx)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory (default: ./output)",
    )
    args = parser.parse_args()
    run_pipeline(Path(args.input), Path(args.output_dir))


if __name__ == "__main__":
    main()
