# tools/comparator_index.py
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

NUMERIC_COLS_DEFAULT = [
    "GDP", "Population", "Urban Pop",
    "MMR", "U5M", "NMR", "CPR", "TFR",
    "PHC"
]

# “Better” direction for aspirational selection (lower is better for mortality/fertility)
LOWER_BETTER = {"MMR", "U5M", "NMR", "TFR"}
HIGHER_BETTER = {"CPR", "PHC"}  # keep GDP/Urban/Pop as context, not “better/worse” targets


def normalize_colnames(cols):
    # make matching more forgiving (handles extra spaces, different casing)
    out = []
    for c in cols:
        c2 = re.sub(r"\s+", " ", str(c)).strip()
        out.append(c2)
    return out


def zscore(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - mu) / sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Path to Excel file")
    ap.add_argument("--sheet", default=None, help="Sheet name (optional)")
    ap.add_argument("--country", required=True, help="Target country name (e.g., Ethiopia)")
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--aspirational_k", type=int, default=8)
    ap.add_argument("--numeric_cols", default=",".join(NUMERIC_COLS_DEFAULT))
    ap.add_argument("--weights", default=None,
                    help="Optional weights as col=weight,... e.g. MMR=1,U5M=1,NMR=1,TFR=0.7,CPR=0.7,PHC=1,GDP=0.4,Urban Pop=0.3")
    ap.add_argument("--peer_filter", action="store_true",
                    help="Apply peer filtering by Income group + Region + CHP + Types of CHW if present (recommended)")
    args = ap.parse_args()

    xls_path = Path(args.file)
    if not xls_path.exists():
        raise SystemExit(f"File not found: {xls_path}")

    # Load excel
    # If no sheet specified, use the first sheet (index 0)
    sheet_to_read = args.sheet if args.sheet is not None else 0
    df = pd.read_excel(xls_path, sheet_name=sheet_to_read)
    df.columns = normalize_colnames(df.columns)

    # Required ID column
    if "Country" not in df.columns:
        raise SystemExit("Expected a 'Country' column in the Excel file.")

    # Clean numeric columns
    numeric_cols = [c.strip() for c in args.numeric_cols.split(",") if c.strip()]
    existing_numeric = [c for c in numeric_cols if c in df.columns]

    if len(existing_numeric) == 0:
        raise SystemExit(f"None of the numeric columns were found. Looked for: {numeric_cols}\nAvailable: {list(df.columns)}")

    for c in existing_numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows missing too much numeric data
    df["_missing_n"] = df[existing_numeric].isna().sum(axis=1)
    df = df[df["_missing_n"] <= max(2, int(len(existing_numeric) * 0.25))].copy()

    # Locate target row
    target_mask = df["Country"].astype(str).str.strip().str.lower() == args.country.strip().lower()
    if target_mask.sum() != 1:
        raise SystemExit(f"Could not uniquely find target country '{args.country}'. Matches found: {int(target_mask.sum())}")

    target = df.loc[target_mask].iloc[0]

    # Optional peer filter (categorical) – does NOT affect scoring columns, only candidate set
    candidates = df.copy()
    peer_cols = [c for c in ["Income group", "Region", "CHP", "Types of CHW"] if c in df.columns]
    if args.peer_filter and peer_cols:
        for pc in peer_cols:
            tv = target.get(pc, None)
            if pd.notna(tv) and str(tv).strip() != "":
                candidates = candidates[candidates[pc].astype(str).str.strip() == str(tv).strip()].copy()

    # Remove target itself from candidates
    candidates = candidates[candidates["Country"].astype(str).str.strip().str.lower() != args.country.strip().lower()].copy()

    # Build weights
    weights = {c: 1.0 for c in existing_numeric}
    if args.weights:
        for part in args.weights.split(","):
            part = part.strip()
            if not part:
                continue
            k, v = part.split("=")
            k = k.strip()
            v = float(v.strip())
            if k in weights:
                weights[k] = v

    # Z-score normalize on combined set so distances are comparable
    all_df = pd.concat([candidates, df.loc[target_mask]], axis=0).copy()
    for c in existing_numeric:
        all_df[f"z_{c}"] = zscore(all_df[c])

    target_row = all_df[all_df["Country"].astype(str).str.strip().str.lower() == args.country.strip().lower()].iloc[0]

    # Weighted Euclidean distance in z-space
    def dist(row):
        s = 0.0
        for c in existing_numeric:
            w = weights.get(c, 1.0)
            a = row[f"z_{c}"]
            b = target_row[f"z_{c}"]
            if np.isnan(a) or np.isnan(b):
                continue
            s += w * (a - b) ** 2
        return float(np.sqrt(s))

    cand_scored = all_df[all_df["Country"].astype(str).str.strip().str.lower() != args.country.strip().lower()].copy()
    cand_scored["similarity_distance"] = cand_scored.apply(dist, axis=1)
    cand_scored = cand_scored.sort_values("similarity_distance", ascending=True)

    # Similarity comparators: smallest distance
    similarity = cand_scored.head(args.topk).copy()

    # Aspirational comparators:
    # - still reasonably close (top 30% by similarity distance)
    # - but “better” in at least 3 key outcome dimensions (MMR/U5M/NMR/TFR lower; CPR/PHC higher)
    cutoff_idx = max(int(len(cand_scored) * 0.30), args.aspirational_k * 3)
    pool = cand_scored.head(cutoff_idx).copy()

    def aspirational_better(row):
        better = 0
        for c in existing_numeric:
            tv = target.get(c, np.nan)
            rv = row.get(c, np.nan)
            if pd.isna(tv) or pd.isna(rv):
                continue
            if c in LOWER_BETTER and rv < tv:
                better += 1
            if c in HIGHER_BETTER and rv > tv:
                better += 1
        return better

    pool["better_count"] = pool.apply(aspirational_better, axis=1)
    aspirational = pool[pool["better_count"] >= 3].sort_values(
        ["better_count", "similarity_distance"], ascending=[False, True]
    ).head(args.aspirational_k)

    # Output
    # Build output columns
    peer_cols_present = [pc for pc in ["Region", "Income group", "CHP", "Types of CHW"] if pc in df.columns]

    # Similarity comparators: no better_count column
    similarity_out_cols = ["Country"] + peer_cols_present + ["similarity_distance"]

    # Aspirational comparators: includes better_count
    aspirational_out_cols = ["Country"] + peer_cols_present + ["similarity_distance", "better_count"]

    print("\n=== TARGET ===")
    print(target[["Country"] + [c for c in ["Region","Income group","CHP","Types of CHW"] if c in df.columns] + existing_numeric].to_string())

    print("\n=== SIMILARITY COMPARATORS ===")
    print(similarity[similarity_out_cols + existing_numeric].to_string(index=False))

    print("\n=== ASPIRATIONAL COMPARATORS ===")
    if len(aspirational) == 0:
        print("No aspirational matches found under current rules. Try: reduce better_count threshold to 1, or widen pool to top 50%.")
    else:
        print(aspirational[aspirational_out_cols + existing_numeric].to_string(index=False))

    # Save file
    out_path = Path("outputs") / "comparator_index"
    out_path.mkdir(parents=True, exist_ok=True)
    similarity.to_csv(out_path / "similarity_comparators.csv", index=False)
    aspirational.to_csv(out_path / "aspirational_comparators.csv", index=False)
    print(f"\nWrote:\n- {out_path/'similarity_comparators.csv'}\n- {out_path/'aspirational_comparators.csv'}")


if __name__ == "__main__":
    main()
