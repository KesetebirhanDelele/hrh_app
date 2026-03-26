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
from datetime import datetime
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
    "Intervention_Package",
    "Variants_List",
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


# Step 7 — Package keyword map (domain → package → trigger keywords)
# Each domain has ≤8 packages; keywords are matched against the canonical
# intervention's combined text (title + description + mechanism).
PACKAGE_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "Motivation & Accountability": {
        "Financial Incentive Systems": [
            "incentiv", "bonus", "payment", "salary", "pbf", "financial reward", "cash",
        ],
        "Non-Financial Recognition Programs": [
            "recogn", "award", "certificate", "non-financial", "honor", "appreciat", "praise",
        ],
        "Performance Management Systems": [
            "performance management", "appraisal", "evaluation", "kpi", "target", "objective",
        ],
        "Attendance Monitoring and Enforcement": [
            "attendance", "absentee", "presence", "register", "biometric", "check-in",
        ],
        "Sanctions and Disciplinary Measures": [
            "sanction", "penalt", "disciplin", "punish", "consequence", "demotion",
        ],
        "Motivation and Engagement Programs": [
            "motivat", "engag", "morale", "satisf", "retention", "job satisfaction",
        ],
    },
    "Workforce Support": {
        "Supervision Systems": [
            "supervis", "oversee", "supervisor visit", "supportive supervision",
        ],
        "Mentorship and Coaching": [
            "mentor", "coach", "buddy", "guided practice", "on-the-job",
        ],
        "Training and Capacity Building": [
            "train", "capacit", "skill", "education", "learning", "workshop", "orientation",
        ],
        "Career Development Pathways": [
            "career", "promot", "advancement", "pathway", "progression", "specializ",
        ],
        "Welfare and Wellbeing Support": [
            "welfare", "wellbeing", "well-being", "burnout", "stress", "psychosocial",
        ],
    },
    "Tools & Infrastructure": {
        "Digital Health Systems": [
            "digital", "app", "mobile", "software", "platform", "ehealth", "mhealth", "electronic",
        ],
        "Data and Monitoring Systems": [
            "data", "dashboard", "report", "hris", "information system", "database", "registry",
        ],
        "Supply Chain and Logistics Tools": [
            "supply", "logistics", "commodit", "equipment", "stock", "material", "inventory",
        ],
        "Communication Technology": [
            "sms", "phone", "radio", "ict", "telecommunicat", "hotline",
        ],
    },
    "Community Engagement": {
        "Community Accountability Mechanisms": [
            "communit", "account", "scorecard", "citizen", "public report", "transparency",
        ],
        "Participatory Planning and Feedback": [
            "participat", "dialogue", "feedback", "forum", "meeting", "consultation",
        ],
        "Social Norm and Behaviour Change": [
            "social norm", "behaviour change", "culture", "attitude", "belief", "stigma",
        ],
        "Community Health Worker Support Networks": [
            "chw", "community health worker", "volunteer", "lay worker", "peer network",
        ],
    },
    "Service Delivery Processes": {
        "Clinical Protocols and Guidelines": [
            "protocol", "guideline", "standard", "procedure", "clinical", "checklist",
        ],
        "Referral and Linkage Systems": [
            "referral", "linkage", "pathway", "transfer", "follow-up", "continuity",
        ],
        "Workflow and Task Optimisation": [
            "workflow", "task shift", "workload", "scheduling", "timetable", "roster",
        ],
        "Quality Improvement Cycles": [
            "quality", "improvement", "audit", "review", "assessment", "continuous",
        ],
    },
    "Enabling Environment": {
        "Policy and Regulatory Frameworks": [
            "policy", "legal", "regulat", "law", "framework", "legislation", "decree",
        ],
        "Leadership and Governance Structures": [
            "leadership", "govern", "management", "administrat", "director", "oversight",
        ],
        "Workplace Conditions and Infrastructure": [
            "workplace", "environment", "condition", "infrastructure", "facilit", "housing",
        ],
        "Financing and Resource Mobilisation": [
            "financ", "fund", "budget", "resource", "investment", "donor", "allocation",
        ],
    },
}

_MAX_PACKAGES_PER_DOMAIN = 8
_FALLBACK_PACKAGE = "General Interventions"

# ---------------------------------------------------------------------------
# CHW scope filter constants
# ---------------------------------------------------------------------------

# Positive signals — any match → include
_CHW_INCLUDE_TERMS = [
    "community health worker", "chw", "health extension worker", "hew",
    "community health volunteer", "lay health worker", "health extension",
    "community health", "village health", "community-based health",
    "outreach worker", "frontline health", "community worker",
    "community health aide", "community health promoter",
    "primary health care worker", "health extension program",
]

# Supervisor context — if paired with community/PHC signal → include
_CHW_SUPERVISOR_TERMS = [
    "supportive supervision", "chw supervisor", "hew supervisor",
    "community health supervisor", "primary care supervisor",
]

# Hard exclusion — primarily non-CHW specialist cadres
_CHW_EXCLUDE_PRIMARY = [
    "physician", "medical specialist", "specialist physician",
    "pharmacist", "pharmacy technician", "tertiary care",
    "tertiary hospital", "secondary care", "inpatient care",
    "intensive care unit", "operating theatre", "surgical ward",
]

# Nurse exclusion context (unless community/supervisory)
_NURSE_EXCLUDE_CONTEXT = [
    "bedside nursing", "inpatient nursing", "ward nurse",
    "hospital nurse", "clinical nursing care",
]

# Country-name strip pattern for description cleanup
_COUNTRY_STRIP_RE = re.compile(
    r"\b(Ethiopia[n]?|Kenya[n]?|Uganda[n]?|Nigeria[n]?|Tanzania[n]?|"
    r"Ghana[ian]?|India[n]?|Bangladesh[i]?|Malawi[an]?|Rwanda[n]?|"
    r"Zambia[n]?|Zimbabwe[an]?)\b",
    re.IGNORECASE,
)

# Target canonical intervention range
_TARGET_MIN_CANONICAL = 80
_TARGET_MAX_CANONICAL = 120
_CONSOLIDATE_THRESHOLD = 150  # trigger second-pass merging above this count


# ---------------------------------------------------------------------------
# CHW filter functions
# ---------------------------------------------------------------------------

def is_relevant_to_chw(row: pd.Series) -> bool:
    """Return True if this row is relevant to CHW / frontline PHC workforce."""
    text = " ".join([
        str(row.get("Title", "")),
        str(row.get("Description", "")),
        str(row.get("Target cadre & setting", "")),
        str(row.get("HRH-II Package Component", "")),
    ]).lower()

    # Strong CHW inclusion signals
    if any(term in text for term in _CHW_INCLUDE_TERMS):
        return True

    # Supervisor working with community / frontline staff
    if any(term in text for term in _CHW_SUPERVISOR_TERMS):
        return True
    if "supervis" in text and any(t in text for t in ["community", "primary health", "frontline"]):
        return True

    # Hard exclusions
    if any(term in text for term in _CHW_EXCLUDE_PRIMARY):
        return False

    # Nurses: include only if clearly community / supervisory context
    if "nurse" in text or "nursing" in text:
        if any(t in text for t in ["community", "supervis", "primary health", "chw", "hew"]):
            return True
        if any(t in text for t in _NURSE_EXCLUDE_CONTEXT):
            return False

    # Default: include (HRH context is broadly relevant)
    return True


def filter_chw_relevant(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only CHW-relevant rows; log removed count."""
    before = len(df)
    mask = df.apply(is_relevant_to_chw, axis=1)
    filtered = df[mask].reset_index(drop=True)
    removed = before - len(filtered)
    pct = removed / before * 100 if before else 0
    print(f"      CHW filter: {before} → {len(filtered)} rows kept "
          f"({removed} removed, {pct:.1f}%)")
    return filtered


# ---------------------------------------------------------------------------
# Description cleanup
# ---------------------------------------------------------------------------

def _strip_country_refs(text: str) -> str:
    """Replace country proper nouns with 'the country' for generalisability."""
    return _COUNTRY_STRIP_RE.sub("the country", text)


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


def _agglom_labels(emb, dist_threshold: float) -> List[int]:
    """Run AgglomerativeClustering with cosine metric at given distance threshold."""
    model = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=dist_threshold,
    )
    return model.fit_predict(emb).tolist()


def assign_clusters(
    df: pd.DataFrame,
    target_min: int = _TARGET_MIN_CANONICAL,
    target_max: int = _TARGET_MAX_CANONICAL,
    batch_size: int = 25,  # kept for API compatibility
) -> pd.DataFrame:
    """Global TF-IDF clustering with binary search on distance threshold.

    For large DataFrames (n > target_max), binary-searches for the distance
    threshold that lands the cluster count inside [target_min, target_max].
    For small DataFrames (tests), uses a fixed threshold of 0.6.

    Higher distance_threshold → more merging → fewer clusters.
    Lower  distance_threshold → less  merging → more  clusters.
    """
    df = df.copy()
    n = len(df)

    if n == 0:
        df["_cluster"] = pd.Series(dtype=int)
        return df
    if n == 1:
        df["_cluster"] = [0]
        return df

    emb, method = compute_embeddings(df)

    if not _SKLEARN or method == "keyword":
        # Keyword fallback: linear scan with fixed 0.3 Jaccard threshold
        texts = [_text_for_embedding(r) for _, r in df.iterrows()]
        labels = [-1] * n
        next_label = 0
        for i in range(n):
            if labels[i] != -1:
                continue
            labels[i] = next_label
            for j in range(i + 1, n):
                if labels[j] == -1 and _keyword_similarity(texts[i], texts[j]) >= 0.3:
                    labels[j] = next_label
            next_label += 1
        df["_cluster"] = labels
        return df

    # For small DataFrames (unit tests), skip binary search
    if n <= target_max:
        df["_cluster"] = _agglom_labels(emb, 0.6)
        return df

    # Binary search: find dist_threshold ∈ (0, 1) that yields target cluster count
    lo, hi = 0.01, 0.99
    best_labels: List[int] = list(range(n))

    for _ in range(30):
        mid = (lo + hi) / 2
        try:
            labels = _agglom_labels(emb, mid)
        except Exception:
            break
        n_clusters = len(set(labels))
        best_labels = labels
        if target_min <= n_clusters <= target_max:
            break
        elif n_clusters > target_max:
            lo = mid   # need more merging → raise threshold
        else:
            hi = mid   # need less merging → lower threshold

    df["_cluster"] = best_labels
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

    # Description: extractive — longest description, capped at 2 sentences,
    # with country-specific references stripped for generalisability.
    desc_texts = [d for d in descriptions if d.strip()]
    if desc_texts:
        best_desc = max(desc_texts, key=len)
        sentences = re.split(r"(?<=[.!?])\s+", best_desc)
        description = _strip_country_refs(" ".join(sentences[:2]))
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
        # All original titles — used for Variants section and Excel column
        "_variant_titles": [t.strip() for t in titles if t.strip()],
        "Variants_List": "; ".join(dict.fromkeys(t.strip() for t in titles if t.strip())),
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
# Post-merge consolidation
# ---------------------------------------------------------------------------

def _consolidate_if_oversized(
    compendium_df: pd.DataFrame,
    max_count: int = _CONSOLIDATE_THRESHOLD,
    target_min: int = _TARGET_MIN_CANONICAL,
    target_max: int = _TARGET_MAX_CANONICAL,
) -> pd.DataFrame:
    """If compendium has >max_count rows, run a second global clustering pass
    on the canonical titles + descriptions to reach the target range.
    """
    if len(compendium_df) <= max_count:
        return compendium_df

    print(f"      {len(compendium_df)} canonical interventions > {max_count} — "
          f"running consolidation pass to target {target_min}–{target_max} ...")

    # Build a proxy DataFrame where canonical fields map to embedding fields
    proxy = compendium_df[["Canonical_Intervention", "Description", "Table3_Domain"]].rename(
        columns={
            "Canonical_Intervention": "Title",
            "Description": "Description",
            "Table3_Domain": "HRH-II Package Component",
        }
    ).copy()

    emb, method = compute_embeddings(proxy)

    if not _SKLEARN or method == "keyword":
        return compendium_df  # can't consolidate without sklearn

    lo, hi = 0.01, 0.99
    best_labels: List[int] = list(range(len(compendium_df)))

    for _ in range(30):
        mid = (lo + hi) / 2
        try:
            labels = _agglom_labels(emb, mid)
        except Exception:
            break
        n_c = len(set(labels))
        best_labels = labels
        if target_min <= n_c <= target_max:
            break
        elif n_c > target_max:
            lo = mid
        else:
            hi = mid

    compendium_df = compendium_df.copy()
    compendium_df["_super_cluster"] = best_labels
    new_rows: List[Dict] = []

    for sc, grp in compendium_df.groupby("_super_cluster"):
        # Representative row: strongest evidence strength
        def _strength_val(s: str) -> int:
            return STRENGTH_ORDER.get(s.lower().strip(), 0)

        best_idx = grp["Strength_of_Evidence"].map(_strength_val).idxmax()
        rep = grp.loc[best_idx].to_dict()

        # Merge variant titles from all members
        all_variants: List[str] = []
        for _, row in grp.iterrows():
            vt = row.get("_variant_titles", [])
            if isinstance(vt, list):
                all_variants.extend(vt)
            # Also include the canonical intervention names being merged
            ci = str(row.get("Canonical_Intervention", ""))
            if ci:
                all_variants.append(ci)
        rep["_variant_titles"] = list(dict.fromkeys(t for t in all_variants if t))
        rep["Variants_List"] = "; ".join(rep["_variant_titles"])

        # Merge evidence types
        ev_types = sorted(set(
            t.strip()
            for _, row in grp.iterrows()
            for t in str(row.get("Evidence_Types", "")).split(";")
            if t.strip() and t.strip() != "no_evidence_found"
        ))
        rep["Evidence_Types"] = "; ".join(ev_types) if ev_types else "no_evidence_found"

        # Merge references
        refs = list(dict.fromkeys(
            r.strip()
            for _, row in grp.iterrows()
            for r in str(row.get("_references", "")).split(";")
            if r.strip()
        ))
        rep["_references"] = "; ".join(refs)
        new_rows.append(rep)

    result = pd.DataFrame(new_rows).drop(columns=["_super_cluster"], errors="ignore")
    print(f"      Consolidated to {len(result)} canonical interventions.")
    return result


# ---------------------------------------------------------------------------
# Step 7 — Package assignment
# ---------------------------------------------------------------------------

def _score_package(text: str, package_kws: Dict[str, List[str]]) -> str:
    """Return the best-matching package label for `text`, or fallback."""
    text_lower = text.lower()
    scores = {
        pkg: sum(1 for kw in kws if kw in text_lower)
        for pkg, kws in package_kws.items()
    }
    best_pkg = max(scores, key=scores.get)
    return best_pkg if scores[best_pkg] > 0 else _FALLBACK_PACKAGE


def assign_packages(compendium_df: pd.DataFrame) -> pd.DataFrame:
    """Add Intervention_Package column.

    Rules:
    - Each intervention belongs to exactly ONE package.
    - Packages are domain-specific (PACKAGE_KEYWORDS).
    - Max 8 packages per domain; excess packages merged into the smallest existing one.
    """
    df = compendium_df.copy()
    packages: List[str] = []

    for _, row in df.iterrows():
        domain = str(row.get("Table3_Domain", ""))
        combined = " ".join([
            str(row.get("Canonical_Intervention", "")),
            str(row.get("Description", "")),
            str(row.get("Mechanism", "")),
        ])
        domain_pkgs = PACKAGE_KEYWORDS.get(domain, {})
        pkg = _score_package(combined, domain_pkgs) if domain_pkgs else _FALLBACK_PACKAGE
        packages.append(pkg)

    df["Intervention_Package"] = packages

    # Enforce max 8 packages per domain
    for domain, group in df.groupby("Table3_Domain"):
        unique_pkgs = df.loc[group.index, "Intervention_Package"].unique().tolist()
        if len(unique_pkgs) > _MAX_PACKAGES_PER_DOMAIN:
            # Count interventions per package; merge smallest into next-smallest
            counts = df.loc[group.index, "Intervention_Package"].value_counts()
            # Sort ascending by count; keep top-8, merge remainder into 8th
            keep = counts.index.tolist()[: _MAX_PACKAGES_PER_DOMAIN]
            merge_target = keep[-1]
            mask = group.index[~df.loc[group.index, "Intervention_Package"].isin(keep)]
            df.loc[mask, "Intervention_Package"] = merge_target

    return df


# ---------------------------------------------------------------------------
# Deduplication of canonical names
# ---------------------------------------------------------------------------

def deduplicate_canonical_names(compendium_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure every Canonical_Intervention name is unique.

    When two or more clusters produce the same shortest title (common with
    large datasets), append a parenthesised counter: "Title (2)", "Title (3)".
    The first occurrence keeps the original name.
    """
    df = compendium_df.copy()
    seen: Dict[str, int] = {}
    new_names: List[str] = []
    for name in df["Canonical_Intervention"]:
        if name not in seen:
            seen[name] = 1
            new_names.append(name)
        else:
            seen[name] += 1
            new_names.append(f"{name} ({seen[name]})")
    df["Canonical_Intervention"] = new_names
    return df


# ---------------------------------------------------------------------------
# Step 10 — Validation
# ---------------------------------------------------------------------------

def validate_structure(compendium_df: pd.DataFrame) -> None:
    """Validate compendium structure and log warnings.

    Raises ValueError on hard failures; prints warnings for soft violations.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # No duplicate canonical intervention names
    dupes = compendium_df["Canonical_Intervention"].duplicated()
    if dupes.any():
        dupe_names = compendium_df.loc[dupes, "Canonical_Intervention"].tolist()
        errors.append(f"Duplicate canonical intervention names: {dupe_names}")

    for domain, group in compendium_df.groupby("Table3_Domain"):
        # Each domain must have ≥1 package
        if "Intervention_Package" not in group.columns:
            errors.append(f"Domain '{domain}': Intervention_Package column missing")
            continue

        pkgs = group["Intervention_Package"].unique().tolist()
        if not pkgs:
            errors.append(f"Domain '{domain}': no packages assigned")

        # Each package must have ≥1 intervention (guaranteed by assign_packages, but verify)
        for pkg in pkgs:
            pkg_count = (group["Intervention_Package"] == pkg).sum()
            if pkg_count == 0:
                errors.append(f"Domain '{domain}' / Package '{pkg}': 0 interventions")

        # Warn if too granular
        if len(pkgs) > 10:
            warnings.append(
                f"Domain '{domain}' has {len(pkgs)} packages (>10) — consider consolidating"
            )

    for w in warnings:
        print(f"  [WARN] {w}")

    if errors:
        raise ValueError("Structure validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


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
    """Write policy-ready Word document.

    Structure:
        Heading 1  → Table3_Domain
        Heading 2  → Intervention_Package
        Heading 3  → Canonical_Intervention
                       ... content ...
                       Variants / Examples (original titles from cluster)
    """
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

    pkg_col = "Intervention_Package" if "Intervention_Package" in compendium_df.columns else None

    # Deduplicate by canonical name to guarantee each appears only once
    seen_canonical: set = set()

    for domain, domain_group in compendium_df.groupby("Table3_Domain"):
        doc.add_heading(str(domain), level=1)

        # Group by package within this domain
        if pkg_col:
            pkg_groups = domain_group.groupby(pkg_col)
        else:
            pkg_groups = [("General Interventions", domain_group)]

        for package, pkg_group in pkg_groups:
            doc.add_heading(str(package), level=2)

            for _, row in pkg_group.iterrows():
                canonical = str(row.get("Canonical_Intervention", ""))
                # Step 8.1: skip duplicates
                if canonical in seen_canonical:
                    continue
                seen_canonical.add(canonical)

                doc.add_heading(canonical, level=3)

                _bold_field("Problem Addressed", row.get("Problem_Addressed", ""))
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

                # Step 8.2: Variants / Examples — original titles from cluster
                variant_titles = row.get("_variant_titles", [])
                if isinstance(variant_titles, list) and len(variant_titles) > 1:
                    p = doc.add_paragraph()
                    p.add_run("Variants / Examples:").bold = True
                    for vt in variant_titles:
                        doc.add_paragraph(vt, style="List Bullet")

                doc.add_paragraph("─" * 60)

    doc.save(output_path)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path: Path, output_dir: Path) -> None:
    timestamp = datetime.now().strftime("%m%d%Y_%H%M%S")
    excel_out = output_dir / f"HRH_Compendium_{timestamp}.xlsx"
    word_out = output_dir / f"HRH_Compendium_{timestamp}.docx"

    # ------------------------------------------------------------------
    print(f"[1/9] Loading data from {input_path} ...")
    df = load_data(input_path)
    initial_count = len(df)
    print(f"      Initial rows: {initial_count}")

    # ------------------------------------------------------------------
    print("[2/9] Filtering to CHW-relevant interventions ...")
    df = filter_chw_relevant(df)
    filtered_count = len(df)
    print(f"      Rows after filter: {filtered_count}")

    # ------------------------------------------------------------------
    print(f"[3/9] Global clustering (target {_TARGET_MIN_CANONICAL}–{_TARGET_MAX_CANONICAL} "
          f"canonical interventions) ...")
    df = assign_clusters(df, target_min=_TARGET_MIN_CANONICAL, target_max=_TARGET_MAX_CANONICAL)
    n_clusters = df["_cluster"].nunique()
    print(f"      {n_clusters} raw clusters identified.")

    # ------------------------------------------------------------------
    print("[4/9] Aggregating clusters → canonical interventions ...")
    canonical_rows = []
    for cid, group in df.groupby("_cluster"):
        row = aggregate_cluster(group.copy(), int(cid))
        row = score_transferability(row)
        canonical_rows.append(row)
    compendium_df = pd.DataFrame(canonical_rows)
    compendium_df = deduplicate_canonical_names(compendium_df)
    n_dupes = sum(1 for n in compendium_df["Canonical_Intervention"] if re.search(r"\s\(\d+\)$", n))
    if n_dupes:
        print(f"      {n_dupes} duplicate name(s) disambiguated.")
    print(f"      {len(compendium_df)} canonical interventions after first pass.")

    # ------------------------------------------------------------------
    print("[5/9] Consolidating if oversized ...")
    compendium_df = _consolidate_if_oversized(compendium_df)
    compendium_df = deduplicate_canonical_names(compendium_df)
    final_canonical_count = len(compendium_df)
    print(f"      Final canonical intervention count: {final_canonical_count}")

    # ------------------------------------------------------------------
    print("[6/9] Assigning intervention packages ...")
    compendium_df = assign_packages(compendium_df)
    for domain, grp in compendium_df.groupby("Table3_Domain"):
        pkg_count = grp["Intervention_Package"].nunique()
        print(f"      {domain}: {pkg_count} package(s)")

    # ------------------------------------------------------------------
    print("[7/9] Validating structure ...")
    validate_structure(compendium_df)
    print("      Validation passed.")

    # ------------------------------------------------------------------
    print("[8/9] Building evidence map ...")
    evidence_map_df = build_evidence_map(df, compendium_df)

    # ------------------------------------------------------------------
    print(f"[9/9] Writing outputs ...")
    write_excel(compendium_df, evidence_map_df, excel_out)
    write_word(compendium_df, word_out)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print(f"  Initial rows:              {initial_count}")
    print(f"  After CHW filter:          {filtered_count}")
    print(f"  Canonical interventions:   {final_canonical_count}")
    print(f"  Excel: {excel_out}")
    print(f"  Word:  {word_out}")
    print("=" * 60)


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
